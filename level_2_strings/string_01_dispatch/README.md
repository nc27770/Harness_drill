# Level-2 String 01 — Dispatch

A cover application that routes any `(input modality × output modality
× parser × composer)` request to the right level-1 module. First
`level_2_strings/` artifact — composes existing modules, doesn't teach
a new lesson at the seam.

## What it is

- **`dispatch.py`** — subprocess router. `dispatch(...)` is the single
  entry point both the UI and the HTTP API call. Picks the right
  module file, builds its CLI, runs it, parses stdout (canonical
  result) and stderr (cost / latency / IR trace).
- **`ui.py`** — Gradio Blocks UI. Catch-phrase gated splash screen,
  capability-filtered dropdowns, four output renderers (text / image /
  audio / video), three tabs (result / summary / raw stderr trace).
- **`server.py`** — FastAPI hosting Gradio at `/` and a JSON API at
  `/api/dispatch`. Phrase enforcement on every API call.
- **`deploy/`** — snapshots of the nginx site config and the systemd
  unit currently running on this EC2 box.

## Why subprocess fan-out, not in-process import

The level-1 modules are self-contained CLIs whose *isolation* is the
curriculum's main pedagogical property — *the diff between Module N
and Module N-1 is the lesson*. An in-process import would force every
module to expose a stable Python API and would dissolve that
isolation. Subprocess fan-out preserves it; the cost is one process
fork per call (negligible against parser+composer latency) and a
slightly fragile stderr-regex extraction (easily replaced by a
`--json-trace` flag when Module 5 lands).

## Dispatch table

Seven module files cover all 16 modality cells. 1h consolidates 1d–1g
for the input × text/audio output cells; 1k/1l close the asset-
conditioned image/video diagonals:

| Output | Input | Module |
|---|---|---|
| text | text | `1c` (`bilateral_x.py`) |
| text | image / audio / video | `1h` (`bilateral_h.py`) |
| audio | any | `1h` (`bilateral_h.py`) |
| image | text | `1i` (`bilateral_i.py`) |
| image | image / audio / video | `1k` (`bilateral_k.py`) |
| video | text | `1j` (`bilateral_j.py`) |
| video | image / audio / video | `1l` (`bilateral_l.py`) |

All 16 cells of the (input × output) modality matrix are covered. 1k
holds two internal paths (edit vs translate); 1l holds two (condition
vs translate). The dispatcher only sees cell coordinates — the path
choice is internal to each module.

## Running locally

```sh
.venv/bin/python level_2_strings/string_01_dispatch/server.py \
  --host 127.0.0.1 --port 7860
```

Then open `http://127.0.0.1:7860/`. Catch phrase is `harness`.

## HTTP API

Every call must include the phrase via either:
- query param: `?phrase=harness`
- header: `X-Harness-Phrase: harness`

```sh
curl -sk -X POST "https://<host>/api/dispatch?phrase=harness" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is 2+2? One sentence.",
    "input_modality": "text",
    "output_modality": "text",
    "parser_slot": "anthropic-fast",
    "composer_slot": "anthropic-fast"
  }'
```

Response:
```json
{
  "module": "1c (text,text)",
  "argv": [...],
  "returncode": 0,
  "stdout": "2 + 2 = 4.",
  "stderr": "...",
  "parsed": {
    "total_cost_usd": 0.000937,
    "stage_costs_usd": [0.000628, 0.000309],
    "stage_latencies_s": [0.89, 0.59],
    "job_id": null
  },
  "canonical_output": "2 + 2 = 4.",
  "presigned_url": "https://..."   // only for s3:// outputs
}
```

For asset-output cells (image / audio / video), `canonical_output` is
an `s3://` URI and `presigned_url` is a 1-hour HTTPS URL the caller can
fetch directly.

## Deployment (current EC2 setup)

```
[ user / API client ]
        │
        ▼  https://ec2-44-210-82-161.compute-1.amazonaws.com/
    ┌────────────────────┐
    │ nginx (port 443)   │  TLS termination (self-signed cert),
    │                    │  reverse proxy, WS upgrade
    └────────┬───────────┘
             │  proxy_pass http://127.0.0.1:7860
             ▼
    ┌────────────────────┐
    │ uvicorn + FastAPI  │  /api/dispatch (gated)
    │ + Gradio at "/"    │  /api/health (open)
    └────────┬───────────┘
             │  subprocess.run(...)
             ▼
    ┌────────────────────┐
    │ level_1_modules/   │  bilateral_x / bilateral_h /
    │ <module>.py        │  bilateral_i / bilateral_j /
    │                    │  bilateral_k / bilateral_l
    └────────────────────┘
```

System files snapshotted in `deploy/`:

- `deploy/nginx-harness.conf` — `/etc/nginx/conf.d/harness.conf`
- `deploy/harness-dispatch.service` — `/etc/systemd/system/harness-dispatch.service`

Service control:

```sh
sudo systemctl status  harness-dispatch.service
sudo systemctl restart harness-dispatch.service
sudo journalctl -u harness-dispatch.service -f
sudo systemctl reload nginx
```

## Trade-offs deliberately accepted

- **Self-signed cert** — browsers warn once per fresh device. Real cert
  needs a registered domain (Let's Encrypt won't issue for
  `*.compute.amazonaws.com`). When a real hostname is in play, swap to
  certbot.
- **No real auth** — single-word catch phrase is the rate-limit. Anyone
  who finds the URL + word can spend video budget. Move to a real
  token before this URL leaks.
- **Stderr regex extraction** — fragile vs a structured trace. Module 5
  (telemetry sink) is what replaces this with per-module
  `--json-trace` output and a persistent journal.
- **No persistent chat history** — single-turn. Module 2 (memory) is
  what adds threads.
- **Static dropdowns** — user picks parser and composer manually. Auto-
  routing is what LIMBIC v0 (L3.1) does — same dispatch plumbing,
  policy plugged in instead of dropdown values.

## What this enables next

- **Module 4 (faculty-tagged evals)** can fan out evaluation calls
  through `/api/dispatch` instead of needing its own per-module
  invocation logic.
- **Module 5 (telemetry sink)** persists every `/api/dispatch` request
  + response to `s3://harness-eng/traces/`, paired by run id.
- **Module L2.2** (chat with memory) layers persistent threads on top
  of this single-turn dispatcher.
- **Jupyter or other UX layers** can mount under nginx alongside this
  one (e.g., `location /jupyter/` block).
