"""Module 1l — Asset-conditioned video OUTPUT (async).

Closes three cells the dispatcher previously refused: (image, video),
(audio, video), (video, video). One module, two paths:

  - Path A (input == image, --edit-mode auto|condition): the image is
    passed to the composer as a conditioning frame. Sora-2 takes it
    via `input_reference=`; Veo takes it via the top-level
    `image=genai_types.Image(...)` kwarg on `generate_videos()`. The
    parser still runs and contributes a video brief alongside.
  - Path B (input in {audio, video}, or --edit-mode generate): the
    asset never reaches the video generator. The parser observes the
    asset and emits a normal video brief; the composer renders from
    text alone.

Condition when you can, translate when you must. (For video, the
input image is a *conditioning signal*, not an edit target — Sora and
Veo treat it as a strong visual reference, often a first-frame anchor.
The word "edit" doesn't quite fit; "condition" does.)

Reuses 1j's async state machine — submit, poll, terminal state. The
`job_id:` line in stderr is preserved (dispatch.py's regex
extractor depends on it).

Parser is constrained by input modality: anthropic excluded entirely
(no audio/video input); openai excluded from video.

(video, video) is the most expensive cell in the matrix — Gemini
parser reads the full clip, then Veo renders new video. A 4-second
smoke test still costs ~$2 per cell; `--all` with a video asset is
genuinely a $10–$20 sweep. The `--yes-i-know-this-costs-money` flag
gates it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import sys
import time
import uuid
import base64
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent / "module_01d_modality"))
from assets import fetch as fetch_asset  # noqa: E402

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Slot tables — parser slots inherit 1c/1h's six; composer slots inherit 1j
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SLOTS: dict[str, tuple[str, str]] = {
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

VIDEO_COMPOSER_SLOTS: dict[str, tuple[str, str]] = {
    "openai-video":  ("openai_video", "sora-2"),
    "google-video":  ("google_video", "veo-3.0-generate-001"),
}

VIDEO_PRICING: dict[str, dict[str, float]] = {
    "sora-2": {"720p_per_second": 0.10, "1080p_per_second": 0.50},
    "veo-3.0-generate-001": {"per_second": 0.50},
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

JOB_COMPLETED = "completed"
JOB_FAILED = "failed"
JOB_REJECTED = "rejected"
TERMINAL_STATES = {JOB_COMPLETED, JOB_FAILED, JOB_REJECTED}


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

# Path A — input is an image; composer will use it as a conditioning
# frame. Brief is shaped around what the conditioning image already
# establishes vs what the video should add (motion, scene continuation).
PARSER_SYSTEM_CONDITION = """You are an INPUT PARSER for a two-stage video-generation pipeline.

The user has supplied an image AND a prompt. The downstream video
model will receive both — the image becomes a conditioning reference
(often a first-frame anchor). Your job is to write a CONDITIONING
BRIEF that tells the video model what the image establishes and what
the clip should add on top.

Output exactly these labeled sections, in order:

IMAGE_OBSERVED: what is in the source image — focal subject,
  composition, lighting, era. Be specific.

WHAT_THE_IMAGE_ESTABLISHES: the visual elements the model should
  inherit (subject identity, style, palette, mood).

CAMERA_MOTION: static / dolly / pan / tilt / tracking / handheld;
  shot type. Be specific — motion is what the clip adds beyond the
  still.

ACTION_AND_CONTINUATION: what should happen in the seconds after the
  conditioning frame. Subject motion, environmental motion, scene
  shift if any.

DURATION_SECONDS: integer. Most labs cap preview clips at 5–10s.

ASPECT_RATIO: 16:9 / 9:16 / 1:1.

NEGATIVE_PROMPTS: explicit "do not include" cues.

SAFETY_FLAGS: real named persons (especially if the conditioning image
  shows one), trademarked characters, sensitive content. If none,
  "none".

