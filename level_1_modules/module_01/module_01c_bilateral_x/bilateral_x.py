"""Module 1c — Bilateral, Cross-Provider.

Module 1b proved the bilateral seam within one lab (Anthropic only, two tiers).
Module 1c removes the single-lab constraint: parser and composer can each be
any (provider, tier) combination across Anthropic, OpenAI, and Google.

This is where the *adapter cost* LIMBIC will eventually amortize starts to be
visible. Each lab's API differs in:

  - System prompt placement (top-level field vs. message role vs. constructor arg)
  - Usage accounting (input/output tokens vs. prompt/completion tokens vs.
    prompt/candidate/total tokens with hidden "thinking" tokens)
  - max_tokens semantics (Gemini's thinking-by-default eats this budget before
    any visible output, so the cap must be generous)
  - Response shape (typed content blocks vs. flat content vs. parts array)

The point of this module is *not* to abstract those differences away cleanly —
that's a Level-2 string. The point is to feel them, by writing one adapter per
lab and noting where each one had to bend to fit a uniform internal CallResult.
The bends ARE the lesson; if they were invisible, you wouldn't learn what
LIMBIC's IR ultimately has to handle.

Slots are named `<provider>-<tier>`:

  anthropic-fast   claude-haiku-4-5
  anthropic-deep   claude-sonnet-4-6
  openai-fast      gpt-4o-mini
  openai-deep      gpt-4o
  google-fast      gemini-2.5-flash
  google-deep      gemini-2.5-pro       (note: thinks by default — pay attention to total_tokens)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Slot table — the entire surface where "which model" is a configuration choice
# ─────────────────────────────────────────────────────────────────────────────

SLOTS: dict[str, tuple[str, str]] = {
    # slot              → (provider,  model id)
    "anthropic-fast":   ("anthropic", "claude-haiku-4-5"),
    "anthropic-deep":   ("anthropic", "claude-sonnet-4-6"),
    "openai-fast":      ("openai",    "gpt-4o-mini"),
    "openai-deep":      ("openai",    "gpt-4o"),
    "google-fast":      ("google",    "gemini-2.5-flash"),
    "google-deep":      ("google",    "gemini-2.5-pro"),
}

# Per-model pricing snapshot in USD per 1M tokens (input, output).
# Approximate. Verify against each provider's pricing page before trusting
# these for any billable purpose. They exist for the visceral feedback,
# not for accounting.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5":  (1.00,  5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "gpt-4o-mini":       (0.15,  0.60),
    "gpt-4o":            (2.50, 10.00),
    "gemini-2.5-flash":  (0.30,  2.50),
    "gemini-2.5-pro":    (1.25, 10.00),
}


# ─────────────────────────────────────────────────────────────────────────────
# Prompts (same as 1b — the role definitions don't change, only the dispatcher)
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SYSTEM = """You are an INPUT PARSER for a two-stage LLM pipeline.

Your job is to read the user's question carefully and produce a compact
STRUCTURED ANALYSIS for a downstream COMPOSER model that will write the
actual answer.

Do NOT answer the question yourself. Produce only the analysis.

Output exactly these labeled sections, in order:

LITERAL_QUESTION: one sentence — what is the user actually asking?
EXPECTED_ANSWER_SHAPE: what kind of answer would satisfy them?
  (format, approximate length, level of detail, tone)
DOMAIN: what subject area or areas does this draw from?
KEY_FACTS_OR_CONCEPTS: bullet list of specific facts, numbers, definitions,
  or concepts the answer should incorporate. If you are unsure, say so —
  do not fabricate.
AMBIGUITIES: any places where the question is unclear or could be answered
  multiple ways. If none, write "none".

Be concise. The composer will see your full output along with the original
question."""

COMPOSER_SYSTEM = """You are an OUTPUT COMPOSER in a two-stage LLM pipeline.

You will receive:
  1. The user's original question
  2. A parser's structured analysis of that question

Use the parser's analysis to ground your response — match the
EXPECTED_ANSWER_SHAPE, incorporate KEY_FACTS_OR_CONCEPTS, and address
AMBIGUITIES if relevant.

