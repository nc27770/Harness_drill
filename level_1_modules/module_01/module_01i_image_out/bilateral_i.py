"""Module 1i — Bilateral with Image OUTPUT.

The bilateral seam now bridges into a *different operator family* on the
composer side: not an autoregressive transformer, but a diffusion-transformer
stack co-trained alongside the labs' chat models. Same wire shape; different
machine on the other side. See `docs/limbic-image-video-generative.md` §1.1.

What this module proves:

  - The bilateral pattern still holds — parser produces a structured IR,
    composer renders it — when the composer's output is no longer text or
    audio but *pixels*.
  - The IR is **modality-shaped**, not generic. The image IR has fields
    (subject, composition, style, lighting, aspect ratio, negatives,
    safety flags) that don't make sense for prose. This is the first
    place in the curriculum where the parser's output schema is dictated
    by the *output modality*, not by an abstract "structured analysis."
  - Cost arithmetic *inverts*: in earlier modules, the bilateral parser
    was a meaningful share of total cost. Here the parser is a rounding
    error against the per-image generation cost. The Goldilocks math
    flips — bilateral is almost always cheap relative to baseline, and
    the question is whether it improves prompt adherence.

Composer side is heavily filtered:

  openai-image  → gpt-image-1                (sync, base64 in response)
  google-image  → gemini-2.5-flash-image     (sync, inline_data in response)
  Anthropic     → no image generation at all (cannot serve as composer)

Parser side is unconstrained (text-shaped lift, all six chat slots eligible).
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

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Slot tables — parser slots reuse 1c–1h's six; composer slots are new
# ─────────────────────────────────────────────────────────────────────────────

PARSER_SLOTS: dict[str, tuple[str, str]] = {
    "anthropic-fast":   ("anthropic", "claude-haiku-4-5"),
    "anthropic-deep":   ("anthropic", "claude-sonnet-4-6"),
    "openai-fast":      ("openai",    "gpt-4o-mini"),
    "openai-deep":      ("openai",    "gpt-4o"),
    "google-fast":      ("google",    "gemini-2.5-flash"),
    "google-deep":      ("google",    "gemini-2.5-pro"),
}

# Composer slots are a SEPARATE family — they are image generators, not chat
# models, and they live behind different endpoints with different pricing
# units (per image, not per token).
IMAGE_COMPOSER_SLOTS: dict[str, tuple[str, str]] = {
    "openai-image":  ("openai_image", "gpt-image-1"),
    "google-image":  ("google_image", "gemini-2.5-flash-image"),
}

# Per-call (image) pricing in USD. Verify against each provider's pricing
# page before relying — image pricing has historically drifted faster than
# text pricing because rendering economics shift with model and quality
# mode.
IMAGE_PRICING: dict[str, dict[str, float]] = {
    # gpt-image-1 (1024x1024) — three quality tiers
    "gpt-image-1": {"low": 0.011, "medium": 0.042, "high": 0.167},
    # gemini-2.5-flash-image — single tier, approximate
    "gemini-2.5-flash-image": {"standard": 0.039},
}

# Text-side pricing for the parser stage (unchanged from 1c–1h).
PARSER_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5":  (1.00,  5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "gpt-4o-mini":       (0.15,  0.60),
    "gpt-4o":            (2.50, 10.00),
    "gemini-2.5-flash":  (0.30,  2.50),
    "gemini-2.5-pro":    (1.25, 10.00),
}


# ─────────────────────────────────────────────────────────────────────────────
# Prompts — image IR is genuinely different from the text/audio IR
# ─────────────────────────────────────────────────────────────────────────────

# The parser's job is no longer to summarize the user's question into a
# generic "structured analysis". For an image generator, the parser is
# producing a SPEC — the kind of thing a creative director would hand to
# an illustrator. Schema reflects that.
PARSER_SYSTEM = """You are an INPUT PARSER for a two-stage image-generation pipeline.

Your job is to read the user's prompt and produce a STRUCTURED IMAGE BRIEF
that an image-generation model will render. You are NOT generating the
image yourself — you are writing the brief.

Output exactly these labeled sections, in order:

SUBJECT_AND_COMPOSITION: what is the focal subject, what surrounds it, and
  how is it framed? Foreground/background, spatial relationships, point of
  view.

STYLE_AND_AESTHETIC: photographic / illustrated / painted / 3D-rendered /
  collage / abstract / etc. Era and influences if relevant. Mood
  (cinematic, intimate, surreal, clinical, playful…).

LIGHTING_AND_COLOR: light source(s), warm vs cool, soft vs harsh, palette
  hints (e.g., "muted earth tones," "high-contrast neon," "sepia").

