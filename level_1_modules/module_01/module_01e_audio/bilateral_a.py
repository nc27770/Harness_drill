"""Module 1e — Bilateral with Audio Input.

Module 1d added image, but every slot could handle it — modality routing
was a *cost* optimization, not a *capability* requirement. Module 1e adds
audio, which only OpenAI and Google natively accept. Anthropic slots
become illegal as parsers in audio mode, and the harness must enforce that.

This is the first place in the curriculum where the **slot capability
matrix** is load-bearing. It's also the first place where LIMBIC's
"modality routing is forced, not optional" thesis lands as code: dispatch
the audio parser, or refuse the request — there is no provider-agnostic
fallback short of adding a transcription step (Whisper, etc.), which we
defer to a future module.

Read alongside `module_01d_modality/bilateral_m.py`. The diff is in three
places:
  1. SLOT_CAPABILITIES — new dict, declares which slots accept which modalities.
  2. The OpenAI adapter — audio requires `gpt-4o-audio-preview` model variants
     (chat.completions audio is gated to specific models, not all GPT-4o slots).
  3. Capability validation in `call()` — fail fast on incompatible slot/modality.

The Anthropic adapter raises NotImplementedError on audio. Defensive — the
capability check upstream should already prevent this, but the error is
informative if someone bypasses the harness.
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

# Borrow assets.py from Module 1d. assets is genuinely a primitive — it
# doesn't change between modules, so duplicating it would be the start of
# drift. When the curriculum promotes a `common/` directory (per the README's
# "added when patterns stabilize" note), assets.py is the first thing to
# move there. Until then, this import is the explicit signal that the
# pattern is shared.
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent / "module_01d_modality"))
from assets import fetch as fetch_asset  # noqa: E402

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Slot table + capability matrix
# ─────────────────────────────────────────────────────────────────────────────

SLOTS: dict[str, tuple[str, str]] = {
    "anthropic-fast":   ("anthropic", "claude-haiku-4-5"),
    "anthropic-deep":   ("anthropic", "claude-sonnet-4-6"),
    "openai-fast":      ("openai",    "gpt-4o-mini"),
    "openai-deep":      ("openai",    "gpt-4o"),
    "google-fast":      ("google",    "gemini-2.5-flash"),
    "google-deep":      ("google",    "gemini-2.5-pro"),
}

# Modalities each slot accepts as INPUT. "text" is universal. "image" was
# already universal in 1d. "audio" is the new restrictor — Anthropic Claude
# does not currently accept audio in messages.create. (When it does, just
# add "audio" to those slots' sets and the rest of the harness picks it up.)
SLOT_CAPABILITIES: dict[str, set[str]] = {
    "anthropic-fast":   {"text", "image"},
    "anthropic-deep":   {"text", "image"},
    "openai-fast":      {"text", "image", "audio"},
    "openai-deep":      {"text", "image", "audio"},
    "google-fast":      {"text", "image", "audio", "video"},
    "google-deep":      {"text", "image", "audio", "video"},
}

# OpenAI's chat.completions API gates audio input to specific "audio-preview"
# model variants — calling plain gpt-4o with an input_audio block fails. The
# adapter rewrites the slot's model id when audio is present.
OPENAI_AUDIO_MODELS: dict[str, str] = {
    "gpt-4o":      "gpt-4o-audio-preview",
    "gpt-4o-mini": "gpt-4o-mini-audio-preview",
}

PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5":           (1.00,  5.00),
    "claude-sonnet-4-6":          (3.00, 15.00),
    "gpt-4o-mini":                (0.15,  0.60),
    "gpt-4o":                     (2.50, 10.00),
    "gpt-4o-mini-audio-preview":  (0.15,  0.60),  # same base pricing; audio tokens billed separately by provider
    "gpt-4o-audio-preview":       (2.50, 10.00),
    "gemini-2.5-flash":           (0.30,  2.50),
    "gemini-2.5-pro":             (1.25, 10.00),
}


# ─────────────────────────────────────────────────────────────────────────────
# Prompts — parser is told audio may be attached and the composer is blind to it
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SYSTEM = """You are an INPUT PARSER for a two-stage LLM pipeline.

Your job is to read the user's question (and any attached audio) carefully
and produce a compact STRUCTURED ANALYSIS for a downstream COMPOSER model
that will write the actual answer. The COMPOSER will NOT receive the audio
— only your text analysis — so any spoken content the answer needs MUST
appear explicitly in your TRANSCRIPT_OR_OBSERVATIONS.

Do NOT answer the question yourself. Produce only the analysis.

Output exactly these labeled sections, in order:

LITERAL_QUESTION: one sentence — what is the user actually asking?
EXPECTED_ANSWER_SHAPE: what kind of answer would satisfy them?
  (format, approximate length, level of detail, tone)
DOMAIN: what subject area or areas does this draw from?
TRANSCRIPT_OR_OBSERVATIONS: if audio is attached, transcribe it verbatim
  AND describe any non-speech features (tone, speakers, music, background
  noise). If no audio, write "no audio".
