"""Level-2 String 01 — Dispatch.

A cover application that composes the level-1 modules. Each module is a
self-contained CLI that teaches one thing at the seam; this dispatcher
routes a (input modality, output modality, parser, composer) request to
the right module's CLI and parses its output.

Curriculum-preserving by design: per-module files in level_1_modules/
are NOT modified. The dispatcher's job is *routing*, not
re-implementation. When LIMBIC v0 lands at L3.1, the policy that picks
parser/composer slots will plug in here; the plumbing stays the same.

Subprocess fan-out, not in-process import. Trade documented in the
README. Briefly: subprocess preserves the "each module is a lesson"
property and gives a debug-friendly invariant — you can always log the
exact CLI that was dispatched.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_BIN = str(REPO_ROOT / ".venv" / "bin" / "python")
MODULES_DIR = REPO_ROOT / "level_1_modules"


# ─────────────────────────────────────────────────────────────────────────────
# Capability matrices — what each slot can do on input and output sides.
# These mirror the per-module matrices in 1e/1g/1h/1i/1j; consolidated
# here so the UI can filter dropdowns without consulting nine files.
# ─────────────────────────────────────────────────────────────────────────────

ALL_PARSER_SLOTS = (
    "anthropic-fast", "anthropic-deep",
    "openai-fast",    "openai-deep",
    "google-fast",    "google-deep",
)

# Input modality → which parser slots can lift it.
PARSER_INPUT_CAPABILITY: dict[str, tuple[str, ...]] = {
    "text":  ALL_PARSER_SLOTS,
    "image": ALL_PARSER_SLOTS,        # all three labs read images
    "audio": ("openai-fast", "openai-deep",
              "google-fast", "google-deep"),   # Anthropic has no audio input
    "video": ("google-fast", "google-deep"),    # Gemini-only for video
}

# Output modality → which composer slots can produce it.
COMPOSER_OUTPUT_CAPABILITY: dict[str, tuple[str, ...]] = {
    "text":  ALL_PARSER_SLOTS,
    "audio": ("openai-fast", "openai-deep"),    # OpenAI audio-preview only
    "image": ("openai-image", "google-image"),  # Anthropic excluded
    "video": ("openai-video", "google-video"),  # Anthropic excluded
}

OUTPUT_MODALITIES = ("text", "audio", "image", "video")
INPUT_MODALITIES  = ("text", "image", "audio", "video")


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch table — (input, output) → (module file, CLI builder).
# Five module files cover the matrix; 1h consolidates 1d/1e/1f/1g.
# ─────────────────────────────────────────────────────────────────────────────


def _module(rel_path: str) -> str:
    return str(MODULES_DIR / rel_path)


@dataclass
class DispatchPlan:
    module_path: str
    argv: list[str]
    label: str          # e.g. "1h (image,audio)"


def plan_dispatch(*,
                  prompt: str,
                  input_modality: str,
                  output_modality: str,
                  parser_slot: str,
                  composer_slot: str,
                  asset_uri: str | None = None,
                  # 1i knobs
                  image_quality: str = "low",
                  # 1j knobs
                  video_duration: int = 4,
                  video_size: str = "1280x720",
                  video_aspect: str = "16:9") -> DispatchPlan:
    """Pick the right module file and assemble its CLI."""

    # (text, text) → 1c bilateral_x.py — three labs, text-shaped IR
    if input_modality == "text" and output_modality == "text":
        path = _module("module_01c_bilateral_x/bilateral_x.py")
        argv = [PYTHON_BIN, path,
                "--parser", parser_slot, "--composer", composer_slot,
                prompt]
        return DispatchPlan(path, argv, f"1c (text,text)")

    # (any, text|audio) → 1h bilateral_h.py — consolidated
    if output_modality in ("text", "audio"):
        path = _module("module_01h_modality_matrix/bilateral_h.py")
        argv = [PYTHON_BIN, path,
                "--parser", parser_slot, "--composer", composer_slot]
        if asset_uri:
            argv += ["--asset", asset_uri]
        if output_modality == "audio":
            argv += ["--audio-out"]
        argv += [prompt]
        return DispatchPlan(path, argv, f"1h ({input_modality},{output_modality})")

    # (text, image) → 1i bilateral_i.py
    if input_modality == "text" and output_modality == "image":
        path = _module("module_01i_image_out/bilateral_i.py")
        argv = [PYTHON_BIN, path,
                "--parser", parser_slot, "--composer", composer_slot,
                "--quality", image_quality,
                prompt]
        return DispatchPlan(path, argv, "1i (text,image)")

    # (text, video) → 1j bilateral_j.py
    if input_modality == "text" and output_modality == "video":
        path = _module("module_01j_video_out/bilateral_j.py")
        argv = [PYTHON_BIN, path,
                "--parser", parser_slot, "--composer", composer_slot,
                "--duration", str(video_duration),
                "--size", video_size,
                "--aspect-ratio", video_aspect,
                prompt]
        return DispatchPlan(path, argv, "1j (text,video)")

    raise ValueError(f"no module covers ({input_modality}, {output_modality}); "
                     f"image-edit and image-to-video are deferred deferrals")


# ─────────────────────────────────────────────────────────────────────────────
# Run + parse — the subprocess invocation and stderr regex extraction
# ─────────────────────────────────────────────────────────────────────────────


COST_RX = re.compile(r"cost=\$([0-9.]+)")
LATENCY_RX = re.compile(r"latency=([0-9.]+)s")
COMPOSER_COST_RX = re.compile(r"cost=\$([0-9,.]+)")
JOB_ID_RX = re.compile(r"job_id:\s*(\S+)")


@dataclass
class DispatchResult:
    plan: DispatchPlan
    returncode: int
    stdout: str            # the asset URI or text answer (last line of stdout)
    full_stdout: str
    stderr: str
    parsed: dict           # extracted cost/latency/job_id/etc.
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "module": self.plan.label,
            "argv": self.plan.argv,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "parsed": self.parsed,
            "error": self.error,
        }


def _parse_stderr(stderr: str) -> dict:
    """Light extraction. The full stderr is preserved separately for the
    UI's trace panel; this is just the top-level fields the comparison
    table needs."""
    costs = [float(c.replace(",", "")) for c in COMPOSER_COST_RX.findall(stderr)]
    latencies = [float(x) for x in LATENCY_RX.findall(stderr)]
    job_ids = JOB_ID_RX.findall(stderr)
    return {
        "total_cost_usd": sum(costs) if costs else None,
        "stage_costs_usd": costs,
        "stage_latencies_s": latencies,
        "job_id": job_ids[0] if job_ids else None,
    }


def run_dispatch(plan: DispatchPlan, *,
                 timeout: float = 900.0,
                 env: dict | None = None) -> DispatchResult:
    """Invoke the planned module CLI. Captures stdout and stderr. Does
    NOT raise on non-zero exit — surfaces the error in the result so the
    UI can render it."""
    proc_env = dict(os.environ)
    if env:
        proc_env.update(env)

    try:
        cp = subprocess.run(
            plan.argv,
            cwd=str(REPO_ROOT),
            env=proc_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        return DispatchResult(plan, -1, "", "", "", {},
                              error=f"TimeoutExpired after {timeout:.0f}s")
    except Exception as e:
        return DispatchResult(plan, -1, "", "", "", {},
                              error=f"{type(e).__name__}: {e}")

    # Last non-empty line of stdout is the canonical result (URI for
    # asset modules, prose-tail for text-out). Full stdout is preserved.
    full_stdout = cp.stdout
    last_line = ""
    for ln in reversed(full_stdout.splitlines()):
        if ln.strip():
            last_line = ln.strip()
            break

    parsed = _parse_stderr(cp.stderr)

    return DispatchResult(
        plan=plan, returncode=cp.returncode,
        stdout=last_line, full_stdout=full_stdout, stderr=cp.stderr,
        parsed=parsed,
        error=None if cp.returncode == 0 else f"non-zero exit {cp.returncode}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pre-signed URLs for S3 outputs so the UI can render them inline
# ─────────────────────────────────────────────────────────────────────────────


def presign_s3(uri: str, *, expires: int = 3600) -> str:
    """Convert s3://bucket/key → https presigned URL. Returns the input
    unchanged if it isn't an S3 URI (e.g., text answers from 1c/1h)."""
    if not uri.startswith("s3://"):
        return uri
    import boto3
    rest = uri[len("s3://"):]
    bucket, _, key = rest.partition("/")
    s3 = boto3.client("s3")
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Top-level entry point — what server.py and ui.py call.
# ─────────────────────────────────────────────────────────────────────────────


