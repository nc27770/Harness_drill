"""Module 1j — Bilateral with Video OUTPUT (async).

Video generation is the first place in the curriculum where the harness
must operate as a state machine, not a synchronous request/response. See
`docs/limbic-image-video-generative.md` §1.3, §4.3, and §6.

What 1j proves:

  - The bilateral pattern survives the modality jump from image to video:
    parser produces a structured IR, composer renders it.
  - The IR gains two video-specific fields (camera motion, duration);
    everything else (subject, composition, style, lighting, aspect
    ratio, negatives, safety) is shared with 1i. Image and video IRs
    are siblings — by design.
  - Async-job control flow is a first-class harness primitive:
    submit → poll → terminal state (completed | failed | rejected).
    Refusal is a TYPED OUTCOME, not an exception. (This is the
    precursor to LIMBIC's "decline to modulate" first-class routing.)
  - Cost arithmetic moves another order of magnitude. Text was
    micro-cents. Image was cents. Video is **dollars per clip**. The
    parser is a rounding error against the composer's bill — bilateral
    is essentially always net-positive on cost.

Composer side filtered to two labs:

  openai-video  → sora-2                        (async; submit / poll / fetch)
  google-video  → veo-3.0-generate-001      (async; LRO; submit / poll / fetch)
  Anthropic     → no video generation at all (cannot serve as composer)

Parser side reuses the six chat slots from 1c–1h.

Note on SDK surfaces: video-generation APIs are evolving. The submit and
poll calls below follow the SDK shapes documented at the time of writing,
but expect minor drift; both labs have moved field names and pagination
between minor versions. If your first run errors on the SDK call, check
the lab's current SDK reference, not the harness logic.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
import uuid
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Slot tables
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SLOTS: dict[str, tuple[str, str]] = {
    "anthropic-fast":   ("anthropic", "claude-haiku-4-5"),
    "anthropic-deep":   ("anthropic", "claude-sonnet-4-6"),
    "openai-fast":      ("openai",    "gpt-4o-mini"),
    "openai-deep":      ("openai",    "gpt-4o"),
    "google-fast":      ("google",    "gemini-2.5-flash"),
    "google-deep":      ("google",    "gemini-2.5-pro"),
}

VIDEO_COMPOSER_SLOTS: dict[str, tuple[str, str]] = {
    "openai-video":  ("openai_video", "sora-2"),
    "google-video":  ("google_video", "veo-3.0-generate-001"),
}

# Per-clip pricing in USD. These are headline numbers — actual billing
# depends on resolution, duration, and whether the lab promoted you to a
# different tier. Verify against each provider's pricing page before
# trusting these for telemetry. The point of having them at all is the
# *visceral feedback* — you should feel a video call is dollars, not
# millicents.
VIDEO_PRICING: dict[str, dict[str, float]] = {
    # Sora-2: roughly $0.10/s at 720p, $0.50/s at 1080p (rough order of
    # magnitude — pricing has been moving)
    "sora-2": {"720p_per_second": 0.10, "1080p_per_second": 0.50},
    # Veo: roughly $0.50/s for the preview tier at the time of writing
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


# ─────────────────────────────────────────────────────────────────────────────
# The video IR — sibling of the image IR, with two video-only fields
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SYSTEM = """You are an INPUT PARSER for a two-stage video-generation pipeline.

Your job is to read the user's prompt and produce a STRUCTURED VIDEO BRIEF
that an async video-generation model will render. You are NOT generating
the video — you are writing the brief.

Output exactly these labeled sections, in order:

SUBJECT_AND_COMPOSITION: what is in the frame, where, framing, point of
  view, foreground/background.

STYLE_AND_AESTHETIC: photographic / cinematic / animated / illustrated /
  documentary / etc. Era and mood (cinematic, intimate, surreal, gritty…).

LIGHTING_AND_COLOR: light source(s), warm vs cool, soft vs harsh, palette.

CAMERA_MOTION: static / dolly / pan / tilt / tracking / crane / handheld;
  shot type (close-up, medium, wide, establishing). Be specific —
  motion is where video distinguishes itself from a still image.

