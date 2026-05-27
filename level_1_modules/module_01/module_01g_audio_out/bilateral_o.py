"""Module 1g — Bilateral with Audio OUTPUT.

Modules 1d, 1e, and 1f all routed *input* modalities. Module 1g flips the
direction: the COMPOSER's output modality is what's routed. The user
attaches text (or no asset), but the composer must emit *audio* — and in
our 3-lab universe, only OpenAI's `gpt-4o-audio-preview` family can do
that in a single chat-completion call.

This is the symmetric counterpart to Module 1e: same single-modality
pressure, opposite direction. Together with 1d/1e/1f, the bilateral
pipeline is now parameterized on *both sides* of the read-act split:

  - Parser: any input modality routed to a capable provider
  - Composer: any output modality routed to a capable provider

The composer emits two things in one round trip: a base64-encoded audio
blob *and* the corresponding text transcript. We save the audio to S3
(because heavy data lives in S3, per the project storage convention) and
print the transcript + S3 URI for downstream use.

Read alongside `module_01e_audio/bilateral_a.py`. The diff is:
  - SLOT_OUTPUT_CAPABILITIES — new dict, separate from input capabilities.
  - The OpenAI adapter has an audio-output mode (modalities=["text",
    "audio"], audio={voice, format}); same audio-preview model rewriting.
  - CallResult carries audio_out bytes + format alongside text.
  - The orchestrator uploads audio output to s3://harness-eng/outputs/
    and surfaces the URI in the run result.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent / "module_01d_modality"))
from assets import fetch as fetch_asset  # noqa: E402

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Slot tables
# ─────────────────────────────────────────────────────────────────────────────

SLOTS: dict[str, tuple[str, str]] = {
    "anthropic-fast":   ("anthropic", "claude-haiku-4-5"),
    "anthropic-deep":   ("anthropic", "claude-sonnet-4-6"),
    "openai-fast":      ("openai",    "gpt-4o-mini"),
    "openai-deep":      ("openai",    "gpt-4o"),
    "google-fast":      ("google",    "gemini-2.5-flash"),
    "google-deep":      ("google",    "gemini-2.5-pro"),
}

SLOT_INPUT_CAPABILITIES: dict[str, set[str]] = {
    "anthropic-fast":   {"text", "image"},
    "anthropic-deep":   {"text", "image"},
    "openai-fast":      {"text", "image", "audio"},
    "openai-deep":      {"text", "image", "audio"},
    "google-fast":      {"text", "image", "audio", "video"},
    "google-deep":      {"text", "image", "audio", "video"},
}

# What each slot can EMIT. Only OpenAI's audio-preview models emit audio
# in chat.completions today. Gemini and Anthropic both have separate
# TTS-style models but they're not unified with the LLM endpoint.
SLOT_OUTPUT_CAPABILITIES: dict[str, set[str]] = {
    "anthropic-fast":   {"text"},
    "anthropic-deep":   {"text"},
    "openai-fast":      {"text", "audio"},  # via gpt-4o-mini-audio-preview
    "openai-deep":      {"text", "audio"},  # via gpt-4o-audio-preview
    "google-fast":      {"text"},
    "google-deep":      {"text"},
}

OPENAI_AUDIO_MODELS: dict[str, str] = {
    "gpt-4o":      "gpt-4o-audio-preview",
    "gpt-4o-mini": "gpt-4o-mini-audio-preview",
}

PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5":           (1.00,  5.00),
    "claude-sonnet-4-6":          (3.00, 15.00),
    "gpt-4o-mini":                (0.15,  0.60),
    "gpt-4o":                     (2.50, 10.00),
    "gpt-4o-mini-audio-preview":  (0.15,  0.60),
    "gpt-4o-audio-preview":       (2.50, 10.00),
    "gemini-2.5-flash":           (0.30,  2.50),
    "gemini-2.5-pro":             (1.25, 10.00),
}


# ─────────────────────────────────────────────────────────────────────────────
# Prompts — composer is told the answer will be SPOKEN
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SYSTEM = """You are an INPUT PARSER for a two-stage LLM pipeline.

The downstream COMPOSER will produce a SPOKEN answer (audio output), so
your analysis should account for that — short, conversational sentences;
no markdown, tables, or other visual formatting in the EXPECTED_ANSWER_SHAPE
section.

Output exactly these labeled sections, in order:

LITERAL_QUESTION: one sentence — what is the user actually asking?
EXPECTED_ANSWER_SHAPE: format/length/tone for SPOKEN delivery. Avoid lists,
  headers, bullet points — speech can't render those naturally.
