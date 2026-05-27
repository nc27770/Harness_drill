# The Mind Contract — SCHEMA v0.1 (frozen 2026-05-27)

The declarative boundary of the canonical agent. A **Mind** is *pure data*: a
`config` (its identity — ends + declared means) and a `state` (its accrued
continuum). Any **body** (runtime / machine) that satisfies the runtime contract
below can load a Mind and animate it. The Mind outlasts any body that hosts it;
a body only *animates* it.

This is the framework. Everything in later modules either evolves this contract
or builds around it. It is versioned (`schema_version`) so it can migrate.

---

## Principle: data ⊥ code

| **Data** (declarative · persisted · zero behavior) | **Code** (the body · side-effecting · never persisted) |
|---|---|
| Mind `config`: id, purpose/ends, model params, tool **contracts**, policies | the loop / animator |
| Mind `state`: status, cursor, transcript, pending, ledger | tool **implementations** (isolated runners) |
| | the provider client (the measurement) |
| | the Store (save/load), the projection (neutral ↔ vendor), the observer/witness |

The contract between them is one shape: `animate(config, state, tool_runners, client) → new_state`.
**Code consumes data, emits data, with contained side effects. Data never contains code.**

## The faculty ontology

Every transcript entry is tagged by faculty — the mind's metabolism:

- **perception** — tokens *in*. The world entering the mind. Includes **human input *and* tool results** (the mind perceives an engine's output). An edge.
- **reasoning** — the intermediate inner loop. Neither how input arrived nor the final conclusion.
- **action** — engaging an *external engine to DO* something. A **means, never a conclusion**.
- **expression** — tokens *out* to the world. The conclusion (`answer`) or a non-conclusive expression (`ask`). The other edge.

The true token sources are the edges (perception in / expression out); reasoning + action are internal metabolism. Memory, eval, and routing all later slice on `faculty`.

---

## Config schema — the declarative Mind (READ-ONLY to the running mind)

```json
{
  "schema_version": "0.1",
  "mind_id": "stable-id",
  "label": "homework-helper",
  "purpose": { "system": "role/constraints", "goal": "… | null" },
  "model": {
    "provider": "anthropic",
    "name": "claude-sonnet-4-6",
    "max_tokens": 1024,
    "temperature": 0.0,
    "thinking": { "enabled": true, "budget_tokens": 1024 }
  },
  "tools": [
    { "name": "calculate", "description": "...", "input_schema": { "...JSON Schema..." } }
  ],
  "policies": { "max_iterations": 6 }
}
```

`tools` are declared **contracts** (name + description + input_schema) — *what the mind is configured to use*. The implementation is supplied by the body, isolated.

## State schema — the continuum (READ-WRITE; transcript append-only)

```json
{
  "schema_version": "0.1",
  "mind_id": "-> config",
  "status": "ready | running | awaiting_input | done",
  "cursor": { "turn": 0, "iteration": 0 },
  "transcript": [
    { "seq": 0, "faculty": "perception", "origin": "human",  "content": "What is 17% of 240, plus 13?" },
    { "seq": 1, "faculty": "reasoning",  "content": "Compute it with the tool." },
    { "seq": 2, "faculty": "action",     "engine": "calculate", "input": { "expression": "17/100*240+13" }, "ref": "a1" },
    { "seq": 3, "faculty": "perception", "origin": "engine", "ref": "a1", "ok": true, "content": "53.8" },
    { "seq": 4, "faculty": "expression", "conclusive": true, "content": "It's 53.8." }
  ],
  "pending": { "type": "ask | null", "question": "… | null" },
  "ledger": { "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "turns": 0 },
  "updated_at": "2026-05-27T..."
}
```

- **No `role` field** — `user`/`assistant` is a *vendor* concept; the projection derives it from `faculty`. Stays provider-agnostic.
- `origin: human | engine` tags the perception edge at its source.
- `ref` pairs an `action` with the `perception` that is its result.
- `conclusive` distinguishes goal-achieving `answer` from `ask` (expression that needs more perception).

---

## Invariants (locked, v0.1)

1. **Ontological lock.** The running mind may only *read* its `config`. There is no code path by which it overwrites its own purpose/scope/goal. Ends are immutable; the mind exercises only means. ("No mind authors its own ends," as access control.)
2. **Tool isolation.** Tools execute **out-of-process** (sandboxed subprocess now; remote callable / TAAFNI later), timeout-bounded. A tool crash, hang, or bad effect returns as a *contained perception* (an error observation), **never as mind death**.
3. **Provider-agnostic transcript.** Faculty-tagged, vendor-neutral; a projection layer maps it to whatever provider animates the mind. The mind outlasts the *vendor*, not just the process.
4. **Identity = config + state.** A Mind is fully re-animatable from these two documents and nothing else host-specific.

## Storage

SQLite — `minds(mind_id, config_json, created_at)` + `states(mind_id, state_json, updated_at)`. JSON columns: queryable, diffable, S3-syncable later.

## The runtime contract — what a *body* must provide

To animate a Mind, a body must supply:
- a **model client** for `config.model.provider`;
- an **isolated tool runner** for every tool in `config.tools` (the body's *provisions* must cover the mind's *declared needs* — `needs ⊆ provisions`, else animation fails loudly);
- the **loop / animator**, the **projection** (neutral ↔ vendor), and the **Store**.

A body is "capable of" a Mind iff it satisfies this contract.