def dispatch(*,
             prompt: str,
             input_modality: str,
             output_modality: str,
             parser_slot: str,
             composer_slot: str,
             asset_uri: str | None = None,
             image_quality: str = "low",
             video_duration: int = 4,
             video_size: str = "1280x720",
             video_aspect: str = "16:9",
             timeout: float = 900.0) -> dict:
    """The single function the UI and HTTP API both call. Returns a JSON-
    serializable dict suitable for both rendering and API response."""

    # Capability validation — fail fast with a useful message rather than
    # letting the module CLI error mid-run.
    if parser_slot not in PARSER_INPUT_CAPABILITY[input_modality]:
        return {"error": f"parser slot '{parser_slot}' cannot handle "
                         f"input modality '{input_modality}'"}
    if composer_slot not in COMPOSER_OUTPUT_CAPABILITY[output_modality]:
        return {"error": f"composer slot '{composer_slot}' cannot produce "
                         f"output modality '{output_modality}'"}

    plan = plan_dispatch(
        prompt=prompt,
        input_modality=input_modality, output_modality=output_modality,
        parser_slot=parser_slot, composer_slot=composer_slot,
        asset_uri=asset_uri,
        image_quality=image_quality,
        video_duration=video_duration, video_size=video_size,
        video_aspect=video_aspect,
    )
    result = run_dispatch(plan, timeout=timeout)

    # Resolve the canonical asset URI — text outputs come back as prose,
    # asset outputs come back as s3://… URIs. The UI wants a presigned
    # https URL for asset rendering; the API wants the raw s3:// for
    # callers to handle themselves.
    payload = result.to_dict()
    canonical = result.stdout
    payload["canonical_output"] = canonical
    if canonical.startswith("s3://"):
        payload["presigned_url"] = presign_s3(canonical)
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# CLI for hand-testing the dispatcher itself (skips Gradio entirely)
# ─────────────────────────────────────────────────────────────────────────────


def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="String 01 — dispatch test CLI.")
    ap.add_argument("prompt")
    ap.add_argument("--input",  default="text", choices=INPUT_MODALITIES)
    ap.add_argument("--output", default="text", choices=OUTPUT_MODALITIES)
    ap.add_argument("--parser",   default="anthropic-fast")
    ap.add_argument("--composer", default="anthropic-fast")
    ap.add_argument("--asset", default=None)
    ap.add_argument("--image-quality", default="low")
    ap.add_argument("--video-duration", type=int, default=4)
    ap.add_argument("--video-size", default="1280x720")
    args = ap.parse_args()

    out = dispatch(
        prompt=args.prompt,
        input_modality=args.input, output_modality=args.output,
        parser_slot=args.parser, composer_slot=args.composer,
        asset_uri=args.asset,
        image_quality=args.image_quality,
        video_duration=args.video_duration, video_size=args.video_size,
    )
    print(json.dumps(out, indent=2))
    return 0 if not out.get("error") else 1


if __name__ == "__main__":
    sys.exit(_cli())