DOMAIN: subject area(s).
KEY_FACTS_OR_CONCEPTS: bullet list of facts, numbers, definitions the
  spoken answer should incorporate.
AMBIGUITIES: anywhere the question is unclear. If none, write "none".

Do NOT answer the question yourself."""

COMPOSER_SYSTEM = """You are an OUTPUT COMPOSER producing a SPOKEN answer.

You will receive:
  1. The user's original question
  2. A parser's structured analysis

Compose your reply so it sounds natural when spoken aloud. Use short,
conversational sentences. Avoid markdown, bullet points, headers, or any
formatting that doesn't translate to speech. Numbers should be spelled
out where it improves clarity (e.g., "two point four million" rather than
"2.4M").

The user will hear your output as audio. Speak directly to them."""


# ─────────────────────────────────────────────────────────────────────────────
# CallResult — extended with audio_out
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CallResult:
    provider: str
    model: str
    text: str                       # transcript when audio_out is set
    input_tokens: int
    output_tokens: int
    visible_output_tokens: int
    latency_seconds: float
    cost_usd: float
    audio_out: bytes | None = None  # raw audio bytes if composer emitted audio
    audio_format: str | None = None # "mp3", "wav", etc.
    error: str | None = None


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    pi, po = PRICING.get(model, (0.0, 0.0))
    return in_tok * pi / 1_000_000 + out_tok * po / 1_000_000


# ─────────────────────────────────────────────────────────────────────────────
# Adapters — parser stays text-only; composer-side OpenAI gets audio mode
# ─────────────────────────────────────────────────────────────────────────────


def _call_anthropic(
    model: str, system: str, user_text: str,
    audio_out: bool, voice: str, audio_format: str,
    max_tokens: int, temperature: float,
) -> CallResult:
    if audio_out:
        raise NotImplementedError(
            "Anthropic does not emit audio output in messages.create. "
            "Route audio-output composers to openai-* slots."
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
    dt_ = time.perf_counter() - t0
    text = "".join(b.text for b in r.content if b.type == "text")
    in_tok, out_tok = r.usage.input_tokens, r.usage.output_tokens
    return CallResult("anthropic", model, text, in_tok, out_tok, out_tok, dt_,
                      _cost(model, in_tok, out_tok))


def _call_openai(
    model: str, system: str, user_text: str,
    audio_out: bool, voice: str, audio_format: str,
    max_tokens: int, temperature: float,
) -> CallResult:
    """OpenAI: when audio_out is True, request modalities=['text','audio']
    and an audio config; the response carries both message.audio.data
    (base64 audio) and message.audio.transcript (the spoken text)."""
    from openai import OpenAI
    client = OpenAI()

    effective_model = model
    request: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": ([{"role": "system", "content": system}] if system else [])
                    + [{"role": "user", "content": user_text}],
    }
    if audio_out:
        effective_model = OPENAI_AUDIO_MODELS.get(model, model)
        request["model"] = effective_model
        request["modalities"] = ["text", "audio"]
        request["audio"] = {"voice": voice, "format": audio_format}

    t0 = time.perf_counter()
    r = client.chat.completions.create(**request)
    dt_ = time.perf_counter() - t0

    msg = r.choices[0].message
    out_audio: bytes | None = None
    out_audio_format: str | None = None
    if audio_out and getattr(msg, "audio", None):
        out_audio = base64.b64decode(msg.audio.data)
        out_audio_format = audio_format
        text = msg.audio.transcript or ""
    else:
        text = msg.content or ""

    in_tok, out_tok = r.usage.prompt_tokens, r.usage.completion_tokens
    return CallResult(
        "openai", effective_model, text, in_tok, out_tok, out_tok, dt_,
        _cost(effective_model, in_tok, out_tok),
        audio_out=out_audio, audio_format=out_audio_format,
    )


def _call_google(
    model: str, system: str, user_text: str,
    audio_out: bool, voice: str, audio_format: str,
    max_tokens: int, temperature: float,
) -> CallResult:
    if audio_out:
        raise NotImplementedError(
            "Gemini's chat models do not emit audio in generate_content. "
            "Route audio-output composers to openai-* slots."
        )
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    m = genai.GenerativeModel(model, system_instruction=system or None)
    t0 = time.perf_counter()
    r = m.generate_content(
        user_text,
        generation_config={"max_output_tokens": max_tokens, "temperature": temperature},
    )
    dt_ = time.perf_counter() - t0
    try:
        text = r.text or ""
    except (ValueError, AttributeError):
        text = ""
    um = r.usage_metadata
    in_tok = um.prompt_token_count
    visible_out = um.candidates_token_count
    billable_out = max(um.total_token_count - in_tok, visible_out)
    return CallResult("google", model, text, in_tok, billable_out, visible_out, dt_,
                      _cost(model, in_tok, billable_out))


_DISPATCH = {
    "anthropic": _call_anthropic,
    "openai":    _call_openai,
    "google":    _call_google,
}


def call(slot: str, *, system: str, user_text: str,
         audio_out: bool = False, voice: str = "alloy", audio_format: str = "mp3",
         max_tokens: int = 2048, temperature: float = 0.0) -> CallResult:
    provider, model = SLOTS[slot]
    if audio_out and "audio" not in SLOT_OUTPUT_CAPABILITIES[slot]:
        return CallResult(
            provider, model, "", 0, 0, 0, 0.0, 0.0,
            error=f"slot {slot} cannot emit audio (output capabilities: "
                  f"{sorted(SLOT_OUTPUT_CAPABILITIES[slot])})",
        )
    try:
        return _DISPATCH[provider](
            model, system, user_text,
            audio_out, voice, audio_format,
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
    audio_uri: str | None = None    # set after upload to S3
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
                  audio_out: bool, voice: str, audio_format: str) -> RunResult:
    parser = call(parser_slot, system=PARSER_SYSTEM, user_text=prompt)
    if parser.error:
        return RunResult(
            label=f"bilateral {parser_slot} → {composer_slot} (audio_out)",
            parser=parser,
            composer=CallResult("(skipped)", "(skipped)", "", 0, 0, 0, 0.0, 0.0,
                                error="skipped — parser failed"),
        )
    composer_input = (
        f"USER'S ORIGINAL QUESTION:\n{prompt}\n\n"
        f"PARSER'S STRUCTURED ANALYSIS:\n{parser.text}"
    )
    composer = call(
        composer_slot, system=COMPOSER_SYSTEM, user_text=composer_input,
        audio_out=audio_out, voice=voice, audio_format=audio_format,
    )
    return RunResult(
        label=f"bilateral {parser_slot} → {composer_slot}" + (" (audio_out)" if audio_out else ""),
        parser=parser, composer=composer,
    )


def run_baseline(prompt: str, slot: str,
                 audio_out: bool, voice: str, audio_format: str) -> RunResult:
    composer = call(
        slot, system="", user_text=prompt,
        audio_out=audio_out, voice=voice, audio_format=audio_format,
    )
    return RunResult(label=f"baseline {slot}" + (" (audio_out)" if audio_out else ""),
                     parser=None, composer=composer)


def upload_audio_output(run: RunResult, *, bucket: str = "harness-eng") -> RunResult:
    """If the composer produced audio, upload to S3 and stamp run.audio_uri.
    Returns the same RunResult for chaining."""
    if run.composer.audio_out is None:
        return run
    import boto3
    s3 = boto3.client("s3")
    fmt = run.composer.audio_format or "mp3"
    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    key = f"outputs/{ts}-{uuid.uuid4().hex[:8]}.{fmt}"
    s3.put_object(
        Bucket=bucket, Key=key, Body=run.composer.audio_out,
        ContentType=f"audio/{ 'mpeg' if fmt == 'mp3' else fmt }",
    )
    run.audio_uri = f"s3://{bucket}/{key}"
    return run


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
            print(f"[in={p.input_tokens} out={p.output_tokens} "
                  f"cost=${p.cost_usd:.6f} latency={p.latency_seconds:.2f}s]", file=err)
    c = run.composer
    print(f"\n--- COMPOSER ({c.provider}/{c.model}) ---", file=err)
    if c.error:
        print(f"ERROR: {c.error}", file=err)
    else:
        modality = " [audio]" if c.audio_out else ""
        print(f"[in={c.input_tokens} out={c.output_tokens}{modality} "
              f"cost=${c.cost_usd:.6f} latency={c.latency_seconds:.2f}s]", file=err)
    if run.audio_uri:
        print(f"\n--- AUDIO UPLOAD ---\nuri:     {run.audio_uri}\n"
              f"play:    aws s3 cp {run.audio_uri} - | mpv -",
              file=err)
    print(f"\n--- TOTAL ---\ntokens:  in={run.total_in_tokens}  out={run.total_out_tokens}\n"
          f"cost:    ${run.total_cost:.6f}\nlatency: {run.total_latency:.2f}s", file=err)
    if run.composer.text:
        print(run.composer.text)  # this is the transcript when audio_out


def _print_comparison_table(runs: list[RunResult]) -> None:
    err = sys.stderr
    print("\n=== COMPARISON ===", file=err)
    print(f"{'Configuration':<58} {'In':>6} {'Out':>6} {'Cost':>10} {'Latency':>9}",
          file=err)
    print("-" * 94, file=err)
    for r in runs:
        flag = "  ⚠" if r.has_error else ""
        print(f"{r.label:<58} {r.total_in_tokens:>6} {r.total_out_tokens:>6} "
              f"${r.total_cost:>8.6f} {r.total_latency:>7.2f}s{flag}", file=err)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


# --all set: parsers vary across labs, composer is forced to an
# audio-capable slot. The parser side is where the bilateral split still
# delivers cross-provider value.
ALL_CONFIGS: list[tuple[str, dict]] = [
    # 2 baselines (only audio-capable slots can baseline)
    ("baseline openai-fast (audio_out)",         {"mode": "baseline", "slot": "openai-fast"}),
    ("baseline openai-deep (audio_out)",         {"mode": "baseline", "slot": "openai-deep"}),
    # 4 bilaterals — diverse parsers, openai-deep composer
    ("bilateral anthropic-fast → openai-deep",
        {"mode": "bilateral", "parser": "anthropic-fast", "composer": "openai-deep"}),
    ("bilateral anthropic-deep → openai-deep",
        {"mode": "bilateral", "parser": "anthropic-deep", "composer": "openai-deep"}),
    ("bilateral google-fast → openai-deep",
        {"mode": "bilateral", "parser": "google-fast",  "composer": "openai-deep"}),
    ("bilateral openai-fast → openai-deep",
        {"mode": "bilateral", "parser": "openai-fast",  "composer": "openai-deep"}),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Module 1g — bilateral with audio output.")
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--parser",   choices=list(SLOTS), default="anthropic-deep",
                    help="parser slot. Default: anthropic-deep (text-only IR is fine here)")
    ap.add_argument("--composer", choices=list(SLOTS), default="openai-deep",
                    help="composer slot. Must support audio output for --audio-out.")
    ap.add_argument("--audio-out", action="store_true", default=True,
                    help="emit audio output (default: True — that's the point of this module)")
    ap.add_argument("--no-audio-out", dest="audio_out", action="store_false",
                    help="emit text only — useful for parser-IR debugging")
    ap.add_argument("--voice", default="alloy",
                    help="OpenAI voice: alloy, echo, fable, onyx, nova, shimmer (default: alloy)")
    ap.add_argument("--audio-format", default="mp3", choices=["mp3", "wav"],
                    help="output audio format (default: mp3)")
    ap.add_argument("--baseline", action="store_true",
                    help="single-call baseline using --composer's slot")
    ap.add_argument("--all", action="store_true", help="run 6 curated configurations")
    ap.add_argument("--no-ir", action="store_true",
                    help="hide the parser's intermediate analysis from output")
    ap.add_argument("--no-upload", action="store_true",
                    help="skip uploading audio to S3; print byte counts only")
    args = ap.parse_args()

    if args.prompt:
        question = " ".join(args.prompt)
    elif not sys.stdin.isatty():
        question = sys.stdin.read().strip()
    else:
        ap.print_help()
        return 2

    if args.audio_out:
        target_slot = args.composer
        if "audio" not in SLOT_OUTPUT_CAPABILITIES[target_slot]:
            print(f"ERROR: --composer {target_slot} cannot emit audio. "
                  f"Use openai-fast or openai-deep.", file=sys.stderr)
            return 2

    def _process(run: RunResult) -> RunResult:
        if not args.no_upload:
            return upload_audio_output(run)
        return run

    if args.all:
        runs: list[RunResult] = []
        for label, cfg in ALL_CONFIGS:
            if cfg["mode"] == "baseline":
                run = run_baseline(question, cfg["slot"],
                                   args.audio_out, args.voice, args.audio_format)
            else:
                run = run_bilateral(question, cfg["parser"], cfg["composer"],
                                    args.audio_out, args.voice, args.audio_format)
            run = _process(run)
            _print_run(run, show_ir=not args.no_ir)
            runs.append(run)
        _print_comparison_table(runs)
        return 0

    if args.baseline:
        run = run_baseline(question, args.composer,
                           args.audio_out, args.voice, args.audio_format)
    else:
        run = run_bilateral(question, args.parser, args.composer,
                            args.audio_out, args.voice, args.audio_format)
    run = _process(run)
    _print_run(run, show_ir=not args.no_ir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
