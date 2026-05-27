"""Module 1b — The Bilateral Split.

Module 1 collapsed read → think → act into one model invocation. Module 1b
SEPARATES read from act:

    user prompt ─► [parser model] ─► structured analysis (IR)
                                          │
                                          ▼
                   original prompt + IR ─► [composer model] ─► final answer

Two axes (deliberately small — see docs/limbic-design.md):

    Direction:  parser  vs  composer
    Tier:       fast    vs  deep

Result: 4 bilateral configurations, plus 2 baselines (single-call fast and
single-call deep) for comparison. The point is to FEEL the seam — does
separating input understanding from output composition produce better, cheaper,
or just *different* outputs than monolithic calls?

You will not know until you run several configurations on the same prompt and
compare. The lesson is in the comparison, not in any single run.

Provider scope: Anthropic only. Cross-provider (Module 1c) is the natural next
step; this module deliberately limits the variables to two tiers within one
lab so the bilateral effect is not confounded with provider differences.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field

import anthropic
from dotenv import load_dotenv


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv()

# Tier mapping — "fast" and "deep" are abstractions over concrete model ids,
# so callers do not couple to model names that drift over time. Update here
# when Anthropic ships a new tier and the rest of the module follows.
TIERS = {
    "fast": "claude-haiku-4-5",
    "deep": "claude-sonnet-4-6",
}

# Per-model pricing snapshot in USD per 1M tokens (input, output).
# ALWAYS verify against console.anthropic.com before relying on these for
# anything billable. These exist for the visceral "you spent $X" feedback,
# not for accounting.
PRICING = {
    "claude-haiku-4-5":  (1.00,  5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7":   (15.00, 75.00),
}


# ─────────────────────────────────────────────────────────────────────────────
# Prompts — the entire definition of what each role does
# ─────────────────────────────────────────────────────────────────────────────

# The PARSER's job is to UNDERSTAND, not ANSWER. Its output is structured
# enough that a downstream composer can use it deterministically, but loose
# enough that the parser can express the genuine shape of the input. We
# deliberately keep the IR as labeled plain text rather than strict JSON for
# this first version — JSON adds parse-failure modes that are not the lesson.
# The IR question is open in docs/limbic-design.md §6.
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

# The COMPOSER receives the user's original prompt AND the parser's IR. It is
# explicitly told the user does NOT see the IR, so it must produce a complete,
# self-contained final answer rather than commenting on the analysis.
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
# The data we care about, after a call
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CallResult:
    """One model call's worth of result + telemetry."""
    model: str
    text: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    cost_usd: float


@dataclass
class RunResult:
    """A complete bilateral (or baseline) run.

    `parser` is None for baseline runs. Totals roll up over whichever calls
    actually happened, so the same accounting works for 1-call and 2-call
    runs without special-casing the consumer.
    """
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
        # Parser and composer run sequentially in this module — latencies add.
        # A future module could run them in parallel for speculative parses.
        return (self.parser.latency_seconds if self.parser else 0.0) + self.composer.latency_seconds

    @property
    def total_in_tokens(self) -> int:
        return (self.parser.input_tokens if self.parser else 0) + self.composer.input_tokens

    @property
    def total_out_tokens(self) -> int:
        return (self.parser.output_tokens if self.parser else 0) + self.composer.output_tokens


# ─────────────────────────────────────────────────────────────────────────────
# The call (same shape as Module 1, with system prompts now load-bearing)
# ─────────────────────────────────────────────────────────────────────────────