Don't over-specify motion — overly rigid camera direction degrades
output. Don't restate the image; trust the model to inherit it."""

# Path B — input is audio or video; composer can't accept it. Parser
# observes the asset and emits a 1j-shaped video brief.
PARSER_SYSTEM_TRANSLATE = """You are an INPUT PARSER for a two-stage video-generation pipeline.

The user has supplied an asset (audio or video) AND a prompt. The
downstream video generator CANNOT see or hear the asset — only your
brief. Observe the asset and translate what's relevant about it into
a video brief the generator can render from text alone.

Output exactly these labeled sections, in order:

ASSET_OBSERVATIONS: describe the asset's content in enough detail
  that someone who never saw or heard it could reason about it.
  Speakers, scene, mood, named entities, on-screen text or
  transcribed speech, key visual moments (for video input).

VISUAL_TRANSLATION: in one sentence — given those observations and
  the user's prompt, what video should be rendered?

SUBJECT_AND_COMPOSITION: focal subject, framing, foreground/background.

STYLE_AND_AESTHETIC: photographic / cinematic / animated /
  documentary. Mood.

LIGHTING_AND_COLOR: light source(s), warm vs cool, palette.

CAMERA_MOTION: static / dolly / pan / tilt / tracking / handheld;
  shot type.

DURATION_SECONDS: integer.

ASPECT_RATIO: 16:9 / 9:16 / 1:1.

NEGATIVE_PROMPTS: explicit "do not include" cues.

SAFETY_FLAGS: anything the policy filter is likely to refuse — real
  named persons (especially when described from audio), trademarked
  characters or logos. If none, "none".

Do not fabricate content the asset does not support. If the audio is
a podcast about taxes, the brief should not invent a beach."""


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
class VideoResult:
    provider: str
    model: str
    job_id: str | None
    terminal_state: str | None
    video_bytes: bytes | None
    mime_type: str | None
    duration_seconds: float | None
    submit_latency: float
    poll_latency: float
    cost_usd: float
    refusal_reason: str | None = None
    error: str | None = None

    @property
    def total_composer_latency(self) -> float:
        return self.submit_latency + self.poll_latency


@dataclass
class RunResult:
    label: str
    path: str            # "condition" or "translate"
    parser: ParserResult | None
    composer: VideoResult
    video_uri: str | None = None

    @property
    def total_cost(self) -> float:
        return (self.parser.cost_usd if self.parser else 0.0) + self.composer.cost_usd

    @property
    def total_latency(self) -> float:
        return ((self.parser.latency_seconds if self.parser else 0.0)
                + self.composer.total_composer_latency)

    @property
    def has_error(self) -> bool:
        return (bool(self.composer.error)
                or self.composer.terminal_state in {JOB_FAILED, JOB_REJECTED}
                or bool(self.parser and self.parser.error))


# ─────────────────────────────────────────────────────────────────────────────
# Parser dispatch — three labs, with optional asset input
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
# Async state machine — same backoff/poll shape as 1j
# ─────────────────────────────────────────────────────────────────────────────


def _backoff_intervals(initial: float = 2.0, factor: float = 1.5, cap: float = 15.0):
    delay = initial
    while True:
        yield min(delay, cap)
        delay *= factor


def _poll_until_terminal(check_status, *, timeout: float = 600.0) -> tuple[str, dict]:
    deadline = time.time() + timeout
    bo = _backoff_intervals()
    last_state = "(unknown)"
    while time.time() < deadline:
        state, payload = check_status()
        last_state = state
        norm = _normalize_state(state)
        if norm in TERMINAL_STATES:
            return norm, payload
        time.sleep(next(bo))
    raise TimeoutError(f"job did not reach terminal state within "
                       f"{timeout:.0f}s (last state: {last_state})")


