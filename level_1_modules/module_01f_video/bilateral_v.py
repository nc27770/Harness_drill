"""Module 1f — Bilateral with Video Input.

Module 1e introduced the capability matrix because audio was *restricted*
(2 of 3 providers). Module 1f turns the screw further: video is *exclusive*
to Google in our 3-lab universe. The parser must be a Google slot — there
is no choice on the input side.

This is the inverse pressure to Module 1e:
  - 1e: 2 of 3 providers, real cross-provider routing decisions remain.
  - 1f: 1 of 3 providers, the only routing decision is parser tier
        (google-fast vs google-deep). The composer can be anywhere.

The bilateral pipeline still earns its keep here, because the composer is
not constrained — Gemini sees the video, distills it to text, and a
non-Google composer can take that text and produce the final answer with
its own prose preferences. This decouples *who has access to the modality*
from *who writes the answer* — exactly the point of the bilateral split.

Read alongside `module_01e_audio/bilateral_a.py`. The diff is:
  - Capability matrix: video added, only on google-* slots.
  - Google adapter: handles inline video bytes (≤20MB) via the same
    {mime_type, data} part shape as audio. Larger files would need
    `genai.upload_file()` — out of scope for this module.
  - No model rewriting in any adapter; Gemini handles video on the same
    model id that handles text/image/audio.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent / "module_01d_modality"))
from assets import fetch as fetch_asset  # noqa: E402

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Slot table + capability matrix (video added, Google-exclusive)
# ─────────────────────────────────────────────────────────────────────────────

SLOTS: dict[str, tuple[str, str]] = {
    "anthropic-fast":   ("anthropic", "claude-haiku-4-5"),
    "anthropic-deep":   ("anthropic", "claude-sonnet-4-6"),
    "openai-fast":      ("openai",    "gpt-4o-mini"),
    "openai-deep":      ("openai",    "gpt-4o"),
    "google-fast":      ("google",    "gemini-2.5-flash"),
    "google-deep":      ("google",    "gemini-2.5-pro"),
}

SLOT_CAPABILITIES: dict[str, set[str]] = {
    "anthropic-fast":   {"text", "image"},
    "anthropic-deep":   {"text", "image"},
    "openai-fast":      {"text", "image", "audio"},
    "openai-deep":      {"text", "image", "audio"},
    "google-fast":      {"text", "image", "audio", "video"},
    "google-deep":      {"text", "image", "audio", "video"},
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
# Prompts — parser told video may be attached
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SYSTEM = """You are an INPUT PARSER for a two-stage LLM pipeline.

Your job is to read the user's question (and any attached video) and
produce a compact STRUCTURED ANALYSIS for a downstream COMPOSER model that
will write the actual answer. The COMPOSER will NOT receive the video —
only your text analysis — so EVERY visual or audio fact the answer might
need MUST appear explicitly in your VIDEO_OBSERVATIONS.

Do NOT answer the question yourself. Produce only the analysis.

Output exactly these labeled sections, in order:

LITERAL_QUESTION: one sentence — what is the user actually asking?
EXPECTED_ANSWER_SHAPE: format, length, level of detail, tone.
DOMAIN: subject area(s).
VIDEO_OBSERVATIONS: if a video is attached, describe the key frames,
  on-screen text, motion, audio, and structural progression in enough
  detail that a model who never sees the video can answer using your
  description alone. If no video, write "no video".
KEY_FACTS_OR_CONCEPTS: bullet list of specific facts, numbers,
  definitions, or concepts the answer should incorporate.
AMBIGUITIES: parts where the question is unclear or the video admits
  multiple readings. If none, write "none".

Be exhaustive on the video — the composer is video-blind."""

COMPOSER_SYSTEM = """You are an OUTPUT COMPOSER in a two-stage LLM pipeline.

You will receive:
  1. The user's original question
  2. A parser's structured analysis (which may include observations from
     a video the user attached — you do NOT see the video)

Use the parser's analysis to ground your response — match the
EXPECTED_ANSWER_SHAPE, incorporate KEY_FACTS_OR_CONCEPTS, draw on
VIDEO_OBSERVATIONS as if you had watched the video yourself.

