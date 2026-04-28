"""Asset fetcher for harness modules.

Resolve a URI (`s3://...`, `http(s)://...`, or local path) to bytes plus a
media type. S3 fetches are cached locally by ETag so repeat reads are free
and stay correct when the upstream object is rewritten.

Why this lives outside the bilateral file: the bilateral pipeline doesn't
care where the image came from, only what bytes it has. Keeping fetch
separate is the smallest possible Level-2 string in the curriculum's sense
— a primitive shared by every later module that needs media.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


CACHE_ROOT = Path.home() / ".cache" / "harness-drill"

# Map common image extensions to their media types. Used as a fallback when
# the source doesn't surface a Content-Type (e.g., local file paths).
_EXT_MEDIA_TYPES: dict[str, str] = {
    # images (module 1d)
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif":  "image/gif",
    # audio (module 1e)
    "mp3":  "audio/mpeg",
    "wav":  "audio/wav",
    "m4a":  "audio/mp4",
    "ogg":  "audio/ogg",
    "flac": "audio/flac",
}


def _media_type_from_uri(uri: str) -> str:
    # Strip query string before reading the extension — common for presigned URLs.
    last = uri.split("?", 1)[0].rsplit(".", 1)
    if len(last) != 2:
        return "application/octet-stream"
    return _EXT_MEDIA_TYPES.get(last[1].lower(), "application/octet-stream")


def _ensure_cache_dir(subdir: str) -> Path:
    p = CACHE_ROOT / subdir
    p.mkdir(parents=True, exist_ok=True)
    return p


# ─── S3 ─────────────────────────────────────────────────────────────────────

def _fetch_s3(uri: str) -> tuple[bytes, str]:
    """boto3 picks up credentials automatically from the EC2 instance role,
    `aws configure`, or AWS_* env vars — in that order."""
    import boto3

    parsed = urlparse(uri)
    bucket, key = parsed.netloc, parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"malformed S3 URI: {uri}")

    s3 = boto3.client("s3")

    # head_object is cheap and gives us the ETag (S3's content fingerprint)
    # plus the server-side Content-Type. ETag changes whenever the object is
    # rewritten, which is exactly the cache-invalidation key we want.
    head = s3.head_object(Bucket=bucket, Key=key)
    etag = head["ETag"].strip('"')
    media_type = head.get("ContentType") or _media_type_from_uri(uri)

    cache_dir = _ensure_cache_dir("s3")
    cache_path = cache_dir / etag

    if cache_path.exists():
        return cache_path.read_bytes(), media_type

    obj = s3.get_object(Bucket=bucket, Key=key)
    data = obj["Body"].read()
    cache_path.write_bytes(data)
    return data, media_type


# ─── HTTP(S) ────────────────────────────────────────────────────────────────

def _fetch_http(uri: str) -> tuple[bytes, str]:
    """No caching — HTTP responses don't always carry stable validators, so
    we fetch fresh every time. Heavy callers should switch to a real HTTP
    cache (httpx + hishel, or similar) when this matters."""
    with urllib.request.urlopen(uri, timeout=30) as r:
        data = r.read()
        media_type = r.headers.get("Content-Type") or _media_type_from_uri(uri)
        # Strip charset, if present: "image/png; charset=binary" → "image/png"
        media_type = media_type.split(";", 1)[0].strip()
        return data, media_type


# ─── Local file ─────────────────────────────────────────────────────────────

def _fetch_local(uri: str) -> tuple[bytes, str]:
    p = Path(uri).expanduser().resolve()
    return p.read_bytes(), _media_type_from_uri(uri)


# ─── Public entry point ─────────────────────────────────────────────────────

def fetch(uri: str) -> tuple[bytes, str]:
    """Return (bytes, media_type) for a URI.

    Supports:
      - s3://bucket/key            (cached by ETag in ~/.cache/harness-drill/s3/)
      - http://... or https://...  (no caching)
      - any other string           (treated as a local filesystem path)
    """
    if uri.startswith("s3://"):
        return _fetch_s3(uri)
    if uri.startswith(("http://", "https://")):
        return _fetch_http(uri)
    return _fetch_local(uri)


__all__ = ["fetch"]