def _normalize_state(raw: str) -> str:
    s = (raw or "").lower()
    if s in {"completed", "succeeded", "done", "success"}:
        return JOB_COMPLETED
    if s in {"failed", "error", "errored"}:
        return JOB_FAILED
    if "rejected" in s or "policy" in s or "blocked" in s or "safety" in s:
        return JOB_REJECTED
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Composer dispatch — Sora-2, with optional input_reference
# ─────────────────────────────────────────────────────────────────────────────


def _call_composer_openai(prompt: str, *,
                          duration_seconds: int, size: str, poll_timeout: float,
                          conditioning_image: tuple[bytes, str] | None = None) -> VideoResult:
    """Sora-2 — async submit/poll/fetch. If conditioning_image is given,
    pass it via input_reference= as a (filename, BytesIO, mime) tuple."""
    from openai import OpenAI
    client = OpenAI()

    create_kwargs: dict = {
        "model": "sora-2",
        "prompt": prompt,
        "size": size,
        "seconds": str(duration_seconds),
    }
    if conditioning_image is not None:
        img_bytes, mime = conditioning_image
        # Sora requires input_reference dimensions to exactly match the
        # requested video size (it treats it as an inpaint base, not a
        # generic visual reference). Resize defensively — warps aspect
        # ratio when source != target shape; callers wanting aspect
        # preservation should letterbox before submitting.
        target_w, target_h = (int(x) for x in size.split("x"))
        from PIL import Image as _PILImage
        src = _PILImage.open(io.BytesIO(img_bytes))
        if src.size != (target_w, target_h):
            print(f"[resized conditioning image: {src.size} → "
                  f"({target_w}, {target_h})]", file=sys.stderr)
            src = src.convert("RGB").resize(
                (target_w, target_h), _PILImage.LANCZOS,
            )
            buf = io.BytesIO()
            src.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            mime = "image/png"
        ext = (mime or "image/png").rsplit("/", 1)[-1]
        if ext == "jpeg":
            ext = "jpg"
        create_kwargs["input_reference"] = (
            f"input.{ext}", io.BytesIO(img_bytes), mime or "image/png",
        )

    t_submit = time.perf_counter()
    job = client.videos.create(**create_kwargs)
    submit_latency = time.perf_counter() - t_submit
    job_id = job.id

    def check():
        v = client.videos.retrieve(job_id)
        return getattr(v, "status", "unknown"), v

    t_poll = time.perf_counter()
    try:
        terminal, final_v = _poll_until_terminal(check, timeout=poll_timeout)
    except TimeoutError as e:
        return VideoResult(
            "openai_video", "sora-2", job_id, None, None, None, None,
            submit_latency, time.perf_counter() - t_poll, 0.0,
            error=f"TimeoutError: {e}",
        )
    poll_latency = time.perf_counter() - t_poll

    if terminal == JOB_REJECTED:
        return VideoResult(
            "openai_video", "sora-2", job_id, JOB_REJECTED, None, None, None,
            submit_latency, poll_latency, 0.0,
            refusal_reason=getattr(final_v, "error", None) or "content policy",
        )
    if terminal == JOB_FAILED:
        return VideoResult(
            "openai_video", "sora-2", job_id, JOB_FAILED, None, None, None,
            submit_latency, poll_latency, 0.0,
            error=str(getattr(final_v, "error", "video generation failed")),
        )

    content = client.videos.download_content(job_id, variant="video")
    video_bytes = content.read() if hasattr(content, "read") else bytes(content)
    is_1080p = size.startswith("1920")
    rate = (VIDEO_PRICING["sora-2"]["1080p_per_second"] if is_1080p
            else VIDEO_PRICING["sora-2"]["720p_per_second"])
    cost = rate * duration_seconds
    return VideoResult(
        "openai_video", "sora-2", job_id, JOB_COMPLETED,
        video_bytes, "video/mp4", float(duration_seconds),
        submit_latency, poll_latency, cost,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Composer dispatch — Veo, with optional image= conditioning
# ─────────────────────────────────────────────────────────────────────────────


def _call_composer_google(prompt: str, *,
                          duration_seconds: int, aspect_ratio: str,
                          poll_timeout: float,
                          conditioning_image: tuple[bytes, str] | None = None) -> VideoResult:
    from google import genai as genai_v2
    from google.genai import types as genai_types

    client = genai_v2.Client(api_key=os.environ["GOOGLE_API_KEY"])
    model = "veo-3.0-generate-001"

    generate_kwargs: dict = {
        "model": model,
        "prompt": prompt,
        "config": genai_types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
        ),
    }
    if conditioning_image is not None:
        img_bytes, mime = conditioning_image
        generate_kwargs["image"] = genai_types.Image(
            image_bytes=img_bytes, mime_type=mime or "image/png",
        )

    t_submit = time.perf_counter()
    operation = client.models.generate_videos(**generate_kwargs)
    submit_latency = time.perf_counter() - t_submit
    job_id = getattr(operation, "name", None) or "(unnamed-operation)"

    def check():
        nonlocal operation
        operation = client.operations.get(operation)
        if getattr(operation, "error", None):
            return "failed", operation
        if getattr(operation, "done", False):
            return "completed", operation
        return "in_progress", operation

    t_poll = time.perf_counter()
    try:
        terminal, final_op = _poll_until_terminal(check, timeout=poll_timeout)
    except TimeoutError as e:
        return VideoResult(
            "google_video", model, job_id, None, None, None, None,
            submit_latency, time.perf_counter() - t_poll, 0.0,
            error=f"TimeoutError: {e}",
        )
    poll_latency = time.perf_counter() - t_poll

    if terminal == JOB_REJECTED:
        return VideoResult(
            "google_video", model, job_id, JOB_REJECTED, None, None, None,
            submit_latency, poll_latency, 0.0,
            refusal_reason=str(getattr(final_op, "error", "content policy")),
        )
    if terminal == JOB_FAILED:
        return VideoResult(
            "google_video", model, job_id, JOB_FAILED, None, None, None,
            submit_latency, poll_latency, 0.0,
            error=str(getattr(final_op, "error", "video generation failed")),
        )

    response = getattr(final_op, "response", None)
    generated = getattr(response, "generated_videos", None) or []
    video_bytes: bytes | None = None
    if generated:
        v = generated[0].video
        video_bytes = getattr(v, "video_bytes", None)
        if video_bytes is None and hasattr(client.files, "download"):
            try:
                video_bytes = client.files.download(file=v)
            except Exception:
                video_bytes = None

    rate = VIDEO_PRICING[model]["per_second"]
    cost = rate * duration_seconds
    return VideoResult(
        "google_video", model, job_id, JOB_COMPLETED,
        video_bytes, "video/mp4", float(duration_seconds),
        submit_latency, poll_latency, cost,
    )