ASPECT_RATIO: 1:1 (square), 16:9 (landscape), 9:16 (portrait), 4:5, etc.
  Match the subject — don't force a ratio.

NEGATIVE_PROMPTS: explicit "do not include" cues. (e.g., "no text
  overlays," "no people in background," "no logos.")

SAFETY_FLAGS: anything the policy filter is likely to refuse — real
  named persons, trademarked characters or logos, sensitive content. If
  none, write "none". A clear flag here prevents wasted generations.

Be specific where it matters, vague where vagueness helps. Don't
over-constrain — image models are creative within constraints, and
over-specification often degrades output."""

# Composers don't see this prompt — they see only the parser's IR — but it's
# documented here for symmetry with the parser_system. The composer is the
# image generator itself; we don't pass a system prompt to it.


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ParserResult:
    provider: str
    model: str
    text: str            # the structured IR
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
    revised_prompt: str | None = None  # some providers return what they
                                       # actually used (rewritten)
    error: str | None = None


@dataclass
class RunResult:
    label: str
    parser: ParserResult | None
    composer: ImageResult
    image_uri: str | None = None       # set after upload to S3

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
# Parser dispatch (text-side — same shape as 1c, three labs)
# ─────────────────────────────────────────────────────────────────────────────


def _parser_cost(model: str, in_tok: int, out_tok: int) -> float:
    pi, po = PARSER_PRICING.get(model, (0.0, 0.0))
    return in_tok * pi / 1_000_000 + out_tok * po / 1_000_000


def _call_parser(slot: str, system: str, user_text: str,
                 max_tokens: int = 1024, temperature: float = 0.7) -> ParserResult:
    """Same three-lab dispatch as 1c. Image briefs benefit from a little
    creative slack (temperature=0.7 default) — exact reproducibility is
    less valuable than a richer brief on this stage."""
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
# Composer dispatch (image-side — different operators, different units)
# ─────────────────────────────────────────────────────────────────────────────


def _call_composer_openai(prompt: str, *, size: str, quality: str) -> ImageResult:
    """OpenAI gpt-image-1 — sync, returns base64 in response.data[0].b64_json.
    Quality dial: 'low' / 'medium' / 'high'. Pricing scales 16× across tiers."""
    from openai import OpenAI
    client = OpenAI()
    t0 = time.perf_counter()
    r = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,           # "1024x1024", "1024x1536", "1536x1024", "auto"
        quality=quality,     # "low", "medium", "high"
        n=1,
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


def _call_composer_google(prompt: str, *, aspect_ratio: str | None) -> ImageResult:
    """Google gemini-2.5-flash-image — sync, image returned inline in
    response.candidates[0].content.parts as inline_data with mime_type and
    raw bytes."""
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    m = genai.GenerativeModel("gemini-2.5-flash-image")
    t0 = time.perf_counter()
    # Aspect ratio control on Gemini's image model is currently expressed
    # via prompt hints rather than a dedicated parameter on most SDK
    # versions. We append it to the prompt as a soft cue.
    full_prompt = prompt
    if aspect_ratio:
        full_prompt = f"{prompt}\n\n(aspect ratio: {aspect_ratio})"
    r = m.generate_content(full_prompt)
    dt_ = time.perf_counter() - t0

    image_bytes: bytes | None = None
    mime: str | None = None
    for part in (r.candidates[0].content.parts if r.candidates else []):
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            image_bytes = inline.data
            mime = inline.mime_type or "image/png"
            break

    cost = IMAGE_PRICING["gemini-2.5-flash-image"]["standard"]
    return ImageResult("google_image", "gemini-2.5-flash-image",
                       image_bytes, mime, None, None, dt_, cost)


def call_image_composer(slot: str, prompt: str, *,
                         size: str = "1024x1024", quality: str = "low",
                         aspect_ratio: str | None = None) -> ImageResult:
    if slot not in IMAGE_COMPOSER_SLOTS:
        return ImageResult("unknown", slot, None, None, None, None, 0.0, 0.0,
                           error=f"unknown image composer slot: {slot}")
    provider, model = IMAGE_COMPOSER_SLOTS[slot]
    try:
        if provider == "openai_image":
            return _call_composer_openai(prompt, size=size, quality=quality)
        elif provider == "google_image":
            return _call_composer_google(prompt, aspect_ratio=aspect_ratio)
    except Exception as e:
        return ImageResult(provider, model, None, None, None, None, 0.0, 0.0,
                           error=f"{type(e).__name__}: {e}"[:200])
    raise RuntimeError(f"unknown image provider: {provider}")


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrators
# ─────────────────────────────────────────────────────────────────────────────


def run_bilateral(prompt: str, parser_slot: str, composer_slot: str, *,
                  size: str, quality: str, aspect_ratio: str | None) -> RunResult:
    parser = _call_parser(parser_slot, PARSER_SYSTEM, prompt)
    if parser.error:
        return RunResult(
            label=f"bilateral {parser_slot} → {composer_slot}",
            parser=parser,
            composer=ImageResult("(skipped)", "(skipped)", None, None, None, None,
                                 0.0, 0.0, error="skipped — parser failed"),
        )
    composer = call_image_composer(
        composer_slot, parser.text,
        size=size, quality=quality, aspect_ratio=aspect_ratio,
    )
    return RunResult(label=f"bilateral {parser_slot} → {composer_slot}",
                     parser=parser, composer=composer)


def run_baseline(prompt: str, composer_slot: str, *,
                 size: str, quality: str, aspect_ratio: str | None) -> RunResult:
    """Baseline = composer-only, with the user's raw prompt. No parser stage.
    This is the LIMBIC 'decline to modulate' route, made explicit for image-out."""
    composer = call_image_composer(
        composer_slot, prompt,
        size=size, quality=quality, aspect_ratio=aspect_ratio,
    )
    return RunResult(label=f"baseline {composer_slot}", parser=None, composer=composer)


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

    # stdout: the URI of the rendered image (pipe-friendly).
    if run.image_uri:
        print(run.image_uri)


def _print_comparison_table(runs: list[RunResult]) -> None:
    err = sys.stderr
    print("\n=== COMPARISON ===", file=err)
    print(f"{'Configuration':<48} {'Cost':>10} {'Latency':>9}", file=err)
    print("-" * 70, file=err)
    for r in runs:
        flag = "  ⚠" if r.has_error else ""
        print(f"{r.label:<48} ${r.total_cost:>8.4f} {r.total_latency:>7.2f}s{flag}",
              file=err)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _build_all_configs() -> list[tuple[str, dict]]:
    configs: list[tuple[str, dict]] = []
    # Two baselines (one per image composer)
    for c in IMAGE_COMPOSER_SLOTS:
        configs.append((f"baseline {c}", {"mode": "baseline", "composer": c}))
    # Bilateral: every parser × every image composer
    for p in PARSER_SLOTS:
        for c in IMAGE_COMPOSER_SLOTS:
            configs.append((f"bilateral {p} → {c}",
                            {"mode": "bilateral", "parser": p, "composer": c}))
    return configs


def main() -> int:
    ap = argparse.ArgumentParser(description="Module 1i — bilateral with image output.")
    ap.add_argument("prompt", nargs="*", help="The user prompt. If omitted, read stdin.")
    ap.add_argument("--parser",   choices=list(PARSER_SLOTS), default="anthropic-deep",
                    help="parser slot (default: anthropic-deep — strong creative-brief writer)")
    ap.add_argument("--composer", choices=list(IMAGE_COMPOSER_SLOTS), default="openai-image",
                    help="image composer slot (default: openai-image)")
    ap.add_argument("--size", default="1024x1024",
                    help="image size for OpenAI (default: 1024x1024)")
    ap.add_argument("--quality", default="low", choices=["low", "medium", "high"],
                    help="OpenAI quality dial (default: low — keeps smoke tests cheap)")
    ap.add_argument("--aspect-ratio", default=None,
                    help="aspect ratio for Google (passed via prompt hint)")
    ap.add_argument("--baseline", action="store_true",
                    help="single-call baseline using --composer (no parser stage)")
    ap.add_argument("--all", action="store_true",
                    help="run all 14 configurations: 2 baselines + 12 bilaterals")
    ap.add_argument("--no-ir", action="store_true",
                    help="hide the parser's intermediate analysis from output")
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

    def _process(run: RunResult) -> RunResult:
        return run if args.no_upload else upload_image(run)

    if args.all:
        runs: list[RunResult] = []
        for label, cfg in _build_all_configs():
            if cfg["mode"] == "baseline":
                run = run_baseline(question, cfg["composer"],
                                   size=args.size, quality=args.quality,
                                   aspect_ratio=args.aspect_ratio)
            else:
                run = run_bilateral(question, cfg["parser"], cfg["composer"],
                                    size=args.size, quality=args.quality,
                                    aspect_ratio=args.aspect_ratio)
            run = _process(run)
            _print_run(run, show_ir=not args.no_ir)
            runs.append(run)
        _print_comparison_table(runs)
        return 0

    if args.baseline:
        run = run_baseline(question, args.composer,
                           size=args.size, quality=args.quality,
                           aspect_ratio=args.aspect_ratio)
    else:
        run = run_bilateral(question, args.parser, args.composer,
                            size=args.size, quality=args.quality,
                            aspect_ratio=args.aspect_ratio)
    run = _process(run)
    _print_run(run, show_ir=not args.no_ir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
