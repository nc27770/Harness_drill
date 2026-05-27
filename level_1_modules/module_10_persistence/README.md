# Module 10 — Persistence & the Canonical Mind (M5 ⊕ M10)

> **Curriculum:** Movement Two, Module 10 — *Persistence and Resumption* — fused with Module 5's *declarative Agent*. See [`docs/curriculum.md`](../../docs/curriculum.md). The data contract is **[`SCHEMA.md`](SCHEMA.md)** (frozen v0.1) — read it first.

**The premise:** an in-process agent dies with its process. A **mind** should
outlast the body that hosts it. So the canonical agent is *born durable*: a
**declarative config** (its identity/ends) + an **externalized state continuum**
(its accrued experience), persisted to disk, invoked via a resumable API. Kill
the body mid-thought; a fresh body loads `(config, state)` by `mind_id` and
resumes *as the same mind*.

This is **data ⊥ code**: the Mind is pure data (SCHEMA.md); this module is the
*body* — pure code that animates it with contained side effects.

## The pieces (the body)

| file | role |
|---|---|
| `SCHEMA.md` | the frozen data contract (config + state, faculties, invariants) |
| `store.py` | SQLite persistence of `(config, state)` by `mind_id` |
| `engine_calculate.py` | a tool that runs **in its own process** (never imported) |
| `engines.py` | the body's isolated tool runners + `provisions()` (the hands) |
| `projection.py` | neutral faculty-transcript ↔ Anthropic messages (the only vendor-aware code) |
| `runtime.py` | the animator (M4 loop, faculty-tagging, **checkpoint every step**), `Body`, `step`/`resume`, CLI |
| `witness.py` | observance, API-form: a live `observer` + a documentary `render_md` (no UI) |

## CLI

```sh
P=level_1_modules/module_10_persistence/runtime.py
.venv/bin/python $P create hw1                      # install a mind (persists config + empty state)
.venv/bin/python $P step  hw1 "What is 17% of 240, plus 13?"   # animate; live observance to stderr
.venv/bin/python $P resume hw1                       # continue a suspended/crashed mind
.venv/bin/python $P show  hw1                         # faculty transcript
.venv/bin/python $P witness hw1                       # serialize the Mind & Machine log (.md + .json)
.venv/bin/python $P list                              # all minds + status
```

## The proof — a mind outlasts the machine

```sh
.venv/bin/python $P create hw1
# crash the body mid-thought, right after the first tool result is persisted:
HARNESS_CRASH_AFTER_TOOL=1 .venv/bin/python $P step hw1 "What is 17% of 240, plus 13?"   # exits 7
.venv/bin/python $P show hw1     # status=running, tool result persisted, NO conclusion yet
# a brand-new process picks up the same mind and finishes — without redoing the tool:
.venv/bin/python $P resume hw1
.venv/bin/python $P show hw1     # status=done; the post-crash steps continue the pre-crash transcript
```

Verified: the resumed mind continued the *same* transcript across a real process
boundary, re-using the already-perceived tool result rather than recomputing it.

## What a body must provide (the capability contract)

A `Body` refuses to host a Mind it isn't capable of: `needs ⊆ provisions`, where
`needs` = the Mind's declared `tools` minus runtime-handled signals (`ask_user`),
and `provisions` = the engines this body's `Registry` can run. A body must be
*capable of* the mind it animates, or it fails loudly.

## Witness (observance, no UI — per the API-first stance)

- **Live:** attach `event_printer()` (or any `observer(event, payload)`) to watch
  faculties flow during `step`/`resume` — the seam an API consumer would stream.
- **Documentary:** `witness <mind_id>` renders the Mind & Machine log to
  `traces/minds/<id>.md` + `.json` (the `.json` is just the canonical state).

## v0.1 deferrals (honest)

- **Extended thinking is OFF here.** Replaying signed thinking blocks across
  tool-use turns is a real edge; SCHEMA stays ready for it, runtime defers it.
- **Sandboxing** is process-isolation + timeout, not seccomp/cgroups; hardening
  is a later step (and the future remote/TAAFNI runner supersedes it).
- **Memory** is the single working continuum only — the M6/M7 mind-state vs
  world-state separation is tagged (`source`/`faculty`) but not yet acted on.