def call_video_composer(slot: str, prompt: str, *,
                        duration_seconds: int, size: str,
                        aspect_ratio: str, poll_timeout: float,
                        conditioning_image: tuple[bytes, str] | None) -> VideoResult:
    if slot not in VIDEO_COMPOSER_SLOTS:
        return VideoResult("unknown", slot, None, None, None, None, None,
                           0.0, 0.0, 0.0,
                           error=f"unknown video composer slot: {slot}")
    provider, model = VIDEO_COMPOSER_SLOTS[slot]
    try:
        if provider == "openai_video":
            return _call_composer_openai(
                prompt, duration_seconds=duration_seconds, size=size,
                poll_timeout=poll_timeout,
                conditioning_image=conditioning_image,
            )
        elif provider == "google_video":
            return _call_composer_google(
                prompt, duration_seconds=duration_seconds,
                aspect_ratio=aspect_ratio, poll_timeout=poll_timeout,
                conditioning_image=conditioning_image,
            )
    except Exception as e:
        return VideoResult(provider, model, None, None, None, None, None,
                           0.0, 0.0, 0.0,
                           error=f"{type(e).__name__}: {e}"[:200])
    raise RuntimeError(f"unknown video provider: {provider}")


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrators
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_path(input_modality: str, edit_mode: str) -> str:
    """auto: condition if image-in else translate. condition: error on
    non-image. generate: force translate even on image input."""
    if edit_mode == "generate":
        return "translate"
    if edit_mode == "condition":
        if input_modality != "image":
            raise ValueError(f"--edit-mode condition requires image input, got {input_modality}")
        return "condition"
    return "condition" if input_modality == "image" else "translate"