Write your final answer DIRECTLY TO THE USER. The user does NOT see the
parser's analysis. Do not refer to the parser, the analysis, or the
two-stage process. Just answer."""


# ─────────────────────────────────────────────────────────────────────────────
# CallResult — the uniform internal shape, after every adapter
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CallResult:
    """One call's result + telemetry, normalized across providers.

    `output_tokens` is the BILLABLE output count, which for Gemini includes
    hidden "thinking" tokens that never appear in `text`. This is deliberate:
    cost calculations should reflect what the provider actually charges, not
    a misleading visible-only count. `visible_output_tokens` is provided
    separately for completeness.
    """
    provider: str
    model: str
    text: str
    input_tokens: int
    output_tokens: int          # billable (visible + hidden thinking, where applicable)
    visible_output_tokens: int  # what actually appears in `text`
    latency_seconds: float
    cost_usd: float
    error: str | None = None    # populated when the adapter raised; text is "" in that case


# ─────────────────────────────────────────────────────────────────────────────
# Adapters — one per provider. The bends ARE the lesson.
# ─────────────────────────────────────────────────────────────────────────────


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    pi, po = PRICING.get(model, (0.0, 0.0))
    return in_tok * pi / 1_000_000 + out_tok * po / 1_000_000


def _call_anthropic(model: str, system: str, user_content: str,
                    max_tokens: int, temperature: float) -> CallResult:
    """Anthropic: system is a top-level field; messages is a list of role-typed
    blocks; usage exposes input_tokens/output_tokens directly."""
    import anthropic
    client = anthropic.Anthropic()
    t0 = time.perf_counter()
    request: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": user_content}],
    }
    if system:
        request["system"] = system
    r = client.messages.create(**request)
    dt = time.perf_counter() - t0
    text = "".join(b.text for b in r.content if b.type == "text")
    in_tok = r.usage.input_tokens
    out_tok = r.usage.output_tokens
    return CallResult(
        provider="anthropic", model=model, text=text,
        input_tokens=in_tok, output_tokens=out_tok, visible_output_tokens=out_tok,
        latency_seconds=dt, cost_usd=_cost(model, in_tok, out_tok),
    )


def _call_openai(model: str, system: str, user_content: str,
                 max_tokens: int, temperature: float) -> CallResult:
    """OpenAI: system is a message with role='system' inside the messages
    array; usage uses prompt_tokens/completion_tokens (different field names)."""
    from openai import OpenAI
    client = OpenAI()
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_content})
    t0 = time.perf_counter()
    r = client.chat.completions.create(
        model=model, max_tokens=max_tokens, temperature=temperature, messages=messages,
    )
    dt = time.perf_counter() - t0
    text = r.choices[0].message.content or ""
    in_tok = r.usage.prompt_tokens
    out_tok = r.usage.completion_tokens
    return CallResult(
        provider="openai", model=model, text=text,
        input_tokens=in_tok, output_tokens=out_tok, visible_output_tokens=out_tok,
        latency_seconds=dt, cost_usd=_cost(model, in_tok, out_tok),
    )


def _call_google(model: str, system: str, user_content: str,
                 max_tokens: int, temperature: float) -> CallResult:
    """Google: system is `system_instruction` on the GenerativeModel constructor;
    usage_metadata exposes prompt_token_count, candidates_token_count, and a
    total_token_count that may exceed the sum (the difference is "thinking"
    tokens — billable, never visible). We bill on the total minus prompt."""
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    m = genai.GenerativeModel(model, system_instruction=system or None)
    t0 = time.perf_counter()
    r = m.generate_content(
        user_content,
        generation_config={"max_output_tokens": max_tokens, "temperature": temperature},
    )
    dt = time.perf_counter() - t0

    # If the model burned all its budget on thinking, .text raises. Guard it.
    try:
        text = r.text or ""
    except (ValueError, AttributeError):
        text = ""

    um = r.usage_metadata
    in_tok = um.prompt_token_count
    visible_out = um.candidates_token_count
    # Billable output = total - input. On Gemini 2.5 Pro this includes thinking tokens.
    billable_out = max(um.total_token_count - in_tok, visible_out)
    return CallResult(
        provider="google", model=model, text=text,
        input_tokens=in_tok, output_tokens=billable_out, visible_output_tokens=visible_out,
        latency_seconds=dt, cost_usd=_cost(model, in_tok, billable_out),
    )


_DISPATCH = {
    "anthropic": _call_anthropic,
    "openai":    _call_openai,
    "google":    _call_google,
}


def call(slot: str, *, system: str, user_content: str,
         max_tokens: int = 2048, temperature: float = 0.0) -> CallResult:
    """Uniform entry point. Resolve slot → (provider, model), dispatch.

    max_tokens defaults to 2048 (not 1024 like Module 1) because Gemini 2.5
    Pro's thinking-by-default can consume the budget before any visible
    output appears. 2048 leaves slack on every provider without breaking
    the bank.

    Errors from the adapters are caught and surfaced via CallResult.error so
    a single provider's failure doesn't poison a multi-config matrix run.
    """
    provider, model = SLOTS[slot]
    try:
        return _DISPATCH[provider](model, system, user_content, max_tokens, temperature)
    except Exception as e:
        return CallResult(
            provider=provider, model=model, text="",
            input_tokens=0, output_tokens=0, visible_output_tokens=0,
            latency_seconds=0.0, cost_usd=0.0, error=f"{type(e).__name__}: {e}"[:200],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrators
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RunResult:
    label: str
    parser: CallResult | None
    composer: CallResult
    final_text: str = field(init=False)

    def __post_init__(self) -> None:
        self.final_text = self.composer.text

    @property
    def total_cost(self) -> float:
        return (self.parser.cost_usd if self.parser else 0.0) + self.composer.cost_usd

    @property
    def total_latency(self) -> float:
        return (self.parser.latency_seconds if self.parser else 0.0) + self.composer.latency_seconds

    @property
    def total_in_tokens(self) -> int:
        return (self.parser.input_tokens if self.parser else 0) + self.composer.input_tokens

    @property
    def total_out_tokens(self) -> int:
        return (self.parser.output_tokens if self.parser else 0) + self.composer.output_tokens

    @property
    def has_error(self) -> bool:
        return bool(self.composer.error) or bool(self.parser and self.parser.error)


def run_bilateral(prompt: str, parser_slot: str, composer_slot: str) -> RunResult:
    parser = call(parser_slot, system=PARSER_SYSTEM, user_content=prompt)
    if parser.error:
        # Don't waste a composer call when the parser already failed.
        return RunResult(
            label=f"bilateral {parser_slot} → {composer_slot}",
            parser=parser,
            composer=CallResult(
                provider="(skipped)", model="(skipped)", text="",
                input_tokens=0, output_tokens=0, visible_output_tokens=0,
                latency_seconds=0.0, cost_usd=0.0,
                error="skipped — parser failed",
            ),
        )
    composer_input = (
        f"USER'S ORIGINAL QUESTION:\n{prompt}\n\n"
        f"PARSER'S STRUCTURED ANALYSIS:\n{parser.text}"
    )
    composer = call(composer_slot, system=COMPOSER_SYSTEM, user_content=composer_input)
    return RunResult(
        label=f"bilateral {parser_slot} → {composer_slot}",
        parser=parser, composer=composer,
    )


def run_baseline(prompt: str, slot: str) -> RunResult:
    composer = call(slot, system="", user_content=prompt)
    return RunResult(label=f"baseline {slot}", parser=None, composer=composer)


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────


def _print_run(run: RunResult, *, show_ir: bool = True) -> None:
    err = sys.stderr
    print(f"\n=== {run.label} ===", file=err)

    if run.parser is not None:
        p = run.parser
        print(f"\n--- PARSER ({p.provider}/{p.model}) ---", file=err)
        if p.error:
            print(f"ERROR: {p.error}", file=err)
        else:
            if show_ir:
                print(p.text, file=err)
            extra = ""
            if p.output_tokens != p.visible_output_tokens:
                extra = f" (visible={p.visible_output_tokens}, +thinking={p.output_tokens - p.visible_output_tokens})"
            print(f"[in={p.input_tokens} out={p.output_tokens}{extra} "
                  f"cost=${p.cost_usd:.6f} latency={p.latency_seconds:.2f}s]", file=err)

    c = run.composer
    print(f"\n--- COMPOSER ({c.provider}/{c.model}) ---", file=err)
    if c.error:
        print(f"ERROR: {c.error}", file=err)
    else:
        extra = ""
        if c.output_tokens != c.visible_output_tokens:
            extra = f" (visible={c.visible_output_tokens}, +thinking={c.output_tokens - c.visible_output_tokens})"
        print(f"[in={c.input_tokens} out={c.output_tokens}{extra} "
              f"cost=${c.cost_usd:.6f} latency={c.latency_seconds:.2f}s]", file=err)

    print(
        f"\n--- TOTAL ---\n"
        f"tokens:  in={run.total_in_tokens}  out={run.total_out_tokens}\n"
        f"cost:    ${run.total_cost:.6f}\n"
        f"latency: {run.total_latency:.2f}s",
        file=err,
    )

    if run.composer.text:
        print(run.composer.text)


def _print_comparison_table(runs: list[RunResult]) -> None:
    err = sys.stderr
    print("\n=== COMPARISON ===", file=err)
    print(f"{'Configuration':<48} {'In':>6} {'Out':>6} {'Cost':>10} {'Latency':>9}",
          file=err)
    print("-" * 84, file=err)
    for r in runs:
        flag = "  ⚠" if r.has_error else ""
        print(
            f"{r.label:<48} {r.total_in_tokens:>6} {r.total_out_tokens:>6} "
            f"${r.total_cost:>8.6f} {r.total_latency:>7.2f}s{flag}",
            file=err,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


# Curated --all set: small enough to run in a few minutes, broad enough to
# show both the same-lab and cross-lab signal. 12 configurations.
ALL_CONFIGS: list[tuple[str, dict]] = [
    # 6 baselines — one per slot
    ("baseline anthropic-fast", {"mode": "baseline", "slot": "anthropic-fast"}),
    ("baseline anthropic-deep", {"mode": "baseline", "slot": "anthropic-deep"}),
    ("baseline openai-fast",    {"mode": "baseline", "slot": "openai-fast"}),
    ("baseline openai-deep",    {"mode": "baseline", "slot": "openai-deep"}),
    ("baseline google-fast",    {"mode": "baseline", "slot": "google-fast"}),
    ("baseline google-deep",    {"mode": "baseline", "slot": "google-deep"}),
    # 3 same-provider bilateral fast→deep (controls for provider, isolates the seam)
    ("bilateral anthropic-fast → anthropic-deep",
        {"mode": "bilateral", "parser": "anthropic-fast", "composer": "anthropic-deep"}),
    ("bilateral openai-fast → openai-deep",
        {"mode": "bilateral", "parser": "openai-fast", "composer": "openai-deep"}),
    ("bilateral google-fast → google-deep",
        {"mode": "bilateral", "parser": "google-fast", "composer": "google-deep"}),
    # 3 cross-provider bilateral — illustrative pairings
    ("bilateral google-fast → anthropic-deep",
        {"mode": "bilateral", "parser": "google-fast", "composer": "anthropic-deep"}),
    ("bilateral openai-fast → anthropic-deep",
        {"mode": "bilateral", "parser": "openai-fast", "composer": "anthropic-deep"}),
    ("bilateral anthropic-fast → google-deep",
        {"mode": "bilateral", "parser": "anthropic-fast", "composer": "google-deep"}),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Module 1c — cross-provider bilateral split.")
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--parser",   choices=list(SLOTS), default="anthropic-fast",
                    help="parser slot (default: anthropic-fast)")
    ap.add_argument("--composer", choices=list(SLOTS), default="anthropic-deep",
                    help="composer slot (default: anthropic-deep)")
    ap.add_argument("--baseline", action="store_true",
                    help="single-call baseline using --composer's slot")
    ap.add_argument("--all", action="store_true",
                    help="run all 12 curated configurations and produce a comparison table")
    ap.add_argument("--no-ir", action="store_true",
                    help="hide the parser's intermediate analysis from output")
    args = ap.parse_args()

    if args.prompt:
        question = " ".join(args.prompt)
    elif not sys.stdin.isatty():
        question = sys.stdin.read().strip()
    else:
        ap.print_help()
        return 2

    if args.all:
        runs: list[RunResult] = []
        for label, cfg in ALL_CONFIGS:
            if cfg["mode"] == "baseline":
                run = run_baseline(question, cfg["slot"])
            else:
                run = run_bilateral(question, cfg["parser"], cfg["composer"])
            _print_run(run, show_ir=not args.no_ir)
            runs.append(run)
        _print_comparison_table(runs)
        return 0

    if args.baseline:
        run = run_baseline(question, args.composer)
    else:
        run = run_bilateral(question, args.parser, args.composer)
    _print_run(run, show_ir=not args.no_ir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
