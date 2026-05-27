"""Module 1d — Bilateral with Modality (image input).

Module 1c's bilateral pipeline routed across providers but stayed text-only.
Module 1d adds a single new degree of freedom — image input — and that is
enough to make the bilateral split *forced*, not optional:

  - Each lab's API serializes images differently (the "API drift" tax).
  - The parser is the natural seat for image perception; the composer
    receives only the parser's text IR.
  - The composer never sees the image, so we don't pay the image-token bill
    twice. This is a first taste of cost-aware modality routing.

Read this file alongside `module_01c_bilateral_x/bilateral_x.py`. Most of
the diff is in the three `_call_*` adapters — three different ways to attach
the same bytes.

Slots are unchanged from 1c (all six current slots have vision):

    anthropic-fast / anthropic-deep / openai-fast / openai-deep
    google-fast    / google-deep
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Make `assets` importable when run from any cwd. Put this dir on sys.path
# so `from assets import fetch` works whether you launch from the repo root,
# the module dir, or anywhere else.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assets import fetch as fetch_asset  # noqa: E402

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Slot table (unchanged from 1c)
# ─────────────────────────────────────────────────────────────────────────────

SLOTS: dict[str, tuple[str, str]] = {
    "anthropic-fast":   ("anthropic", "claude-haiku-4-5"),
    "anthropic-deep":   ("anthropic", "claude-sonnet-4-6"),
    "openai-fast":      ("openai",    "gpt-4o-mini"),
    "openai-deep":      ("openai",    "gpt-4o"),
    "google-fast":      ("google",    "gemini-2.5-flash"),
    "google-deep":      ("google",    "gemini-2.5-pro"),
}

PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5":  (1.00,  5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "gpt-4o-mini":       (0.15,  0.60),
    "gpt-4o":            (2.50, 10.00),
    "gemini-2.5-flash":  (0.30,  2.50),
    "gemini-2.5-pro":    (1.25, 10.00),
}


# ─────────────────────────────────────────────────────────────────────────────
# Prompts — minor tweak: parser is told it may receive an image
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SYSTEM = """You are an INPUT PARSER for a two-stage LLM pipeline.

Your job is to read the user's question (and any attached image) carefully
and produce a compact STRUCTURED ANALYSIS for a downstream COMPOSER model
that will write the actual answer. The COMPOSER will NOT see the image —
only your analysis — so any visual information the answer needs MUST appear
explicitly in your KEY_FACTS_OR_CONCEPTS.

Do NOT answer the question yourself. Produce only the analysis.

Output exactly these labeled sections, in order:

LITERAL_QUESTION: one sentence — what is the user actually asking?
EXPECTED_ANSWER_SHAPE: what kind of answer would satisfy them?
  (format, approximate length, level of detail, tone)
DOMAIN: what subject area or areas does this draw from?
VISUAL_OBSERVATIONS: if an image is attached, describe what is in it in
  enough detail that a model who never sees the image can answer the user's
  question using your description alone. Numbers, labels, structural
  relationships — everything the answer might need. If no image, write
  "no image".
KEY_FACTS_OR_CONCEPTS: bullet list of specific facts, numbers, definitions,
  or concepts the answer should incorporate.
AMBIGUITIES: anywhere the question is unclear or the image admits multiple
  readings. If none, write "none".

Be concise but exhaustive about visual content — the composer is blind to
the image."""

COMPOSER_SYSTEM = """You are an OUTPUT COMPOSER in a two-stage LLM pipeline.

You will receive:
  1. The user's original question
  2. A parser's structured analysis (which may include observations about
     an image the user attached — you do NOT see the image directly)

Use the parser's analysis to ground your response — match the
EXPECTED_ANSWER_SHAPE, incorporate KEY_FACTS_OR_CONCEPTS, draw on
VISUAL_OBSERVATIONS as if you had seen the image yourself.

