"""FastAPI server hosting the dispatch UI + JSON API.

Mounts Gradio under "/" so the browser experience is the catch-phrase-
gated UI. Adds "/api/dispatch" for HTTP callers — same dispatch
function, JSON in, JSON out, requires `?phrase=harness` (or an
`X-Harness-Phrase` header) on every call.

Run:
    .venv/bin/python level_2_strings/string_01_dispatch/server.py
                  [--host 127.0.0.1] [--port 7860]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow importing dispatch.py and ui.py whether you run this file
# directly or import it.
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import gradio as gr

from dispatch import dispatch
from ui import build_ui, CATCH_PHRASE


api = FastAPI(title="Harness Drill — Dispatch", version="0.1.0")


class DispatchRequest(BaseModel):
    prompt: str
    input_modality: str = "text"
    output_modality: str = "text"
    parser_slot: str = "anthropic-fast"
    composer_slot: str = "anthropic-deep"
    asset_uri: str | None = None
    image_quality: str = "low"
    video_duration: int = 4
    video_size: str = "1280x720"
    video_aspect: str = "16:9"


def _check_phrase(phrase: str | None) -> None:
    if (phrase or "").strip().lower() != CATCH_PHRASE:
        raise HTTPException(status_code=401, detail="missing or wrong phrase")


@api.get("/api/health")
def health():
    return {"status": "ok"}


@api.post("/api/dispatch")
def api_dispatch(req: DispatchRequest,
                 phrase: str | None = Query(default=None),
                 x_harness_phrase: str | None = Header(default=None)):
    _check_phrase(phrase or x_harness_phrase)
    out = dispatch(**req.model_dump())
    if out.get("error"):
        return JSONResponse(out, status_code=400 if "cannot" in out["error"] else 500)
    return out


# Mount the Gradio UI at "/".
gradio_blocks = build_ui()
app = gr.mount_gradio_app(api, gradio_blocks, path="/")


def _main() -> int:
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()
    uvicorn.run(
        "server:app" if args.reload else app,
        host=args.host, port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
