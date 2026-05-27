"""Module 1k — Asset-conditioned image OUTPUT.

Closes three cells the dispatcher previously refused: (image, image),
(audio, image), (video, image). One module, two paths:

  - Path A (input == image, --edit-mode auto|edit): the image goes to
    the composer's edit endpoint (gpt-image-1 `images.edit`, or Gemini
    in-context image edit). Parser still runs, producing an
    EDIT-shaped brief — what to keep, what to change.
  - Path B (input in {audio, video}, or --edit-mode generate): the
    asset never reaches the image generator. The parser observes the
    asset and emits a normal image brief; the composer renders from
    that brief, text-only. This is a translation lesson — the parser
    is doing modality conversion, not the composer.

Edit when you can, translate when you must. The choice is a function
of the input modality, not of the composer slot — gpt-image-1 and
Gemini both serve as either edit or generate composer.

Parser is constrained by input modality (anthropic excluded from
audio/video; openai excluded from video). Composer is image-only
(openai-image, google-image — same slots as 1i).
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent / "module_01d_modality"))
from assets import fetch as fetch_asset  # noqa: E402

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Slot tables — parser slots inherit 1c/1h's six; composer slots inherit 1i
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SLOTS: dict[str, tuple[str, str]] = {
    "anthropic-fast":   ("anthropic", "claude-haiku-4-5"),
    "anthropic-deep":   ("anthropic", "claude-sonnet-4-6"),
    "openai-fast":      ("openai",    "gpt-4o-mini"),
    "openai-deep":      ("openai",    "gpt-4o"),
    "google-fast":      ("google",    "gemini-2.5-flash"),
    "google-deep":      ("google",    "gemini-2.5-pro"),
}

# What each parser slot can RECEIVE on the input side. Mirrors 1h.
SLOT_INPUT_CAPABILITIES: dict[str, set[str]] = {
    "anthropic-fast":   {"text", "image"},
    "anthropic-deep":   {"text", "image"},
    "openai-fast":      {"text", "image", "audio"},
    "openai-deep":      {"text", "image", "audio"},
    "google-fast":      {"text", "image", "audio", "video"},
    "google-deep":      {"text", "image", "audio", "video"},
}

IMAGE_COMPOSER_SLOTS: dict[str, tuple[str, str]] = {
    "openai-image":  ("openai_image", "gpt-image-1"),
    "google-image":  ("google_image", "gemini-2.5-flash-image"),
}

# Reused verbatim from 1i (per design Q6 — same per-image rates for edit
# and generate; the lesson is structural, not billing fidelity).
IMAGE_PRICING: dict[str, dict[str, float]] = {
    "gpt-image-1": {"low": 0.011, "medium": 0.042, "high": 0.167},
    "gemini-2.5-flash-image": {"standard": 0.039},
}

PARSER_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5":  (1.00,  5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "gpt-4o-mini":       (0.15,  0.60),
    "gpt-4o":            (2.50, 10.00),
    "gemini-2.5-flash":  (0.30,  2.50),
    "gemini-2.5-pro":    (1.25, 10.00),
}

OPENAI_AUDIO_MODELS: dict[str, str] = {
    "gpt-4o":      "gpt-4o-audio-preview",
    "gpt-4o-mini": "gpt-4o-mini-audio-preview",
}


# ─────────────────────────────────────────────────────────────────────────────
# Modality detection
# ─────────────────────────────────────────────────────────────────────────────


def detect_input_modality(media_type: str | None) -> str:
    if not media_type:
        return "text"
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("audio/"):
        return "audio"
    if media_type.startswith("video/"):
        return "video"
    return "text"


def _audio_format_for_openai(mt: str | None) -> str:
    return {
        "audio/mpeg": "mp3", "audio/mp3": "mp3",
        "audio/wav": "wav", "audio/x-wav": "wav",
        "audio/mp4": "m4a", "audio/ogg": "ogg", "audio/flac": "flac",
    }.get(mt or "", "mp3")


# ─────────────────────────────────────────────────────────────────────────────
# Parser system prompts — one per path
# ─────────────────────────────────────────────────────────────────────────────

# Path A — input is an image, composer will run the EDIT endpoint. The
# brief is shaped around what to keep vs change.
PARSER_SYSTEM_EDIT = """You are an INPUT PARSER for a two-stage image-EDIT pipeline.