Write your final answer DIRECTLY TO THE USER. The user does NOT see the
parser's analysis. Do not refer to the parser, the analysis, or the
two-stage process. Just answer."""


# ─────────────────────────────────────────────────────────────────────────────
# CallResult (unchanged from 1c)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CallResult:
    provider: str
    model: str
    text: str
    input_tokens: int
    output_tokens: int          # billable (visible + hidden thinking, where applicable)
    visible_output_tokens: int
    latency_seconds: float
    cost_usd: float
    error: str | None = None


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    pi, po = PRICING.get(model, (0.0, 0.0))
    return in_tok * pi / 1_000_000 + out_tok * po / 1_000_000


# ─────────────────────────────────────────────────────────────────────────────
# Adapters — image attachment is where they diverge most
# ─────────────────────────────────────────────────────────────────────────────


def _call_anthropic(
    model: str, system: str, user_text: str,
    image_bytes: bytes | None, image_media_type: str | None,
    max_tokens: int, temperature: float,
) -> CallResult:
    """Anthropic: image goes in `messages[0].content` as a typed block of
    `type=image` with a base64 source. Image block precedes the text block."""
    import anthropic
    client = anthropic.Anthropic()

    content_blocks: list[dict] = []
    if image_bytes is not None:
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_media_type or "image/png",
                "data": base64.b64encode(image_bytes).decode("ascii"),
            },
        })
    content_blocks.append({"type": "text", "text": user_text})

    request: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content_blocks}],
    }
    if system:
        request["system"] = system

    t0 = time.perf_counter()
    r = client.messages.create(**request)
    dt = time.perf_counter() - t0

    text = "".join(b.text for b in r.content if b.type == "text")
    in_tok, out_tok = r.usage.input_tokens, r.usage.output_tokens
    return CallResult("anthropic", model, text, in_tok, out_tok, out_tok, dt,
                      _cost(model, in_tok, out_tok))


def _call_openai(
    model: str, system: str, user_text: str,
    image_bytes: bytes | None, image_media_type: str | None,
    max_tokens: int, temperature: float,
) -> CallResult:
    """OpenAI: image goes inside the user message's content array as a
    `type=image_url` part — the URL field accepts data: URIs (RFC 2397),
    so we base64-encode and prefix with the media type."""
    from openai import OpenAI
    client = OpenAI()

    user_parts: list[dict] = []
    if image_bytes is not None:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        user_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{image_media_type or 'image/png'};base64,{b64}"},
        })
    user_parts.append({"type": "text", "text": user_text})

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_parts})

    t0 = time.perf_counter()
    r = client.chat.completions.create(
        model=model, max_tokens=max_tokens, temperature=temperature, messages=messages,
    )
    dt = time.perf_counter() - t0

    text = r.choices[0].message.content or ""
    in_tok, out_tok = r.usage.prompt_tokens, r.usage.completion_tokens
    return CallResult("openai", model, text, in_tok, out_tok, out_tok, dt,
                      _cost(model, in_tok, out_tok))


def _call_google(
    model: str, system: str, user_text: str,
    image_bytes: bytes | None, image_media_type: str | None,
    max_tokens: int, temperature: float,
) -> CallResult:
    """Google: image goes as an inline blob part — a dict with mime_type and
    raw bytes (no base64 — the SDK encodes for us). Parts are passed as a
    list to generate_content alongside the text part."""
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    m = genai.GenerativeModel(model, system_instruction=system or None)

    parts: list = []
    if image_bytes is not None:
        parts.append({"mime_type": image_media_type or "image/png", "data": image_bytes})
    parts.append(user_text)

    t0 = time.perf_counter()
    r = m.generate_content(
        parts,
        generation_config={"max_output_tokens": max_tokens, "temperature": temperature},
    )
    dt = time.perf_counter() - t0

    try:
        text = r.text or ""
    except (ValueError, AttributeError):
        text = ""

    um = r.usage_metadata
    in_tok = um.prompt_token_count
    visible_out = um.candidates_token_count
    billable_out = max(um.total_token_count - in_tok, visible_out)
    return CallResult("google", model, text, in_tok, billable_out, visible_out, dt,
                      _cost(model, in_tok, billable_out))


_DISPATCH = {
    "anthropic": _call_anthropic,
    "openai":    _call_openai,
    "google":    _call_google,
}


def call(slot: str, *, system: str, user_text: str,
         image_bytes: bytes | None = None, image_media_type: str | None = None,
         max_tokens: int = 2048, temperature: float = 0.0) -> CallResult:
    provider, model = SLOTS[slot]
    try:
        return _DISPATCH[provider](
            model, system, user_text,
            image_bytes, image_media_type,
            max_tokens, temperature,
        )
    except Exception as e:
        return CallResult(provider, model, "", 0, 0, 0, 0.0, 0.0,
                          error=f"{type(e).__name__}: {e}"[:200])


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


def run_bilateral(prompt: str, parser_slot: str, composer_slot: str,
                  image_bytes: bytes | None, image_media_type: str | None) -> RunResult:
    parser = call(
        parser_slot, system=PARSER_SYSTEM, user_text=prompt,
        image_bytes=image_bytes, image_media_type=image_media_type,
    )
    if parser.error:
        return RunResult(
            label=f"bilateral {parser_slot} → {composer_slot}",
            parser=parser,
            composer=CallResult("(skipped)", "(skipped)", "", 0, 0, 0, 0.0, 0.0,
                                error="skipped — parser failed"),
        )

    # Composer is intentionally blind to the image. It receives only the
    # original question + the parser's text-only IR. This is deliberate
    # cost optimization — we don't want to re-pay the image-token tax on
    # every composer attempt across configurations.
    composer_input = (
        f"USER'S ORIGINAL QUESTION:\n{prompt}\n\n"
        f"PARSER'S STRUCTURED ANALYSIS:\n{parser.text}"
    )
    composer = call(composer_slot, system=COMPOSER_SYSTEM, user_text=composer_input)
    return RunResult(label=f"bilateral {parser_slot} → {composer_slot}",
                     parser=parser, composer=composer)


def run_baseline(prompt: str, slot: str,
                 image_bytes: bytes | None, image_media_type: str | None) -> RunResult:
    """Baseline runs with the image attached directly — no parser stage."""
    composer = call(
        slot, system="", user_text=prompt,
        image_bytes=image_bytes, image_media_type=image_media_type,
    )
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


ALL_CONFIGS: list[tuple[str, dict]] = [
    ("baseline anthropic-deep", {"mode": "baseline", "slot": "anthropic-deep"}),
    ("baseline openai-deep",    {"mode": "baseline", "slot": "openai-deep"}),
    ("baseline google-deep",    {"mode": "baseline", "slot": "google-deep"}),
    ("bilateral anthropic-fast → anthropic-deep",
        {"mode": "bilateral", "parser": "anthropic-fast", "composer": "anthropic-deep"}),
    ("bilateral openai-fast → openai-deep",
        {"mode": "bilateral", "parser": "openai-fast", "composer": "openai-deep"}),
    ("bilateral google-fast → google-deep",
        {"mode": "bilateral", "parser": "google-fast", "composer": "google-deep"}),
    ("bilateral google-fast → anthropic-deep",
        {"mode": "bilateral", "parser": "google-fast", "composer": "anthropic-deep"}),
    ("bilateral anthropic-fast → google-deep",
        {"mode": "bilateral", "parser": "anthropic-fast", "composer": "google-deep"}),
    ("bilateral openai-fast → anthropic-deep",
        {"mode": "bilateral", "parser": "openai-fast", "composer": "anthropic-deep"}),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Module 1d — bilateral with image input.")
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--image", default=None,
                    help="image URI: s3://bucket/key, http(s)://..., or a local path")
    ap.add_argument("--parser",   choices=list(SLOTS), default="google-fast",
                    help="parser slot (default: google-fast — Gemini's native multimodal makes it a strong cheap parser)")
    ap.add_argument("--composer", choices=list(SLOTS), default="anthropic-deep",
                    help="composer slot (default: anthropic-deep)")
    ap.add_argument("--baseline", action="store_true",
                    help="single-call baseline using --composer's slot")
    ap.add_argument("--all", action="store_true",
                    help="run 9 curated configurations and produce a comparison table")
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

    image_bytes: bytes | None = None
    image_media_type: str | None = None
    if args.image:
        print(f"[fetching image: {args.image}]", file=sys.stderr)
        image_bytes, image_media_type = fetch_asset(args.image)
        print(f"[fetched: {len(image_bytes)} bytes, media_type={image_media_type}]",
              file=sys.stderr)

    if args.all:
        runs: list[RunResult] = []
        for label, cfg in ALL_CONFIGS:
            if cfg["mode"] == "baseline":
                run = run_baseline(question, cfg["slot"], image_bytes, image_media_type)
            else:
                run = run_bilateral(question, cfg["parser"], cfg["composer"],
                                    image_bytes, image_media_type)
            _print_run(run, show_ir=not args.no_ir)
            runs.append(run)
        _print_comparison_table(runs)
        return 0

    if args.baseline:
        run = run_baseline(question, args.composer, image_bytes, image_media_type)
    else:
        run = run_bilateral(question, args.parser, args.composer,
                            image_bytes, image_media_type)
    _print_run(run, show_ir=not args.no_ir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
