"""Module 1h — Closing the Modality Matrix.

Modules 1d–1g instrumented 5 of 8 cells in the input × output modality
plane. Module 1h closes the remaining 3:

    (image,  audio)   "look at this and tell me out loud"
    (audio,  audio)   "respond to my speech with speech"
    (video,  audio)   "narrate this video"

After 1h, every (input modality, output modality) cell where at least
one valid (parser, composer) pair exists is reachable via the same
bilateral CLI. This is the smallest module that completes modality
coverage; the harness now spans every cell in the table the
README's Coverage Map describes.

Conceptually, 1h is the "compositional close" of the modality work:
nothing new at the adapter level — every line of provider-specific
serialization already exists in 1d/1e/1f/1g. What's new is:

  - **Two simultaneous capability matrices** (input AND output) consulted
    on every dispatch.
  - **Asset-type auto-detection** from the URI extension, so one CLI flag
    `--asset` accepts image, audio, OR video without the user telling
    the harness which is which.
  - **A larger curated `--all` set** that exercises all 3 newly-closed
    cells in one comparison run.

Read alongside 1d, 1e, 1f, 1g — the diff vs. each of them is small. 1h
is the consolidation, not a new primitive.
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

# What each slot can RECEIVE (input modalities).
SLOT_INPUT_CAPABILITIES: dict[str, set[str]] = {
    "anthropic-fast":   {"text", "image"},
    "anthropic-deep":   {"text", "image"},
    "openai-fast":      {"text", "image", "audio"},
    "openai-deep":      {"text", "image", "audio"},
    "google-fast":      {"text", "image", "audio", "video"},
    "google-deep":      {"text", "image", "audio", "video"},
}

# What each slot can EMIT (output modalities).
SLOT_OUTPUT_CAPABILITIES: dict[str, set[str]] = {
    "anthropic-fast":   {"text"},
    "anthropic-deep":   {"text"},
    "openai-fast":      {"text", "audio"},
    "openai-deep":      {"text", "audio"},
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
# Asset-type auto-detection from media type
# ─────────────────────────────────────────────────────────────────────────────


def detect_input_modality(media_type: str | None) -> str:
    """Map media type → input modality bucket. Defaults to 'text' for unknown."""
    if not media_type:
        return "text"
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("audio/"):
        return "audio"
    if media_type.startswith("video/"):
        return "video"
    return "text"


# ─────────────────────────────────────────────────────────────────────────────
# Prompts — composer told output may be spoken
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SYSTEM = """You are an INPUT PARSER for a two-stage LLM pipeline.

Your job is to read the user's question (and any attached image, audio, or
video) carefully and produce a compact STRUCTURED ANALYSIS for a
downstream COMPOSER model that will write the actual answer.

The COMPOSER may produce a SPOKEN answer (audio output), so favor
transcribable observations over visual layout descriptions where both
would convey the same fact.

Do NOT answer the question yourself. Output exactly these labeled
sections, in order:

LITERAL_QUESTION: one sentence — what is the user actually asking?
EXPECTED_ANSWER_SHAPE: format/length/tone. If audio output is expected,
  prefer short conversational sentences over lists or markdown.
DOMAIN: subject area(s).
SENSORY_OBSERVATIONS: if a visual or audio asset is attached, describe
  its contents in enough detail that a model who never sees/hears it can
  answer using your description alone. Include numbers, transcriptions,
  on-screen text, structural relationships. If no asset, write "no asset".
KEY_FACTS_OR_CONCEPTS: bullet list of facts the answer should incorporate.
AMBIGUITIES: anywhere the question or asset is unclear. If none, "none"."""

COMPOSER_SYSTEM_TEXT = """You are an OUTPUT COMPOSER in a two-stage LLM pipeline.

You will receive:
  1. The user's original question
  2. A parser's structured analysis (which may include observations from
     an asset the user attached — you do NOT receive the asset)

Use the parser's analysis to ground your response. Write your final
answer DIRECTLY TO THE USER. Do not refer to the parser, the analysis,
or the two-stage process."""

COMPOSER_SYSTEM_AUDIO = """You are an OUTPUT COMPOSER producing a SPOKEN answer.

You will receive:
  1. The user's original question
  2. A parser's structured analysis (which may include observations from
     an asset the user attached — you do NOT receive the asset)

Compose your reply so it sounds natural when spoken. Use short,
conversational sentences. Avoid markdown, bullet points, headers, or
formatting that doesn't translate to speech. Numbers spelled out where
clarity benefits.