The user has supplied an image AND a prompt. A downstream image-edit
model will receive both. Your job is to write an EDIT BRIEF that the
edit model will take alongside the original image.

Output exactly these labeled sections, in order:

SUBJECT_OBSERVED: what is in the source image — focal subject,
  background, composition, distinctive details. Be specific.

INTENT: in one sentence, what does the user want done to this image?

WHAT_TO_PRESERVE: aspects of the original that must remain (subject
  identity, composition, color palette, era, etc.).

WHAT_TO_CHANGE: explicit edits — additions, removals, substitutions,
  stylistic shifts. Be concrete.

NEGATIVE_PROMPTS: explicit "do not" cues for the edit model.

SAFETY_FLAGS: anything the policy filter is likely to refuse — real
  named persons, trademarked characters or logos, removal of
  watermarks/credits. If none, write "none".

Be specific where the prompt is concrete and conservative where it is
vague — edit models over-edit when given license."""

# Path B — input is audio or video, composer cannot accept it. Parser
# observes the asset and emits a normal image brief (1i-shaped).
PARSER_SYSTEM_TRANSLATE = """You are an INPUT PARSER for a two-stage image-generation pipeline.

The user has supplied an asset (audio or video) AND a prompt. The
downstream image generator CANNOT see or hear the asset — only your
brief. Observe the asset and translate what's relevant about it into a
visual brief the generator can render from text alone.

Output exactly these labeled sections, in order:

ASSET_OBSERVATIONS: describe the asset's content in enough detail that
  someone who never saw or heard it could reason about it. Speakers,
  scene, mood, named entities, on-screen text or transcribed speech.

VISUAL_TRANSLATION: in one sentence — given those observations and the
  user's prompt, what image should be rendered?

SUBJECT_AND_COMPOSITION: focal subject, framing, foreground/background.

STYLE_AND_AESTHETIC: photographic / illustrated / painted / 3D /
  collage / abstract. Mood.

LIGHTING_AND_COLOR: light source(s), warm vs cool, soft vs harsh.

ASPECT_RATIO: 1:1, 16:9, 9:16, 4:5. Match the subject.

NEGATIVE_PROMPTS: explicit "do not include" cues.

SAFETY_FLAGS: anything the policy filter is likely to refuse — real
  named persons (especially when described from audio), trademarked
  characters or logos. If none, write "none".