DURATION_SECONDS: integer seconds. Most labs cap clips at 5–10 seconds
  for the preview tiers; if the user asks for more, normalize down to a
  feasible value and note the cap.

ASPECT_RATIO: 16:9 (landscape, default), 9:16 (vertical), 1:1 (square).

NEGATIVE_PROMPTS: explicit "do not include" cues.

SAFETY_FLAGS: anything the policy filter is likely to refuse — real
  named persons, trademarked characters or logos, sensitive content. If
  none, write "none". Video labs refuse at higher rates than text labs;
  a clear flag here prevents wasted minutes-long renders.

Be specific where it matters. Don't over-specify motion — overly rigid
camera direction often degrades output."""


# ─────────────────────────────────────────────────────────────────────────────
# Result types — the typed outcomes for an async pipeline
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


# Terminal states. Refusal is a first-class outcome — not an exception.
JOB_COMPLETED = "completed"
JOB_FAILED = "failed"
JOB_REJECTED = "rejected"   # content policy refusal
TERMINAL_STATES = {JOB_COMPLETED, JOB_FAILED, JOB_REJECTED}


@dataclass
class VideoResult:
    provider: str
    model: str
    job_id: str | None
    terminal_state: str | None      # "completed" | "failed" | "rejected"
    video_bytes: bytes | None
    mime_type: str | None
    duration_seconds: float | None
    submit_latency: float           # how long the submit call took
    poll_latency: float             # how long the poll loop took
    cost_usd: float
    refusal_reason: str | None = None
    error: str | None = None

    @property
    def total_composer_latency(self) -> float:
        return self.submit_latency + self.poll_latency


@dataclass
class RunResult:
    label: str
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
# Parser dispatch (text-side — same three-lab shape as 1c–1i)
# ─────────────────────────────────────────────────────────────────────────────


def _parser_cost(model: str, in_tok: int, out_tok: int) -> float:
    pi, po = PARSER_PRICING.get(model, (0.0, 0.0))
    return in_tok * pi / 1_000_000 + out_tok * po / 1_000_000


def _call_parser(slot: str, system: str, user_text: str,
                 max_tokens: int = 1024, temperature: float = 0.7) -> ParserResult:
    provider, model = PARSER_SLOTS[slot]
    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic()
            t0 = time.perf_counter()
            r = client.messages.create(
                model=model, max_tokens=max_tokens, temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user_text}],
            )
            dt_ = time.perf_counter() - t0
            text = "".join(b.text for b in r.content if b.type == "text")
            in_tok, out_tok = r.usage.input_tokens, r.usage.output_tokens
            return ParserResult(provider, model, text, in_tok, out_tok, dt_,
                                _parser_cost(model, in_tok, out_tok))
        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI()
            t0 = time.perf_counter()
            r = client.chat.completions.create(
                model=model, max_tokens=max_tokens, temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
            )
            dt_ = time.perf_counter() - t0
            text = r.choices[0].message.content or ""
            in_tok = r.usage.prompt_tokens
            out_tok = r.usage.completion_tokens
            return ParserResult(provider, model, text, in_tok, out_tok, dt_,
                                _parser_cost(model, in_tok, out_tok))
        elif provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
            m = genai.GenerativeModel(model, system_instruction=system)
            t0 = time.perf_counter()
            r = m.generate_content(
                user_text,
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
# Async job state machine — submit, poll, terminal
# ─────────────────────────────────────────────────────────────────────────────


def _backoff_intervals(initial: float = 2.0, factor: float = 1.5,
                       cap: float = 15.0):
    """Exponential backoff capped at `cap` seconds. Polite to lab quota,
    fast enough that 60-second renders aren't bottlenecked by the poll
    interval."""
    delay = initial
    while True:
        yield min(delay, cap)
        delay *= factor


def _poll_until_terminal(check_status, *, timeout: float = 600.0) -> tuple[str, dict]:
    """Drive an async job to a terminal state. `check_status` is a thunk
    that returns (state, payload). Returns (terminal_state, payload).
    Raises TimeoutError if the job doesn't terminate in `timeout` seconds.

    State strings expected from `check_status`:
      - in-flight: "queued", "in_progress", "running", "processing"
      - terminal: "completed" / "succeeded" / "done"
                  "failed" / "error"
                  "rejected" / "content_policy_violation"
    """
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
    return s   # in-flight states pass through


# ─────────────────────────────────────────────────────────────────────────────
# Composer dispatch — OpenAI Sora
# ─────────────────────────────────────────────────────────────────────────────


def _call_composer_openai(prompt: str, *, duration_seconds: int, size: str,
                          poll_timeout: float) -> VideoResult:
    """OpenAI Sora — async. Submit, poll, fetch.

    Pricing dial: 720p (`1280x720`) ~$0.10/s; 1080p (`1920x1080`) ~$0.50/s.
    Duration default 4 seconds keeps smoke tests at single-cents-to-dollars
    territory.
    """
    from openai import OpenAI
    client = OpenAI()

    t_submit = time.perf_counter()
    job = client.videos.create(
        model="sora-2",
        prompt=prompt,
        size=size,                       # "1280x720" or "1920x1080"
        seconds=str(duration_seconds),   # SDK accepts string seconds
    )
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

    # Completed — download the rendered bytes.
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
# Composer dispatch — Google Veo
# ─────────────────────────────────────────────────────────────────────────────


def _call_composer_google(prompt: str, *, duration_seconds: int,
                          aspect_ratio: str, poll_timeout: float) -> VideoResult:
    """Google Veo — async via long-running operation. Submit returns an
    Operation; poll until `.done` is True; pull the resulting URI/bytes.

    Veo's preview tier caps at ~8 seconds at the time of writing.
    """
    from google import genai as genai_v2
    from google.genai import types as genai_types

    client = genai_v2.Client(api_key=os.environ["GOOGLE_API_KEY"])
    model = "veo-3.0-generate-001"

    t_submit = time.perf_counter()
    operation = client.models.generate_videos(
        model=model,
        prompt=prompt,
        config=genai_types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,             # "16:9" / "9:16"
            duration_seconds=duration_seconds,
        ),
    )
    submit_latency = time.perf_counter() - t_submit
    job_id = getattr(operation, "name", None) or "(unnamed-operation)"

    def check():
        # Veo's Operation surface: refresh and read .done / .error / .response.
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

    # Completed — pull bytes from the response. Veo returns a list of
    # generated videos under operation.response.generated_videos[*].video,
    # each with a downloadable handle.
    response = getattr(final_op, "response", None)
    generated = getattr(response, "generated_videos", None) or []
    video_bytes: bytes | None = None
    if generated:
        v = generated[0].video
        # Newer SDKs expose video.video_bytes; older return a URI you fetch.
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
                        aspect_ratio: str, poll_timeout: float) -> VideoResult:
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
            )
        elif provider == "google_video":
            return _call_composer_google(
                prompt, duration_seconds=duration_seconds,
                aspect_ratio=aspect_ratio, poll_timeout=poll_timeout,
            )
    except Exception as e:
        return VideoResult(provider, model, None, None, None, None, None,
                           0.0, 0.0, 0.0,
                           error=f"{type(e).__name__}: {e}"[:200])
    raise RuntimeError(f"unknown video provider: {provider}")


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrators
# ─────────────────────────────────────────────────────────────────────────────


def run_bilateral(prompt: str, parser_slot: str, composer_slot: str, *,
                  duration_seconds: int, size: str, aspect_ratio: str,
                  poll_timeout: float) -> RunResult:
    parser = _call_parser(parser_slot, PARSER_SYSTEM, prompt)
    if parser.error:
        return RunResult(
            label=f"bilateral {parser_slot} → {composer_slot}",
            parser=parser,
            composer=VideoResult("(skipped)", "(skipped)", None, None,
                                 None, None, None, 0.0, 0.0, 0.0,
                                 error="skipped — parser failed"),
        )
    composer = call_video_composer(
        composer_slot, parser.text,
        duration_seconds=duration_seconds, size=size,
        aspect_ratio=aspect_ratio, poll_timeout=poll_timeout,
    )
    return RunResult(label=f"bilateral {parser_slot} → {composer_slot}",
                     parser=parser, composer=composer)


def run_baseline(prompt: str, composer_slot: str, *,
                 duration_seconds: int, size: str, aspect_ratio: str,
                 poll_timeout: float) -> RunResult:
    composer = call_video_composer(
        composer_slot, prompt,
        duration_seconds=duration_seconds, size=size,
        aspect_ratio=aspect_ratio, poll_timeout=poll_timeout,
    )
    return RunResult(label=f"baseline {composer_slot}",
                     parser=None, composer=composer)


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
# Reporting — cost formatter scales for dollars-per-clip
# ─────────────────────────────────────────────────────────────────────────────


def _fmt_cost(usd: float) -> str:
    """Cost formatter that survives the order-of-magnitude jump from
    text (micro-cents) to video (dollars). The visceral-feedback intent
    is preserved by always showing 4 significant digits at the working
    scale."""
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
        print(f"\n--- PARSER ({p.provider}/{p.model}) ---", file=err)
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
    print(f"{'Configuration':<48} {'Cost':>10} {'Latency':>9} {'State':>10}", file=err)
    print("-" * 82, file=err)
    for r in runs:
        state = (r.composer.terminal_state or "—") if r.composer else "—"
        flag = "  ⚠" if r.has_error else ""
        print(f"{r.label:<48} {_fmt_cost(r.total_cost):>10} "
              f"{r.total_latency:>7.2f}s {state:>10}{flag}", file=err)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _build_all_configs() -> list[tuple[str, dict]]:
    configs: list[tuple[str, dict]] = []
    for c in VIDEO_COMPOSER_SLOTS:
        configs.append((f"baseline {c}", {"mode": "baseline", "composer": c}))
    for p in PARSER_SLOTS:
        for c in VIDEO_COMPOSER_SLOTS:
            configs.append((f"bilateral {p} → {c}",
                            {"mode": "bilateral", "parser": p, "composer": c}))
    return configs


def main() -> int:
    ap = argparse.ArgumentParser(description="Module 1j — bilateral with video output (async).")
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--parser",   choices=list(PARSER_SLOTS), default="anthropic-deep",
                    help="parser slot (default: anthropic-deep)")
    ap.add_argument("--composer", choices=list(VIDEO_COMPOSER_SLOTS), default="openai-video",
                    help="video composer slot (default: openai-video)")
    ap.add_argument("--duration", type=int, default=4,
                    help="clip duration in seconds (default: 4 — keep smoke tests cheap)")
    ap.add_argument("--size", default="1280x720",
                    help="OpenAI Sora size: 1280x720 (cheap) or 1920x1080 (5× cost)")
    ap.add_argument("--aspect-ratio", default="16:9",
                    help="Google Veo aspect ratio (default: 16:9)")
    ap.add_argument("--poll-timeout", type=float, default=600.0,
                    help="max seconds to wait for the async job (default: 600)")
    ap.add_argument("--baseline", action="store_true",
                    help="single-call baseline using --composer (no parser stage)")
    ap.add_argument("--all", action="store_true",
                    help="run all 14 configurations: 2 baselines + 12 bilaterals "
                         "(WARNING: 14 × video cost — easily $20+)")
    ap.add_argument("--no-ir", action="store_true",
                    help="hide the parser's intermediate analysis from output")
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

    def _process(run: RunResult) -> RunResult:
        return run if args.no_upload else upload_video(run)

    common_kwargs = dict(
        duration_seconds=args.duration, size=args.size,
        aspect_ratio=args.aspect_ratio, poll_timeout=args.poll_timeout,
    )

    if args.all:
        runs: list[RunResult] = []
        for label, cfg in _build_all_configs():
            if cfg["mode"] == "baseline":
                run = run_baseline(question, cfg["composer"], **common_kwargs)
            else:
                run = run_bilateral(question, cfg["parser"], cfg["composer"], **common_kwargs)
            run = _process(run)
            _print_run(run, show_ir=not args.no_ir)
            runs.append(run)
        _print_comparison_table(runs)
        return 0

    if args.baseline:
        run = run_baseline(question, args.composer, **common_kwargs)
    else:
        run = run_bilateral(question, args.parser, args.composer, **common_kwargs)
    run = _process(run)
    _print_run(run, show_ir=not args.no_ir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