def _call(
    *,
    model: str,
    system: str,
    user_content: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> CallResult:
    """One round-trip to Anthropic. Same skeleton as Module 1's call_model."""
    client = anthropic.Anthropic()
    started_at = time.perf_counter()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    elapsed = time.perf_counter() - started_at

    text = "".join(b.text for b in response.content if b.type == "text")
    in_tok = response.usage.input_tokens
    out_tok = response.usage.output_tokens
    price_in, price_out = PRICING.get(model, (0.0, 0.0))
    cost = in_tok * price_in / 1_000_000 + out_tok * price_out / 1_000_000

    return CallResult(model, text, in_tok, out_tok, elapsed, cost)


# ─────────────────────────────────────────────────────────────────────────────
# The pipeline configurations
# ─────────────────────────────────────────────────────────────────────────────


def run_bilateral(prompt: str, parser_tier: str, composer_tier: str) -> RunResult:
    """Two-stage: parser first, composer second, IR threaded between them."""
    parser = _call(
        model=TIERS[parser_tier],
        system=PARSER_SYSTEM,
        user_content=prompt,
    )
    composer_input = (
        f"USER'S ORIGINAL QUESTION:\n{prompt}\n\n"
        f"PARSER'S STRUCTURED ANALYSIS:\n{parser.text}"
    )
    composer = _call(
        model=TIERS[composer_tier],
        system=COMPOSER_SYSTEM,
        user_content=composer_input,
    )
    return RunResult(
        label=f"bilateral parser={parser_tier} composer={composer_tier}",
        parser=parser,
        composer=composer,
    )


def run_baseline(prompt: str, tier: str) -> RunResult:
    """Single-call baseline — no parser/composer split, no system prompt
    beyond an empty default. This is what Module 1's bare_call.py did."""
    composer = _call(
        model=TIERS[tier],
        system="",  # explicit no-system to mirror module 1's default behavior
        user_content=prompt,
    )
    return RunResult(label=f"baseline {tier}", parser=None, composer=composer)


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────


def _print_run(run: RunResult, *, show_ir: bool = True) -> None:
    """Print one run's full trace + final answer.

    Final answer goes to stdout (pipe-friendly). Everything else — parser IR,
    per-call telemetry, totals — goes to stderr. Same convention as Module 1.
    """
    err = sys.stderr

    print(f"\n=== {run.label} ===", file=err)

    if run.parser and show_ir:
        print(f"\n--- PARSER ({run.parser.model}) ---", file=err)
        print(run.parser.text, file=err)
        print(
            f"[in={run.parser.input_tokens} out={run.parser.output_tokens} "
            f"cost=${run.parser.cost_usd:.6f} "
            f"latency={run.parser.latency_seconds:.2f}s]",
            file=err,
        )

    print(f"\n--- COMPOSER ({run.composer.model}) ---", file=err)
    print(
        f"[in={run.composer.input_tokens} out={run.composer.output_tokens} "
        f"cost=${run.composer.cost_usd:.6f} "
        f"latency={run.composer.latency_seconds:.2f}s]",
        file=err,
    )

    print(
        f"\n--- TOTAL ---\n"
        f"tokens:  in={run.total_in_tokens}  out={run.total_out_tokens}\n"
        f"cost:    ${run.total_cost:.6f}\n"
        f"latency: {run.total_latency:.2f}s",
        file=err,
    )

    # Final user-facing answer to stdout.
    print(run.final_text)


def _print_comparison_table(runs: list[RunResult]) -> None:
    """Compact summary across runs — pure stderr, after the per-run details."""
    err = sys.stderr
    print("\n=== COMPARISON ===", file=err)
    print(f"{'Configuration':<40} {'In':>6} {'Out':>6} {'Cost':>10} {'Latency':>9}",
          file=err)
    print("-" * 75, file=err)
    for r in runs:
        print(
            f"{r.label:<40} {r.total_in_tokens:>6} {r.total_out_tokens:>6} "
            f"${r.total_cost:>8.6f} {r.total_latency:>7.2f}s",
            file=err,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


ALL_CONFIGS: list[tuple[str, dict]] = [
    ("baseline fast",                    {"mode": "baseline",  "tier": "fast"}),
    ("baseline deep",                    {"mode": "baseline",  "tier": "deep"}),
    ("bilateral parser=fast composer=fast", {"mode": "bilateral", "parser": "fast", "composer": "fast"}),
    ("bilateral parser=fast composer=deep", {"mode": "bilateral", "parser": "fast", "composer": "deep"}),
    ("bilateral parser=deep composer=fast", {"mode": "bilateral", "parser": "deep", "composer": "fast"}),
    ("bilateral parser=deep composer=deep", {"mode": "bilateral", "parser": "deep", "composer": "deep"}),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Module 1b — bilateral split prototype.")
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--parser",   choices=list(TIERS), default="fast",
                    help="parser tier (default: fast)")
    ap.add_argument("--composer", choices=list(TIERS), default="deep",
                    help="composer tier (default: deep)")
    ap.add_argument("--baseline", action="store_true",
                    help="single-call baseline using --composer's tier (no parser stage)")
    ap.add_argument("--all", action="store_true",
                    help="run all 6 configurations on the same prompt and produce a comparison table")
    ap.add_argument("--no-ir", action="store_true",
                    help="hide the parser's intermediate analysis from output")
    args = ap.parse_args()

    # Question from argv, or stdin if argv is empty and stdin is piped.
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
                run = run_baseline(question, cfg["tier"])
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