Write your final answer DIRECTLY TO THE USER. The user does NOT see the
parser's analysis. Do not refer to the parser, the analysis, or the
two-stage process. Just answer."""


# ─────────────────────────────────────────────────────────────────────────────
# CallResult / cost
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CallResult:
    provider: str
    model: str
    text: str
    input_tokens: int
    output_tokens: int
    visible_output_tokens: int
    latency_seconds: float
    cost_usd: float
    error: str | None = None


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    pi, po = PRICING.get(model, (0.0, 0.0))
    return in_tok * pi / 1_000_000 + out_tok * po / 1_000_000


# ─────────────────────────────────────────────────────────────────────────────
# Adapters — only Google supports video; Anthropic + OpenAI guard
# ─────────────────────────────────────────────────────────────────────────────


def _call_anthropic(
    model: str, system: str, user_text: str,
    video_bytes: bytes | None, video_media_type: str | None,
    max_tokens: int, temperature: float,
) -> CallResult:
    if video_bytes is not None:
        raise NotImplementedError(
            "Anthropic models do not natively accept video input. "
            "Route video parsers to google-* slots."
        )
    import anthropic
    client = anthropic.Anthropic()
    request: dict = {
        "model": model, "max_tokens": max_tokens, "temperature": temperature,
        "messages": [{"role": "user", "content": user_text}],
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
    video_bytes: bytes | None, video_media_type: str | None,
    max_tokens: int, temperature: float,
) -> CallResult:
    if video_bytes is not None:
        raise NotImplementedError(
            "OpenAI chat.completions does not accept video input as a content block. "
            "Route video parsers to google-* slots."
        )
    from openai import OpenAI
    client = OpenAI()
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_text})
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
    video_bytes: bytes | None, video_media_type: str | None,
    max_tokens: int, temperature: float,
) -> CallResult:
    """Google: video as inline blob part (mime_type + bytes), same shape as
    audio and image. Inline is capped at ~20MB — for larger videos, use
    `genai.upload_file()` and pass the File object as a part instead. We
    don't take that path here; it's a future-module concern."""
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    m = genai.GenerativeModel(model, system_instruction=system or None)

    parts: list = []
    if video_bytes is not None:
        if len(video_bytes) > 20 * 1024 * 1024:
            return CallResult(
                "google", model, "", 0, 0, 0, 0.0, 0.0,
                error=f"video too large for inline ({len(video_bytes)} bytes); "
                      f"use genai.upload_file() — out of scope for this module",
            )
        parts.append({"mime_type": video_media_type or "video/mp4", "data": video_bytes})
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
         video_bytes: bytes | None = None, video_media_type: str | None = None,
         max_tokens: int = 4096, temperature: float = 0.0) -> CallResult:
    provider, model = SLOTS[slot]
    if video_bytes is not None and "video" not in SLOT_CAPABILITIES[slot]:
        return CallResult(
            provider, model, "", 0, 0, 0, 0.0, 0.0,
            error=f"slot {slot} does not accept video (capabilities: "
                  f"{sorted(SLOT_CAPABILITIES[slot])})",
        )
    try:
        return _DISPATCH[provider](
            model, system, user_text,
            video_bytes, video_media_type,
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
                  video_bytes: bytes | None, video_media_type: str | None) -> RunResult:
    parser = call(
        parser_slot, system=PARSER_SYSTEM, user_text=prompt,
        video_bytes=video_bytes, video_media_type=video_media_type,
    )
    if parser.error:
        return RunResult(
            label=f"bilateral {parser_slot} → {composer_slot}",
            parser=parser,
            composer=CallResult("(skipped)", "(skipped)", "", 0, 0, 0, 0.0, 0.0,
                                error="skipped — parser failed"),
        )
    composer_input = (
        f"USER'S ORIGINAL QUESTION:\n{prompt}\n\n"
        f"PARSER'S STRUCTURED ANALYSIS:\n{parser.text}"
    )
    composer = call(composer_slot, system=COMPOSER_SYSTEM, user_text=composer_input)
    return RunResult(label=f"bilateral {parser_slot} → {composer_slot}",
                     parser=parser, composer=composer)


def run_baseline(prompt: str, slot: str,
                 video_bytes: bytes | None, video_media_type: str | None) -> RunResult:
    composer = call(
        slot, system="", user_text=prompt,
        video_bytes=video_bytes, video_media_type=video_media_type,
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
    print(f"\n--- TOTAL ---\ntokens:  in={run.total_in_tokens}  out={run.total_out_tokens}\n"
          f"cost:    ${run.total_cost:.6f}\nlatency: {run.total_latency:.2f}s", file=err)
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
        print(f"{r.label:<48} {r.total_in_tokens:>6} {r.total_out_tokens:>6} "
              f"${r.total_cost:>8.6f} {r.total_latency:>7.2f}s{flag}", file=err)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


# Curated --all: 2 baselines (Google only — others can't see the video) plus
# 4 bilaterals where a Google parser drives a non-Google composer. The whole
# point of 1f is "Google sees, anyone composes" — most rows in --all show
# that pattern.
ALL_CONFIGS: list[tuple[str, dict]] = [
    ("baseline google-fast",                       {"mode": "baseline", "slot": "google-fast"}),
    ("baseline google-deep",                       {"mode": "baseline", "slot": "google-deep"}),
    ("bilateral google-fast → google-deep",
        {"mode": "bilateral", "parser": "google-fast", "composer": "google-deep"}),
    ("bilateral google-fast → anthropic-deep",
        {"mode": "bilateral", "parser": "google-fast", "composer": "anthropic-deep"}),
    ("bilateral google-fast → openai-deep",
        {"mode": "bilateral", "parser": "google-fast", "composer": "openai-deep"}),
    ("bilateral google-deep → anthropic-deep",
        {"mode": "bilateral", "parser": "google-deep", "composer": "anthropic-deep"}),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Module 1f — bilateral with video input.")
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--video", default=None,
                    help="video URI: s3://bucket/key, http(s)://..., or local path (≤20MB inline)")
    ap.add_argument("--parser",   choices=list(SLOTS), default="google-fast",
                    help="parser slot. Must support video. Default: google-fast")
    ap.add_argument("--composer", choices=list(SLOTS), default="anthropic-deep",
                    help="composer slot. Any slot — composer is video-blind.")
    ap.add_argument("--baseline", action="store_true",
                    help="single-call baseline using --composer's slot")
    ap.add_argument("--all", action="store_true",
                    help="run 6 curated configurations (Google-parsed video, mixed composers)")
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

    video_bytes: bytes | None = None
    video_media_type: str | None = None
    if args.video:
        print(f"[fetching video: {args.video}]", file=sys.stderr)
        video_bytes, video_media_type = fetch_asset(args.video)
        print(f"[fetched: {len(video_bytes)} bytes, media_type={video_media_type}]",
              file=sys.stderr)

    if video_bytes is not None:
        if not args.baseline and "video" not in SLOT_CAPABILITIES[args.parser]:
            print(f"ERROR: --parser {args.parser} does not accept video. "
                  f"Use google-fast or google-deep.", file=sys.stderr)
            return 2
        if args.baseline and "video" not in SLOT_CAPABILITIES[args.composer]:
            print(f"ERROR: --composer {args.composer} (used as baseline) does not accept video. "
                  f"Use google-fast or google-deep.", file=sys.stderr)
            return 2

    if args.all:
        runs: list[RunResult] = []
        for label, cfg in ALL_CONFIGS:
            if cfg["mode"] == "baseline":
                run = run_baseline(question, cfg["slot"], video_bytes, video_media_type)
            else:
                run = run_bilateral(question, cfg["parser"], cfg["composer"],
                                    video_bytes, video_media_type)
            _print_run(run, show_ir=not args.no_ir)
            runs.append(run)
        _print_comparison_table(runs)
        return 0

    if args.baseline:
        run = run_baseline(question, args.composer, video_bytes, video_media_type)
    else:
        run = run_bilateral(question, args.parser, args.composer, video_bytes, video_media_type)
    _print_run(run, show_ir=not args.no_ir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