def run_bilateral(prompt: str, parser_slot: str, composer_slot: str, *,
                  asset_bytes: bytes | None,
                  asset_media_type: str | None,
                  input_modality: str,
                  edit_mode: str,
                  duration_seconds: int, size: str, aspect_ratio: str,
                  poll_timeout: float,
                  show_ir: bool = True) -> RunResult:
    path = _resolve_path(input_modality, edit_mode)
    parser_system = PARSER_SYSTEM_CONDITION if path == "condition" else PARSER_SYSTEM_TRANSLATE

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
            composer=VideoResult("(skipped)", "(skipped)", None, None,
                                 None, None, None, 0.0, 0.0, 0.0,
                                 error="skipped — parser failed"),
        )

    composer_prompt = prompt if not show_ir else f"{prompt}\n\n[BRIEF]\n{parser.text}"
    conditioning = ((asset_bytes, asset_media_type or "image/png")
                    if path == "condition" and asset_bytes is not None else None)
    composer = call_video_composer(
        composer_slot, composer_prompt,
        duration_seconds=duration_seconds, size=size,
        aspect_ratio=aspect_ratio, poll_timeout=poll_timeout,
        conditioning_image=conditioning,
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
                 duration_seconds: int, size: str, aspect_ratio: str,
                 poll_timeout: float) -> RunResult:
    """Composer-only — no parser stage. For path=condition, the asset
    still goes to the composer as input_reference / image=. For
    path=translate, the asset is discarded (no description = nothing to
    render)."""
    path = _resolve_path(input_modality, edit_mode)
    conditioning = ((asset_bytes, asset_media_type or "image/png")
                    if path == "condition" and asset_bytes is not None else None)
    composer = call_video_composer(
        composer_slot, prompt,
        duration_seconds=duration_seconds, size=size,
        aspect_ratio=aspect_ratio, poll_timeout=poll_timeout,
        conditioning_image=conditioning,
    )
    return RunResult(label=f"baseline {composer_slot} [{path}]",
                     path=path, parser=None, composer=composer)


def upload_video(run: RunResult, *, bucket: str = "harness-eng") -> RunResult:
    if run.composer.video_bytes is None:
        return run
    import boto3
    s3 = boto3.client("s3")
    ext = (run.composer.mime_type or "video/mp4").split("/")[-1]
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"outputs/videos/{ts}-{uuid.uuid4().hex[:8]}.{ext}"
    s3.put_object(
        Bucket=bucket, Key=key, Body=run.composer.video_bytes,
        ContentType=run.composer.mime_type or "video/mp4",
    )
    run.video_uri = f"s3://{bucket}/{key}"
    return run


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────


def _fmt_cost(usd: float) -> str:
    if usd >= 1.0:
        return f"${usd:,.2f}"
    if usd >= 0.01:
        return f"${usd:.4f}"
    return f"${usd:.6f}"


