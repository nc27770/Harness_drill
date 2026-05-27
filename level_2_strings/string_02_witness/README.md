# Level-2 String 02 — The Witness (Mind & Machine log)

> **Curriculum:** **Layer 2** — a cross-module *surface* over the agent-loop kernels (Modules 2–5), the same layer as the Module-1 dispatcher (`string_01_dispatch/`). Embodies treatise Part VII (Observance) and previews Module 11 (traces & telemetry).

A Gradio app that runs the **real** kernel from
`level_1_modules/module_02_conversation/conversation.py` (nothing faked) and
makes its machinery visible, turn by turn — then serializes every thread to disk
as the **Mind & Machine log**.

## Why it's a string, not a module

It witnesses a *single* lesson today (M2, the conversation loop) but is built to
carry M3 (three-phase loop), M4 (native tools), and M5 (the agent class) on the
**same UI** — a cross-module surface that composes level-1 modules. By the
project's convention that's a Layer-2 string. It attaches to the kernel's
`observer` seam, so new event types (tool calls, actions) light up new panels
without touching the kernel's teaching diff.

## The five live panels

| Panel | Shows |
|---|---|
| **Conversation (Mind)** | what was said |
| **Harness meta-log** | the loop's internal events: append → ship-full-history → maybe-compact → API call → reply |
| **Telemetry (Machine)** | per-turn + cumulative ctx/out/cost, plus the **balloon** plotted |
| **Chain-of-thought** | model reasoning (toggle extended thinking) |
| **Pre / Post compaction** | the messages list before vs after, with the summary that replaced the old turns |
| **Logs & Compare** | where this thread is serialized + the index of all threads |

## The Mind & Machine log

*Mind* = conversation + chain-of-thought; *Machine* = tokens, cost, latency,
compaction mechanics. One conversation = one uniquely-identified thread, written
to `traces/witness/` (git-ignored):

```
<ts>_<id>_<label>.jsonl   append-only raw event stream — crash-safe source of truth
<ts>_<id>_<label>.json    structured record (rewritten each turn, always whole)
<ts>_<id>_<label>.md      human-readable transcript
index.jsonl               DERIVED: one row per thread, for comparison
```

**One file per conversation, not one appended mega-log** — so a single thread
renders standalone, threads can't corrupt each other, and identity is the
filename. Comparison is served by the *derived* `index.jsonl` (rebuilt by
scanning the `.json` files), never by appending raw logs together.

Rebuild/compare the index from the CLI:

```sh
.venv/bin/python level_2_strings/string_02_witness/mindmachine_log.py traces/witness
```

## Demo threads (test cases, not modules)

Three scripted threads — same kernel, different inputs/settings — each writes one
log file (your first rows to compare):

- **compaction-fidelity** — compaction fires but the summary *preserves* the early
  facts. The happy path.
- **lost-in-the-middle** — a fact stated at turn 1, buried, then queried. Position
  effect; the *setup* is the lesson (and why compaction keeps recent turns).
- **compaction-loss** — precise facts + a tiny summary budget that *must* drop
  detail; a later query hits what was dropped → visible loss. The real risk of
  summarize-and-compact.

## Run

```sh
.venv/bin/python level_2_strings/string_02_witness/witness.py \
    [--host 127.0.0.1] [--port 7861] [--share]
```

Gated by the catch phrase **`harness`** (server-side enforced, same as the
Module-1 dispatcher). With `--share`, the public `*.gradio.live` URL makes live
API calls on your key — the phrase is the only guard; close it when done.