KEY_FACTS_OR_CONCEPTS: bullet list of specific facts, numbers, definitions,
  or concepts the answer should incorporate.
AMBIGUITIES: anywhere the question is unclear or the audio is hard to
  understand. If none, write "none".

Be exhaustive on the transcript — the composer is deaf to the audio."""

COMPOSER_SYSTEM = """You are an OUTPUT COMPOSER in a two-stage LLM pipeline.

You will receive:
  1. The user's original question
  2. A parser's structured analysis (which may include a transcript of audio
     the user attached — you do NOT receive the audio directly)

Use the parser's analysis to ground your response — match the
EXPECTED_ANSWER_SHAPE, incorporate KEY_FACTS_OR_CONCEPTS, and treat the
TRANSCRIPT_OR_OBSERVATIONS as your only window into the audio.

Write your final answer DIRECTLY TO THE USER. The user does NOT see the
parser's analysis. Do not refer to the parser, the analysis, or the
two-stage process. Just answer."""


# ─────────────────────────────────────────────────────────────────────────────
# CallResult (unchanged from 1d)
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
# Adapters — audio attachment differs from image in subtle but real ways
# ─────────────────────────────────────────────────────────────────────────────


def _media_type_to_audio_format(mt: str) -> str:
    """OpenAI's input_audio block expects a `format` field with values like
    "wav" or "mp3" — not full media types. Translate."""
    return {
        "audio/mpeg": "mp3", "audio/mp3": "mp3",
        "audio/wav":  "wav", "audio/x-wav": "wav",
        "audio/mp4":  "m4a",
        "audio/ogg":  "ogg", "audio/flac": "flac",
    }.get(mt, "mp3")


def _call_anthropic(
    model: str, system: str, user_text: str,
    audio_bytes: bytes | None, audio_media_type: str | None,
    max_tokens: int, temperature: float,
) -> CallResult:
    """Anthropic does not natively accept audio. Defensive guard — the
    capability check in call() should prevent us from getting here, but
    this raises with a clear message if it ever does."""
    if audio_bytes is not None:
        raise NotImplementedError(
            "Anthropic models do not natively accept audio input. "
            "Route audio parsers to openai-* or google-* slots, or add a "
            "transcription step (e.g., Whisper) before this adapter."
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
    audio_bytes: bytes | None, audio_media_type: str | None,
    max_tokens: int, temperature: float,
) -> CallResult:
    """OpenAI: audio goes inside the user message's content array as a
    `type=input_audio` part with base64-encoded bytes and a 'format' tag.
    BUT — chat.completions audio is gated to specific models. The adapter
    rewrites gpt-4o → gpt-4o-audio-preview when audio is present."""
    from openai import OpenAI
    client = OpenAI()

    effective_model = model
    user_parts: list[dict] = []
    if audio_bytes is not None:
        effective_model = OPENAI_AUDIO_MODELS.get(model, model)
        user_parts.append({
            "type": "input_audio",
            "input_audio": {
                "data": base64.b64encode(audio_bytes).decode("ascii"),
                "format": _media_type_to_audio_format(audio_media_type or "audio/mpeg"),
            },
        })
    user_parts.append({"type": "text", "text": user_text})

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_parts})

    t0 = time.perf_counter()
    r = client.chat.completions.create(
        model=effective_model, max_tokens=max_tokens, temperature=temperature,
        messages=messages,
    )
    dt = time.perf_counter() - t0

    text = r.choices[0].message.content or ""
    in_tok, out_tok = r.usage.prompt_tokens, r.usage.completion_tokens
    return CallResult("openai", effective_model, text, in_tok, out_tok, out_tok, dt,
                      _cost(effective_model, in_tok, out_tok))


def _call_google(
    model: str, system: str, user_text: str,
    audio_bytes: bytes | None, audio_media_type: str | None,
    max_tokens: int, temperature: float,
) -> CallResult:
    """Google: audio is just another inline blob part — same shape as image,
    different mime_type. Of the three providers, Google is the most uniform
    in how it handles modalities at the API level."""
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    m = genai.GenerativeModel(model, system_instruction=system or None)

    parts: list = []
    if audio_bytes is not None:
        parts.append({"mime_type": audio_media_type or "audio/mpeg", "data": audio_bytes})
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
         audio_bytes: bytes | None = None, audio_media_type: str | None = None,
         max_tokens: int = 4096, temperature: float = 0.0) -> CallResult:
    """Dispatch with capability checking.

    max_tokens default bumped to 4096 (vs 2048 in 1d) because audio
    transcription often runs longer than image description, and Gemini's
    thinking-by-default still applies.
    """
    provider, model = SLOTS[slot]
    if audio_bytes is not None and "audio" not in SLOT_CAPABILITIES[slot]:
        return CallResult(
            provider, model, "", 0, 0, 0, 0.0, 0.0,
            error=f"slot {slot} does not accept audio (capabilities: "
                  f"{sorted(SLOT_CAPABILITIES[slot])})",
        )
    try:
        return _DISPATCH[provider](
            model, system, user_text,
            audio_bytes, audio_media_type,
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
                  audio_bytes: bytes | None, audio_media_type: str | None) -> RunResult:
    parser = call(
        parser_slot, system=PARSER_SYSTEM, user_text=prompt,
        audio_bytes=audio_bytes, audio_media_type=audio_media_type,
    )
    if parser.error:
        return RunResult(
            label=f"bilateral {parser_slot} → {composer_slot}",
            parser=parser,
            composer=CallResult("(skipped)", "(skipped)", "", 0, 0, 0, 0.0, 0.0,
                                error="skipped — parser failed"),
        )

    # Composer never sees the audio. It receives only the parser's text IR.
    composer_input = (
        f"USER'S ORIGINAL QUESTION:\n{prompt}\n\n"
        f"PARSER'S STRUCTURED ANALYSIS:\n{parser.text}"
    )
    composer = call(composer_slot, system=COMPOSER_SYSTEM, user_text=composer_input)
    return RunResult(label=f"bilateral {parser_slot} → {composer_slot}",
                     parser=parser, composer=composer)


def run_baseline(prompt: str, slot: str,
                 audio_bytes: bytes | None, audio_media_type: str | None) -> RunResult:
    composer = call(
        slot, system="", user_text=prompt,
        audio_bytes=audio_bytes, audio_media_type=audio_media_type,
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


# Curated --all: only audio-capable parsers (openai-*, google-*). Composers
# can be any slot since they only see text. 7 configs total.
ALL_CONFIGS: list[tuple[str, dict]] = [
    # 4 baselines on audio-capable slots only
    ("baseline openai-fast",    {"mode": "baseline", "slot": "openai-fast"}),
    ("baseline openai-deep",    {"mode": "baseline", "slot": "openai-deep"}),
    ("baseline google-fast",    {"mode": "baseline", "slot": "google-fast"}),
    ("baseline google-deep",    {"mode": "baseline", "slot": "google-deep"}),
    # 3 bilateral with audio-capable parser, mixed composers
    ("bilateral google-fast → anthropic-deep",
        {"mode": "bilateral", "parser": "google-fast", "composer": "anthropic-deep"}),
    ("bilateral openai-fast → anthropic-deep",
        {"mode": "bilateral", "parser": "openai-fast", "composer": "anthropic-deep"}),
    ("bilateral google-fast → google-deep",
        {"mode": "bilateral", "parser": "google-fast", "composer": "google-deep"}),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Module 1e — bilateral with audio input.")
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--audio", default=None,
                    help="audio URI: s3://bucket/key, http(s)://..., or local path")
    ap.add_argument("--parser",   choices=list(SLOTS), default="google-fast",
                    help="parser slot. Must support audio. Default: google-fast")
    ap.add_argument("--composer", choices=list(SLOTS), default="anthropic-deep",
                    help="composer slot. Any slot — composer only sees text IR.")
    ap.add_argument("--baseline", action="store_true",
                    help="single-call baseline using --composer's slot")
    ap.add_argument("--all", action="store_true",
                    help="run 7 curated audio-capable configurations")
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

    audio_bytes: bytes | None = None
    audio_media_type: str | None = None
    if args.audio:
        print(f"[fetching audio: {args.audio}]", file=sys.stderr)
        audio_bytes, audio_media_type = fetch_asset(args.audio)
        print(f"[fetched: {len(audio_bytes)} bytes, media_type={audio_media_type}]",
              file=sys.stderr)

    # Pre-validate the chosen slots when audio is involved. Fail fast with
    # a useful message rather than letting the adapter raise mid-pipeline.
    if audio_bytes is not None:
        if not args.baseline and "audio" not in SLOT_CAPABILITIES[args.parser]:
            print(f"ERROR: --parser {args.parser} does not accept audio. "
                  f"Try: openai-fast, openai-deep, google-fast, google-deep.",
                  file=sys.stderr)
            return 2
        if args.baseline and "audio" not in SLOT_CAPABILITIES[args.composer]:
            print(f"ERROR: --composer {args.composer} (used as baseline) does not accept audio.",
                  file=sys.stderr)
            return 2

    if args.all:
        runs: list[RunResult] = []
        for label, cfg in ALL_CONFIGS:
            if cfg["mode"] == "baseline":
                run = run_baseline(question, cfg["slot"], audio_bytes, audio_media_type)
            else:
                run = run_bilateral(question, cfg["parser"], cfg["composer"],
                                    audio_bytes, audio_media_type)
            _print_run(run, show_ir=not args.no_ir)
            runs.append(run)
        _print_comparison_table(runs)
        return 0

    if args.baseline:
        run = run_baseline(question, args.composer, audio_bytes, audio_media_type)
    else:
        run = run_bilateral(question, args.parser, args.composer,
                            audio_bytes, audio_media_type)
    _print_run(run, show_ir=not args.no_ir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