def _print_run(run: RunResult, *, show_ir: bool = True) -> None:
    err = sys.stderr
    print(f"\n=== {run.label} ===", file=err)

    if run.parser is not None:
        p = run.parser
        path_tag = "condition" if run.path == "condition" else "translate (asset→IR)"
        print(f"\n--- PARSER ({p.provider}/{p.model}) [path: {path_tag}] ---", file=err)
        if p.error:
            print(f"ERROR: {p.error}", file=err)
        else:
            if show_ir:
                print(p.text, file=err)
            print(f"[in={p.input_tokens} out={p.output_tokens} "
                  f"cost={_fmt_cost(p.cost_usd)} "
                  f"latency={p.latency_seconds:.2f}s]", file=err)

    c = run.composer
    print(f"\n--- COMPOSER ({c.provider}/{c.model}) ---", file=err)
    print(f"job_id: {c.job_id}", file=err)
    if c.error:
        print(f"ERROR: {c.error}", file=err)
    elif c.terminal_state == JOB_REJECTED:
        print(f"REFUSED (policy): {c.refusal_reason}", file=err)
    elif c.terminal_state == JOB_FAILED:
        print(f"FAILED: (no bytes returned)", file=err)
    else:
        bytes_str = f"{len(c.video_bytes):,} bytes" if c.video_bytes else "(no bytes)"
        print(f"[duration={c.duration_seconds}s {bytes_str} "
              f"mime={c.mime_type} cost={_fmt_cost(c.cost_usd)} "
              f"submit={c.submit_latency:.2f}s "
              f"poll={c.poll_latency:.2f}s]", file=err)

    if run.video_uri:
        print(f"\n--- VIDEO UPLOAD ---\nuri: {run.video_uri}", file=err)

    print(f"\n--- TOTAL ---\ncost:    {_fmt_cost(run.total_cost)}\n"
          f"latency: {run.total_latency:.2f}s", file=err)

    if run.video_uri:
        print(run.video_uri)


def _print_comparison_table(runs: list[RunResult]) -> None:
    err = sys.stderr
    print("\n=== COMPARISON ===", file=err)
    print(f"{'Configuration':<54} {'Path':>10} {'Cost':>10} "
          f"{'Latency':>9} {'State':>10}", file=err)
    print("-" * 96, file=err)
    for r in runs:
        state = (r.composer.terminal_state or "—") if r.composer else "—"
        flag = "  ⚠" if r.has_error else ""
        print(f"{r.label:<54} {r.path:>10} {_fmt_cost(r.total_cost):>10} "
              f"{r.total_latency:>7.2f}s {state:>10}{flag}", file=err)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _eligible_parsers(input_modality: str) -> list[str]:
    return [s for s, caps in SLOT_INPUT_CAPABILITIES.items()
            if input_modality in caps]


def _build_all_configs(input_modality: str) -> list[tuple[str, dict]]:
    configs: list[tuple[str, dict]] = []
    for c in VIDEO_COMPOSER_SLOTS:
        configs.append((f"baseline {c}", {"mode": "baseline", "composer": c}))
    for p in _eligible_parsers(input_modality):
        for c in VIDEO_COMPOSER_SLOTS:
            configs.append((f"bilateral {p} → {c}",
                            {"mode": "bilateral", "parser": p, "composer": c}))
    return configs