The user will hear your output as audio. Speak directly to them."""


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
    audio_out: bytes | None = None
    audio_format: str | None = None
    error: str | None = None


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    pi, po = PRICING.get(model, (0.0, 0.0))
    return in_tok * pi / 1_000_000 + out_tok * po / 1_000_000


# ─────────────────────────────────────────────────────────────────────────────
# Adapters — same shapes as 1d/1e/1f/1g, now consolidated
# ─────────────────────────────────────────────────────────────────────────────


def _audio_format_for_openai(mt: str | None) -> str:
    return {
        "audio/mpeg": "mp3", "audio/mp3": "mp3",
        "audio/wav": "wav", "audio/x-wav": "wav",
        "audio/mp4": "m4a", "audio/ogg": "ogg", "audio/flac": "flac",
    }.get(mt or "", "mp3")


def _call_anthropic(
    model: str, system: str, user_text: str,
    asset_bytes: bytes | None, asset_media_type: str | None, asset_modality: str,
    audio_out: bool, voice: str, audio_format: str,
    max_tokens: int, temperature: float,
) -> CallResult:
    if asset_modality not in {"text", "image"}:
        raise NotImplementedError(f"Anthropic does not accept {asset_modality} input.")
    if audio_out:
        raise NotImplementedError("Anthropic does not emit audio in messages.create.")

    import anthropic
    client = anthropic.Anthropic()
    content_blocks: list[dict] = []
    if asset_modality == "image" and asset_bytes is not None:
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": asset_media_type or "image/png",
                "data": base64.b64encode(asset_bytes).decode("ascii"),
            },
        })
    content_blocks.append({"type": "text", "text": user_text})

    request: dict = {
        "model": model, "max_tokens": max_tokens, "temperature": temperature,
        "messages": [{"role": "user", "content": content_blocks}],
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
    asset_bytes: bytes | None, asset_media_type: str | None, asset_modality: str,
    audio_out: bool, voice: str, audio_format: str,
    max_tokens: int, temperature: float,
) -> CallResult:
    if asset_modality == "video":
        raise NotImplementedError("OpenAI chat.completions does not accept video input.")

    from openai import OpenAI
    client = OpenAI()

    effective_model = model
    user_parts: list[dict] = []

    if asset_modality == "image" and asset_bytes is not None:
        b64 = base64.b64encode(asset_bytes).decode("ascii")
        user_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{asset_media_type or 'image/png'};base64,{b64}"},
        })
    elif asset_modality == "audio" and asset_bytes is not None:
        effective_model = OPENAI_AUDIO_MODELS.get(model, model)
        user_parts.append({
            "type": "input_audio",
            "input_audio": {
                "data": base64.b64encode(asset_bytes).decode("ascii"),
                "format": _audio_format_for_openai(asset_media_type),
            },
        })

    user_parts.append({"type": "text", "text": user_text})

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_parts})

    request: dict = {
        "model": effective_model, "max_tokens": max_tokens,
        "temperature": temperature, "messages": messages,
    }
    if audio_out:
        # If we already rewrote to an audio-preview model for input audio, keep it.
        # Otherwise rewrite now for audio output. Either way, the audio-preview
        # variant handles both directions.
        effective_model = OPENAI_AUDIO_MODELS.get(model, effective_model)
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
    asset_bytes: bytes | None, asset_media_type: str | None, asset_modality: str,
    audio_out: bool, voice: str, audio_format: str,
    max_tokens: int, temperature: float,
) -> CallResult:
    if audio_out:
        raise NotImplementedError("Gemini chat does not emit audio.")
    if asset_modality == "video" and asset_bytes and len(asset_bytes) > 20 * 1024 * 1024:
        return CallResult(
            "google", model, "", 0, 0, 0, 0.0, 0.0,
            error=f"video too large for inline ({len(asset_bytes)} bytes); "
                  f"use genai.upload_file() — out of scope",
        )

    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    m = genai.GenerativeModel(model, system_instruction=system or None)

    parts: list = []
    if asset_modality in {"image", "audio", "video"} and asset_bytes is not None:
        parts.append({"mime_type": asset_media_type or "application/octet-stream",
                      "data": asset_bytes})
    parts.append(user_text)

    t0 = time.perf_counter()
    r = m.generate_content(
        parts,
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
         asset_bytes: bytes | None = None, asset_media_type: str | None = None,
         asset_modality: str = "text",
         audio_out: bool = False, voice: str = "alloy", audio_format: str = "mp3",
         max_tokens: int = 4096, temperature: float = 0.0) -> CallResult:
    provider, model = SLOTS[slot]
    in_caps = SLOT_INPUT_CAPABILITIES[slot]
    out_caps = SLOT_OUTPUT_CAPABILITIES[slot]

    if asset_modality not in in_caps:
        return CallResult(
            provider, model, "", 0, 0, 0, 0.0, 0.0,
            error=f"slot {slot} does not accept {asset_modality} input "
                  f"(supports: {sorted(in_caps)})",
        )
    if audio_out and "audio" not in out_caps:
        return CallResult(
            provider, model, "", 0, 0, 0, 0.0, 0.0,
            error=f"slot {slot} cannot emit audio "
                  f"(supports: {sorted(out_caps)})",
        )
    try:
        return _DISPATCH[provider](
            model, system, user_text,
            asset_bytes, asset_media_type, asset_modality,
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
    audio_uri: str | None = None
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
                  asset_bytes: bytes | None, asset_media_type: str | None,
                  asset_modality: str,
                  audio_out: bool, voice: str, audio_format: str) -> RunResult:
    parser = call(
        parser_slot, system=PARSER_SYSTEM, user_text=prompt,
        asset_bytes=asset_bytes, asset_media_type=asset_media_type,
        asset_modality=asset_modality,
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
    composer = call(
        composer_slot,
        system=COMPOSER_SYSTEM_AUDIO if audio_out else COMPOSER_SYSTEM_TEXT,
        user_text=composer_input,
        audio_out=audio_out, voice=voice, audio_format=audio_format,
    )
    suffix = " (audio_out)" if audio_out else ""
    return RunResult(label=f"bilateral {parser_slot} → {composer_slot}{suffix}",
                     parser=parser, composer=composer)


def run_baseline(prompt: str, slot: str,
                 asset_bytes: bytes | None, asset_media_type: str | None,
                 asset_modality: str,
                 audio_out: bool, voice: str, audio_format: str) -> RunResult:
    composer = call(
        slot, system="", user_text=prompt,
        asset_bytes=asset_bytes, asset_media_type=asset_media_type,
        asset_modality=asset_modality,
        audio_out=audio_out, voice=voice, audio_format=audio_format,
    )
    suffix = " (audio_out)" if audio_out else ""
    return RunResult(label=f"baseline {slot}{suffix}", parser=None, composer=composer)


def upload_audio_output(run: RunResult, *, bucket: str = "harness-eng") -> RunResult:
    if run.composer.audio_out is None:
        return run
    import boto3
    s3 = boto3.client("s3")
    fmt = run.composer.audio_format or "mp3"
    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    key = f"outputs/{ts}-{uuid.uuid4().hex[:8]}.{fmt}"
    s3.put_object(
        Bucket=bucket, Key=key, Body=run.composer.audio_out,
        ContentType=f"audio/{'mpeg' if fmt == 'mp3' else fmt}",
    )
    run.audio_uri = f"s3://{bucket}/{key}"
    return run


# ─────────────────────────────────────────────────────────────────────────────
# Reporting (same shape as 1g)
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
        modality = " [audio]" if c.audio_out else ""
        extra = ""
        if c.output_tokens != c.visible_output_tokens:
            extra = f" (visible={c.visible_output_tokens}, +thinking={c.output_tokens - c.visible_output_tokens})"
        print(f"[in={c.input_tokens} out={c.output_tokens}{extra}{modality} "
              f"cost=${c.cost_usd:.6f} latency={c.latency_seconds:.2f}s]", file=err)

    if run.audio_uri:
        print(f"\n--- AUDIO UPLOAD ---\nuri:     {run.audio_uri}", file=err)

    print(f"\n--- TOTAL ---\ntokens:  in={run.total_in_tokens}  out={run.total_out_tokens}\n"
          f"cost:    ${run.total_cost:.6f}\nlatency: {run.total_latency:.2f}s", file=err)
    if run.composer.text:
        print(run.composer.text)


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
# CLI — dynamic --all configs depending on detected input modality
# ─────────────────────────────────────────────────────────────────────────────


def _build_all_configs(input_modality: str, audio_out: bool) -> list[tuple[str, dict]]:
    """Curate a sensible --all set given the (input_modality, audio_out) cell."""
    valid_parsers = [s for s, caps in SLOT_INPUT_CAPABILITIES.items()
                     if input_modality in caps]
    valid_composers = [s for s, caps in SLOT_OUTPUT_CAPABILITIES.items()
                       if (("audio" in caps) if audio_out else ("text" in caps))]

    configs: list[tuple[str, dict]] = []

    # Baselines: slot must support BOTH input and output.
    for s in valid_parsers:
        if s in valid_composers:
            configs.append((f"baseline {s}{' (audio_out)' if audio_out else ''}",
                            {"mode": "baseline", "slot": s}))

    # Bilateral: every (valid_parser, valid_composer) pair where parser != composer
    # if parsers and composers are the same set (avoid same-slot bilateral redundancy
    # when there is no asymmetric tier or provider lift).
    for p in valid_parsers:
        for c in valid_composers:
            # Same-slot bilateral is pure overhead — skip.
            if p == c:
                continue
            configs.append((
                f"bilateral {p} → {c}{' (audio_out)' if audio_out else ''}",
                {"mode": "bilateral", "parser": p, "composer": c},
            ))

    return configs


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Module 1h — bilateral across all input modalities, optional audio output.",
    )
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--asset", default=None,
                    help="asset URI (s3://, http(s)://, or local path). Modality auto-detected.")
    ap.add_argument("--audio-out", action="store_true",
                    help="emit audio output (composer must support it)")
    ap.add_argument("--voice", default="alloy",
                    help="OpenAI voice when --audio-out (default: alloy)")
    ap.add_argument("--audio-format", default="mp3", choices=["mp3", "wav"],
                    help="output audio format (default: mp3)")
    ap.add_argument("--parser",   choices=list(SLOTS), default=None,
                    help="parser slot (default: chosen by modality)")
    ap.add_argument("--composer", choices=list(SLOTS), default=None,
                    help="composer slot (default: chosen by output modality)")
    ap.add_argument("--baseline", action="store_true",
                    help="single-call baseline using --composer's slot")
    ap.add_argument("--all", action="store_true",
                    help="run all valid (capability-filtered) configurations for the detected cell")
    ap.add_argument("--no-ir", action="store_true",
                    help="hide the parser's intermediate analysis from output")
    ap.add_argument("--no-upload", action="store_true",
                    help="skip uploading audio outputs to S3")
    args = ap.parse_args()

    if args.prompt:
        question = " ".join(args.prompt)
    elif not sys.stdin.isatty():
        question = sys.stdin.read().strip()
    else:
        ap.print_help()
        return 2

    # Fetch asset and detect modality.
    asset_bytes: bytes | None = None
    asset_media_type: str | None = None
    asset_modality = "text"
    if args.asset:
        print(f"[fetching asset: {args.asset}]", file=sys.stderr)
        asset_bytes, asset_media_type = fetch_asset(args.asset)
        asset_modality = detect_input_modality(asset_media_type)
        print(f"[fetched: {len(asset_bytes)} bytes, media_type={asset_media_type}, "
              f"modality={asset_modality}]", file=sys.stderr)

    # Default slot picks if user didn't specify.
    if args.parser is None:
        # Pick a fast, capable parser.
        for s in ("google-fast", "openai-fast", "anthropic-fast"):
            if asset_modality in SLOT_INPUT_CAPABILITIES[s]:
                args.parser = s
                break
    if args.composer is None:
        args.composer = "openai-deep" if args.audio_out else "anthropic-deep"

    def _process(run: RunResult) -> RunResult:
        if not args.no_upload:
            return upload_audio_output(run)
        return run

    if args.all:
        configs = _build_all_configs(asset_modality, args.audio_out)
        if not configs:
            print(f"ERROR: no valid configurations for cell "
                  f"({asset_modality}, {'audio' if args.audio_out else 'text'})",
                  file=sys.stderr)
            return 2
        runs: list[RunResult] = []
        for label, cfg in configs:
            if cfg["mode"] == "baseline":
                run = run_baseline(question, cfg["slot"],
                                   asset_bytes, asset_media_type, asset_modality,
                                   args.audio_out, args.voice, args.audio_format)
            else:
                run = run_bilateral(question, cfg["parser"], cfg["composer"],
                                    asset_bytes, asset_media_type, asset_modality,
                                    args.audio_out, args.voice, args.audio_format)
            run = _process(run)
            _print_run(run, show_ir=not args.no_ir)
            runs.append(run)
        _print_comparison_table(runs)
        return 0

    if args.baseline:
        run = run_baseline(question, args.composer,
                           asset_bytes, asset_media_type, asset_modality,
                           args.audio_out, args.voice, args.audio_format)
    else:
        run = run_bilateral(question, args.parser, args.composer,
                            asset_bytes, asset_media_type, asset_modality,
                            args.audio_out, args.voice, args.audio_format)
    run = _process(run)
    _print_run(run, show_ir=not args.no_ir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