Do not fabricate visual details the asset does not support. If the
audio is a podcast about taxes, the brief should not invent a beach."""


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ParserResult:
    provider: str
    model: str
    text: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    cost_usd: float
    error: str | None = None


@dataclass
class ImageResult:
    provider: str
    model: str
    image_bytes: bytes | None
    mime_type: str | None
    width: int | None
    height: int | None
    latency_seconds: float
    cost_usd: float
    revised_prompt: str | None = None
    error: str | None = None


@dataclass
class RunResult:
    label: str
    path: str            # "edit" or "translate"
    parser: ParserResult | None
    composer: ImageResult
    image_uri: str | None = None

    @property
    def total_cost(self) -> float:
        return (self.parser.cost_usd if self.parser else 0.0) + self.composer.cost_usd

    @property
    def total_latency(self) -> float:
        return (self.parser.latency_seconds if self.parser else 0.0) + self.composer.latency_seconds

    @property
    def has_error(self) -> bool:
        return bool(self.composer.error) or bool(self.parser and self.parser.error)


# ─────────────────────────────────────────────────────────────────────────────
# Parser dispatch — same shape as 1h's call(), but image-brief output
# ─────────────────────────────────────────────────────────────────────────────


def _parser_cost(model: str, in_tok: int, out_tok: int) -> float:
    pi, po = PARSER_PRICING.get(model, (0.0, 0.0))
    return in_tok * pi / 1_000_000 + out_tok * po / 1_000_000


def _call_parser(slot: str, system: str, user_text: str, *,
                 asset_bytes: bytes | None = None,
                 asset_media_type: str | None = None,
                 asset_modality: str = "text",
                 max_tokens: int = 1024,
                 temperature: float = 0.5) -> ParserResult:
    """Three-lab parser dispatch with optional asset input. Mirrors 1h's
    call() for the asset-handling pieces but always returns text (no
    audio output). Capability gate up front."""
    provider, model = PARSER_SLOTS[slot]
    if asset_modality not in SLOT_INPUT_CAPABILITIES[slot]:
        return ParserResult(provider, model, "", 0, 0, 0.0, 0.0,
                            error=f"slot {slot} does not accept {asset_modality} input "
                                  f"(supports: {sorted(SLOT_INPUT_CAPABILITIES[slot])})")
    try:
        if provider == "anthropic":
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
            t0 = time.perf_counter()
            r = client.messages.create(
                model=model, max_tokens=max_tokens, temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": content_blocks}],
            )
            dt_ = time.perf_counter() - t0
            text = "".join(b.text for b in r.content if b.type == "text")
            in_tok, out_tok = r.usage.input_tokens, r.usage.output_tokens
            return ParserResult(provider, model, text, in_tok, out_tok, dt_,
                                _parser_cost(model, in_tok, out_tok))

        elif provider == "openai":
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
            t0 = time.perf_counter()
            r = client.chat.completions.create(
                model=effective_model, max_tokens=max_tokens, temperature=temperature,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user_parts}],
            )
            dt_ = time.perf_counter() - t0
            text = r.choices[0].message.content or ""
            in_tok = r.usage.prompt_tokens
            out_tok = r.usage.completion_tokens
            return ParserResult(provider, effective_model, text, in_tok, out_tok, dt_,
                                _parser_cost(effective_model, in_tok, out_tok))

        elif provider == "google":
            if asset_modality == "video" and asset_bytes and len(asset_bytes) > 20 * 1024 * 1024:
                return ParserResult(provider, model, "", 0, 0, 0.0, 0.0,
                                    error=f"video too large for inline ({len(asset_bytes)} bytes); "
                                          f"use genai.upload_file() — out of scope")
            import google.generativeai as genai
            genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
            m = genai.GenerativeModel(model, system_instruction=system)
            parts: list = []
            if asset_modality in {"image", "audio", "video"} and asset_bytes is not None:
                parts.append({"mime_type": asset_media_type or "application/octet-stream",
                              "data": asset_bytes})
            parts.append(user_text)
            t0 = time.perf_counter()
            r = m.generate_content(
                parts,
                generation_config={"max_output_tokens": max_tokens,
                                   "temperature": temperature},
            )
            dt_ = time.perf_counter() - t0
            try:
                text = r.text or ""
            except (ValueError, AttributeError):
                text = ""
            um = r.usage_metadata
            in_tok = um.prompt_token_count
            out_tok = max(um.total_token_count - in_tok, um.candidates_token_count)
            return ParserResult(provider, model, text, in_tok, out_tok, dt_,
                                _parser_cost(model, in_tok, out_tok))
    except Exception as e:
        return ParserResult(provider, model, "", 0, 0, 0.0, 0.0,
                            error=f"{type(e).__name__}: {e}"[:200])
    raise RuntimeError(f"unknown provider: {provider}")


# ─────────────────────────────────────────────────────────────────────────────
# Composer dispatch — Path A (edit) and Path B (generate)
# ─────────────────────────────────────────────────────────────────────────────


def _call_composer_openai_generate(prompt: str, *, size: str, quality: str) -> ImageResult:
    """Path B / 1i-style — text-only image generation."""
    from openai import OpenAI
    client = OpenAI()
    t0 = time.perf_counter()
    r = client.images.generate(
        model="gpt-image-1", prompt=prompt, size=size, quality=quality, n=1,
    )
    dt_ = time.perf_counter() - t0
    item = r.data[0]
    image_bytes = base64.b64decode(item.b64_json) if item.b64_json else None
    revised = getattr(item, "revised_prompt", None)
    cost = IMAGE_PRICING["gpt-image-1"].get(quality, 0.042)
    width, height = (int(x) for x in size.split("x"))
    return ImageResult("openai_image", "gpt-image-1",
                       image_bytes, "image/png", width, height,
                       dt_, cost, revised_prompt=revised)


def _call_composer_openai_edit(prompt: str, *,
                               image_bytes: bytes, mime_type: str,
                               size: str, quality: str) -> ImageResult:
    """Path A — gpt-image-1 edit endpoint. The image is sent as a file-like
    tuple `(filename, BytesIO, content_type)`."""
    from openai import OpenAI
    client = OpenAI()
    ext = (mime_type or "image/png").rsplit("/", 1)[-1]
    if ext == "jpeg":
        ext = "jpg"
    file_tuple = (f"input.{ext}", io.BytesIO(image_bytes), mime_type or "image/png")
    t0 = time.perf_counter()
    r = client.images.edit(
        model="gpt-image-1", image=file_tuple, prompt=prompt,
        size=size, quality=quality, n=1,
    )
    dt_ = time.perf_counter() - t0
    item = r.data[0]
    out_bytes = base64.b64decode(item.b64_json) if item.b64_json else None
    revised = getattr(item, "revised_prompt", None)
    cost = IMAGE_PRICING["gpt-image-1"].get(quality, 0.042)
    width, height = (int(x) for x in size.split("x"))
    return ImageResult("openai_image", "gpt-image-1",
                       out_bytes, "image/png", width, height,
                       dt_, cost, revised_prompt=revised)


def _call_composer_google_generate(prompt: str, *, aspect_ratio: str | None) -> ImageResult:
    """Path B — Gemini image gen, text-only."""
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    m = genai.GenerativeModel("gemini-2.5-flash-image")
    full_prompt = prompt if not aspect_ratio else f"{prompt}\n\n(aspect ratio: {aspect_ratio})"
    t0 = time.perf_counter()
    r = m.generate_content(full_prompt)
    dt_ = time.perf_counter() - t0
    image_bytes, mime = _extract_inline_image(r)
    cost = IMAGE_PRICING["gemini-2.5-flash-image"]["standard"]
    return ImageResult("google_image", "gemini-2.5-flash-image",
                       image_bytes, mime, None, None, dt_, cost)


def _call_composer_google_edit(prompt: str, *,
                               image_bytes: bytes, mime_type: str,
                               aspect_ratio: str | None) -> ImageResult:
    """Path A — Gemini image model in-context edit. The asset goes into
    the parts list alongside the text prompt; the model interprets the
    pair as edit-on-image."""
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    m = genai.GenerativeModel("gemini-2.5-flash-image")
    full_prompt = prompt if not aspect_ratio else f"{prompt}\n\n(aspect ratio: {aspect_ratio})"
    parts = [
        {"mime_type": mime_type or "image/png", "data": image_bytes},
        full_prompt,
    ]
    t0 = time.perf_counter()
    r = m.generate_content(parts)
    dt_ = time.perf_counter() - t0
    out_bytes, out_mime = _extract_inline_image(r)
    cost = IMAGE_PRICING["gemini-2.5-flash-image"]["standard"]
    return ImageResult("google_image", "gemini-2.5-flash-image",
                       out_bytes, out_mime, None, None, dt_, cost)


def _extract_inline_image(r) -> tuple[bytes | None, str | None]:
    for part in (r.candidates[0].content.parts if r.candidates else []):
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            return inline.data, (inline.mime_type or "image/png")
    return None, None


def call_image_composer(slot: str, prompt: str, *,
                        path: str,
                        image_bytes: bytes | None,
                        mime_type: str | None,
                        size: str,
                        quality: str,
                        aspect_ratio: str | None) -> ImageResult:
    if slot not in IMAGE_COMPOSER_SLOTS:
        return ImageResult("unknown", slot, None, None, None, None, 0.0, 0.0,
                           error=f"unknown image composer slot: {slot}")
    provider, model = IMAGE_COMPOSER_SLOTS[slot]
    try:
        if path == "edit":
            if image_bytes is None:
                return ImageResult(provider, model, None, None, None, None, 0.0, 0.0,
                                   error="path=edit requires image_bytes")
            if provider == "openai_image":
                return _call_composer_openai_edit(prompt, image_bytes=image_bytes,
                                                  mime_type=mime_type or "image/png",
                                                  size=size, quality=quality)
            if provider == "google_image":
                return _call_composer_google_edit(prompt, image_bytes=image_bytes,
                                                  mime_type=mime_type or "image/png",
                                                  aspect_ratio=aspect_ratio)
        else:  # path == "translate" → text-only generate
            if provider == "openai_image":
                return _call_composer_openai_generate(prompt, size=size, quality=quality)
            if provider == "google_image":
                return _call_composer_google_generate(prompt, aspect_ratio=aspect_ratio)
    except Exception as e:
        return ImageResult(provider, model, None, None, None, None, 0.0, 0.0,
                           error=f"{type(e).__name__}: {e}"[:200])
    raise RuntimeError(f"unknown image provider: {provider}")


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrators
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_path(input_modality: str, edit_mode: str) -> str:
    """auto: edit if image-in else translate. edit: error on non-image.
    generate: force translate even on image-in."""
    if edit_mode == "generate":
        return "translate"
    if edit_mode == "edit":
        if input_modality != "image":
            raise ValueError(f"--edit-mode edit requires image input, got {input_modality}")
        return "edit"
    return "edit" if input_modality == "image" else "translate"


def run_bilateral(prompt: str, parser_slot: str, composer_slot: str, *,
                  asset_bytes: bytes | None,
                  asset_media_type: str | None,
                  input_modality: str,
                  edit_mode: str,
                  size: str, quality: str,
                  aspect_ratio: str | None,
                  show_ir: bool = True) -> RunResult:
    path = _resolve_path(input_modality, edit_mode)
    parser_system = PARSER_SYSTEM_EDIT if path == "edit" else PARSER_SYSTEM_TRANSLATE

    parser = _call_parser(
        parser_slot, parser_system, prompt,
        asset_bytes=asset_bytes if input_modality != "text" else None,
        asset_media_type=asset_media_type,
        asset_modality=input_modality,
    )
    if parser.error:
        return RunResult(
            label=f"bilateral {parser_slot} → {composer_slot} [{path}]",
            path=path, parser=parser,
            composer=ImageResult("(skipped)", "(skipped)", None, None, None, None,
                                 0.0, 0.0, error="skipped — parser failed"),
        )

    # Composer prompt = original user prompt + parser IR (so the edit
    # endpoint sees both intent and structured guidance).
    composer_prompt = prompt if not show_ir else f"{prompt}\n\n[BRIEF]\n{parser.text}"
    composer = call_image_composer(
        composer_slot, composer_prompt,
        path=path,
        image_bytes=asset_bytes if path == "edit" else None,
        mime_type=asset_media_type if path == "edit" else None,
        size=size, quality=quality, aspect_ratio=aspect_ratio,
    )
    return RunResult(
        label=f"bilateral {parser_slot} → {composer_slot} [{path}]",
        path=path, parser=parser, composer=composer,
    )


def run_baseline(prompt: str, composer_slot: str, *,
                 asset_bytes: bytes | None,
                 asset_media_type: str | None,
                 input_modality: str,
                 edit_mode: str,
                 size: str, quality: str,
                 aspect_ratio: str | None) -> RunResult:
    """Composer-only — no parser stage. For path=edit, the asset still
    goes to the edit endpoint with the user's raw prompt. For
    path=translate, this is composer-only text-to-image (the asset is
    discarded — there's no way to compose without a description)."""
    path = _resolve_path(input_modality, edit_mode)
    composer = call_image_composer(
        composer_slot, prompt,
        path=path,
        image_bytes=asset_bytes if path == "edit" else None,
        mime_type=asset_media_type if path == "edit" else None,
        size=size, quality=quality, aspect_ratio=aspect_ratio,
    )
    return RunResult(label=f"baseline {composer_slot} [{path}]",
                     path=path, parser=None, composer=composer)


def upload_image(run: RunResult, *, bucket: str = "harness-eng") -> RunResult:
    if run.composer.image_bytes is None:
        return run
    import boto3
    s3 = boto3.client("s3")
    ext = (run.composer.mime_type or "image/png").split("/")[-1]
    if ext == "jpeg":
        ext = "jpg"
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"outputs/images/{ts}-{uuid.uuid4().hex[:8]}.{ext}"
    s3.put_object(
        Bucket=bucket, Key=key, Body=run.composer.image_bytes,
        ContentType=run.composer.mime_type or "image/png",
    )
    run.image_uri = f"s3://{bucket}/{key}"
    return run


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────


def _print_run(run: RunResult, *, show_ir: bool = True) -> None:
    err = sys.stderr
    print(f"\n=== {run.label} ===", file=err)

    if run.parser is not None:
        p = run.parser
        path_tag = "edit" if run.path == "edit" else "translate (asset→IR)"
        print(f"\n--- PARSER ({p.provider}/{p.model}) [path: {path_tag}] ---", file=err)
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
        size_str = f"{c.width}x{c.height}" if c.width and c.height else "—"
        bytes_str = f"{len(c.image_bytes):,} bytes" if c.image_bytes else "(no bytes)"
        print(f"[size={size_str} {bytes_str} mime={c.mime_type} "
              f"cost=${c.cost_usd:.4f} latency={c.latency_seconds:.2f}s]", file=err)
        if c.revised_prompt:
            print(f"[provider rewrote prompt: {c.revised_prompt[:200]}…]", file=err)

    if run.image_uri:
        print(f"\n--- IMAGE UPLOAD ---\nuri:     {run.image_uri}", file=err)

    print(f"\n--- TOTAL ---\ncost:    ${run.total_cost:.4f}\n"
          f"latency: {run.total_latency:.2f}s", file=err)

    if run.image_uri:
        print(run.image_uri)


def _print_comparison_table(runs: list[RunResult]) -> None:
    err = sys.stderr
    print("\n=== COMPARISON ===", file=err)
    print(f"{'Configuration':<54} {'Path':>10} {'Cost':>10} {'Latency':>9}", file=err)
    print("-" * 86, file=err)
    for r in runs:
        flag = "  ⚠" if r.has_error else ""
        print(f"{r.label:<54} {r.path:>10} ${r.total_cost:>8.4f} "
              f"{r.total_latency:>7.2f}s{flag}", file=err)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _eligible_parsers(input_modality: str) -> list[str]:
    return [s for s, caps in SLOT_INPUT_CAPABILITIES.items()
            if input_modality in caps]


def _build_all_configs(input_modality: str) -> list[tuple[str, dict]]:
    configs: list[tuple[str, dict]] = []
    for c in IMAGE_COMPOSER_SLOTS:
        configs.append((f"baseline {c}", {"mode": "baseline", "composer": c}))
    for p in _eligible_parsers(input_modality):
        for c in IMAGE_COMPOSER_SLOTS:
            configs.append((f"bilateral {p} → {c}",
                            {"mode": "bilateral", "parser": p, "composer": c}))
    return configs


def main() -> int:
    ap = argparse.ArgumentParser(description="Module 1k — asset-conditioned image output.")
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--parser",   choices=list(PARSER_SLOTS), default="anthropic-deep")
    ap.add_argument("--composer", choices=list(IMAGE_COMPOSER_SLOTS), default="openai-image")
    ap.add_argument("--asset", default=None,
                    help="asset URI (s3://, http(s)://, or local path). Modality auto-detected.")
    ap.add_argument("--edit-mode", choices=["auto", "edit", "generate"], default="auto",
                    help="auto: edit when input is image, translate otherwise. "
                         "edit: force edit endpoint (errors on non-image input). "
                         "generate: force translate path (parser-IR → text→image).")
    ap.add_argument("--size", default="1024x1024")
    ap.add_argument("--quality", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--aspect-ratio", default=None)
    ap.add_argument("--baseline", action="store_true",
                    help="composer-only — no parser stage")
    ap.add_argument("--all", action="store_true",
                    help="run every legal (parser, composer) for the detected input modality")
    ap.add_argument("--no-ir", action="store_true",
                    help="hide parser IR from composer prompt and from stderr")
    ap.add_argument("--no-upload", action="store_true",
                    help="skip uploading rendered image to S3")
    args = ap.parse_args()

    if args.prompt:
        question = " ".join(args.prompt)
    elif not sys.stdin.isatty():
        question = sys.stdin.read().strip()
    else:
        ap.print_help()
        return 2

    asset_bytes: bytes | None = None
    asset_media_type: str | None = None
    input_modality = "text"
    if args.asset:
        print(f"[fetching asset: {args.asset}]", file=sys.stderr)
        asset_bytes, asset_media_type = fetch_asset(args.asset)
        input_modality = detect_input_modality(asset_media_type)
        print(f"[fetched: {len(asset_bytes)} bytes, media_type={asset_media_type}, "
              f"input_modality={input_modality}]", file=sys.stderr)

    def _process(run: RunResult) -> RunResult:
        return run if args.no_upload else upload_image(run)

    if args.all:
        runs: list[RunResult] = []
        for label, cfg in _build_all_configs(input_modality):
            if cfg["mode"] == "baseline":
                run = run_baseline(question, cfg["composer"],
                                   asset_bytes=asset_bytes,
                                   asset_media_type=asset_media_type,
                                   input_modality=input_modality,
                                   edit_mode=args.edit_mode,
                                   size=args.size, quality=args.quality,
                                   aspect_ratio=args.aspect_ratio)
            else:
                run = run_bilateral(question, cfg["parser"], cfg["composer"],
                                    asset_bytes=asset_bytes,
                                    asset_media_type=asset_media_type,
                                    input_modality=input_modality,
                                    edit_mode=args.edit_mode,
                                    size=args.size, quality=args.quality,
                                    aspect_ratio=args.aspect_ratio,
                                    show_ir=not args.no_ir)
            run = _process(run)
            _print_run(run, show_ir=not args.no_ir)
            runs.append(run)
        _print_comparison_table(runs)
        return 0

    if args.baseline:
        run = run_baseline(question, args.composer,
                           asset_bytes=asset_bytes,
                           asset_media_type=asset_media_type,
                           input_modality=input_modality,
                           edit_mode=args.edit_mode,
                           size=args.size, quality=args.quality,
                           aspect_ratio=args.aspect_ratio)
    else:
        run = run_bilateral(question, args.parser, args.composer,
                            asset_bytes=asset_bytes,
                            asset_media_type=asset_media_type,
                            input_modality=input_modality,
                            edit_mode=args.edit_mode,
                            size=args.size, quality=args.quality,
                            aspect_ratio=args.aspect_ratio,
                            show_ir=not args.no_ir)
    run = _process(run)
    _print_run(run, show_ir=not args.no_ir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