def _estimate_sweep_cost(configs: list[tuple[str, dict]], *,
                         duration_seconds: int, size: str) -> float:
    """Rough cost ceiling for --all. Ignores parser cost (rounding error)
    and assumes both labs charge their listed per-second rate."""
    is_1080p = size.startswith("1920")
    sora_rate = (VIDEO_PRICING["sora-2"]["1080p_per_second"] if is_1080p
                 else VIDEO_PRICING["sora-2"]["720p_per_second"])
    veo_rate = VIDEO_PRICING["veo-3.0-generate-001"]["per_second"]
    total = 0.0
    for _, cfg in configs:
        c = cfg["composer"]
        if c == "openai-video":
            total += sora_rate * duration_seconds
        elif c == "google-video":
            total += veo_rate * duration_seconds
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="Module 1l — asset-conditioned video output (async).")
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--parser",   choices=list(PARSER_SLOTS), default="google-deep")
    ap.add_argument("--composer", choices=list(VIDEO_COMPOSER_SLOTS), default="google-video")
    ap.add_argument("--asset", required=True,
                    help="asset URI (s3://, http(s)://, or local path). Modality auto-detected. "
                         "1l requires an asset by definition; for text-only video, use 1j.")
    ap.add_argument("--edit-mode", choices=["auto", "condition", "generate"], default="auto",
                    help="auto: condition when input is image, translate otherwise. "
                         "condition: force conditioning (errors on non-image input). "
                         "generate: force translate path (parser-IR → text→video).")
    ap.add_argument("--duration", type=int, default=4)
    ap.add_argument("--size", default="1280x720",
                    help="Sora size: 1280x720 (cheap) or 1920x1080 (5× cost)")
    ap.add_argument("--aspect-ratio", default="16:9")
    ap.add_argument("--poll-timeout", type=float, default=600.0)
    ap.add_argument("--baseline", action="store_true",
                    help="composer-only — no parser stage")
    ap.add_argument("--all", action="store_true",
                    help="run every legal (parser, composer) for the detected input modality")
    ap.add_argument("--yes-i-know-this-costs-money", action="store_true",
                    help="required for --all (video sweeps are easily $10–$20)")
    ap.add_argument("--no-ir", action="store_true",
                    help="hide parser IR from composer prompt and from stderr")
    ap.add_argument("--no-upload", action="store_true",
                    help="skip uploading rendered video to S3")
    args = ap.parse_args()

    if args.prompt:
        question = " ".join(args.prompt)
    elif not sys.stdin.isatty():
        question = sys.stdin.read().strip()
    else:
        ap.print_help()
        return 2

    print(f"[fetching asset: {args.asset}]", file=sys.stderr)
    asset_bytes, asset_media_type = fetch_asset(args.asset)
    input_modality = detect_input_modality(asset_media_type)
    print(f"[fetched: {len(asset_bytes)} bytes, media_type={asset_media_type}, "
          f"input_modality={input_modality}]", file=sys.stderr)

    def _process(run: RunResult) -> RunResult:
        return run if args.no_upload else upload_video(run)

    common_kwargs = dict(
        duration_seconds=args.duration, size=args.size,
        aspect_ratio=args.aspect_ratio, poll_timeout=args.poll_timeout,
    )

    if args.all:
        configs = _build_all_configs(input_modality)
        ceiling = _estimate_sweep_cost(configs, duration_seconds=args.duration, size=args.size)
        print(f"[--all sweep: {len(configs)} configurations, "
              f"estimated cost ceiling ~{_fmt_cost(ceiling)}]", file=sys.stderr)
        if not args.yes_i_know_this_costs_money:
            print("[--all requires --yes-i-know-this-costs-money — refusing]",
                  file=sys.stderr)
            return 2
        runs: list[RunResult] = []
        for label, cfg in configs:
            if cfg["mode"] == "baseline":
                run = run_baseline(question, cfg["composer"],
                                   asset_bytes=asset_bytes,
                                   asset_media_type=asset_media_type,
                                   input_modality=input_modality,
                                   edit_mode=args.edit_mode,
                                   **common_kwargs)
            else:
                run = run_bilateral(question, cfg["parser"], cfg["composer"],
                                    asset_bytes=asset_bytes,
                                    asset_media_type=asset_media_type,
                                    input_modality=input_modality,
                                    edit_mode=args.edit_mode,
                                    show_ir=not args.no_ir,
                                    **common_kwargs)
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
                           **common_kwargs)
    else:
        run = run_bilateral(question, args.parser, args.composer,
                            asset_bytes=asset_bytes,
                            asset_media_type=asset_media_type,
                            input_modality=input_modality,
                            edit_mode=args.edit_mode,
                            show_ir=not args.no_ir,
                            **common_kwargs)
    run = _process(run)
    _print_run(run, show_ir=not args.no_ir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
