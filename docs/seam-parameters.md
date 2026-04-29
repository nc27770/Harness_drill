# Seam Parameters — the axis orthogonal to modality

> **Status: locked.** Architectural decision. Implementation evolves
> bottom-up (per-module passthrough first; dispatcher consolidation
> second). This document fixes the framing and the scope; it is not a
> build plan.

## Thesis

The modality matrix closes at 1l. Sixteen `(input × output)` cells,
seven module files, no deferrals. That axis is done.

There is a second axis, orthogonal to modality, that the curriculum
has touched only incidentally: **the parameters of the measurement
act itself**. Temperature, seed, voice, guidance scale, reasoning
effort, streaming, caching. These are not new lessons at the seam —
the lesson "what is temperature" was taught in Module 1 (bare call)
and never revisited. They are *dial settings on every existing
measurement act*, applicable universally across all `1..1l` modules.

This document fixes:

1. What counts as a seam parameter (and what does not).
2. Why these belong on the dispatcher, not in new curriculum modules.
3. The two-phase evolution path: per-module passthrough as training
   ground; dispatcher consolidation as the consolidation step.

## Two categories

The curriculum's measurement-seam framing (see
[`measurement-seam.md`](measurement-seam.md)) treats every model call
as a single act — prepared input → frozen weights → resolved output.
Seam parameters split cleanly along that act:

### Category A — outcome-shapers (which eigenvalue collapses out)

These determine **what comes out** of the inference, given fixed
input. They live on the prepared-state / operator-selection side of
the seam. Different settings → genuinely different outputs.

| Parameter | What it does | Currently lives |
|---|---|---|
| **temperature** | softmax sharpness (LLM); not directly applicable to most DiTs | Hardcoded inconsistently — 1c=0.0, 1i=0.7, 1k=0.5. No flag. |
| **top_p / top_k** | nucleus / top-k sampling (LLM only) | Not exposed |
| **seed** | RNG seed for sampling (LLM) and noise schedule (DiT) | Not exposed anywhere |
| **CFG / guidance scale** | classifier-free guidance strength (DiT image/video) | Not exposed; SDK defaults |
| **voice** | TTS voice identity (audio output) | Hardcoded `"alloy"` in 1g; not in dispatcher |
| **audio_format** | TTS output container (mp3 / wav / opus) | Hardcoded `"mp3"` in 1g |
| **reasoning_effort / thinking_budget** | how much hidden inference happens before visible collapse (Anthropic extended thinking, OpenAI o-series, Gemini thinking) | Not exposed; SDK defaults |
| **max_tokens / max_output_tokens** | output length cap | Hardcoded per module |

These are the **outcome-shaping** knobs. Two calls with different
settings here are not the same call — they're different measurement
acts producing different resolved outputs from the same prepared
state.

### Category B — mechanics-of-how (delivery and bookkeeping around the same act)

These do not change *what* comes out. They change *how* the
input/output crosses the wire, or what bookkeeping the harness
collects alongside.

| Parameter | What it does |
|---|---|
| **streaming** | same call, incremental wire delivery — third control-flow primitive alongside sync (1c–1i) and async-job (1j–1l) |
| **batch** | same call, deferred wire delivery; cheaper, slower, fire-and-forget |
| **cache_control / prompt caching** | same call, cheaper wire because the prefix is re-used (Anthropic explicit, OpenAI implicit) |
| **logprobs** | same call, extra introspection on the response (probabilities of generated tokens) |
| **embeddings** | different output *shape* (fixed-dim float vector) but still a single measurement act with no internal stages |

A streamed call and a sync call return the same content for the same
input. Batch and immediate return the same content. Caching changes
cost and latency but not output. Logprobs add a side channel.
Embeddings are a different output type but the same one-shot
measurement structure.

## Explicitly out of scope

**Tool-call output handling** is excluded. The *seam-side parameter*
(passing `tools=[...]` to offer tool emission) is dispatcher
territory and could be captured here. But the *post-seam plumbing*
(parsing the structured emission, executing the tool, looping back
with the result) is genuine **Module 3 (tool use)** scaffolding, not
a seam parameter. Splitting tool-call across two layers muddles the
framing. The whole concern is deferred to Module 3, where it has a
single home.

## Why this is dispatcher-territory, not new curriculum modules

A new curriculum module earns its slot in `level_1_modules/` by
**teaching one new lesson at the seam**. The modality matrix doubled
the matrix (`limbic-image-video-generative.md` §4.1) — that was a new
lesson on the output side. Asset conditioning on Sora/Veo (Module 1l)
introduced a new control-flow shape — that was a new lesson.

Seam parameters do not introduce new lessons. They are dial
settings on lessons already taught. Spawning `module_01m_temperature`,
`module_01n_seed`, `module_01o_streaming` would be **redundant
re-teaching** — the seam shape is unchanged; only the knob position
moves.

The architecturally correct home for them is therefore the
**dispatcher**, which already:

- validates capability per cell,
- builds the argv for each module's CLI,
- carries `image_quality`, `video_duration`, `video_size`,
  `video_aspect` across module boundaries today (`dispatch.py:91–97`).

Adding a `GenerationKnobs` dataclass to the dispatcher and propagating
its fields into each module's CLI is the natural extension. The
modules grow argparse flag surface, not lesson surface.

## Two-phase evolution

The intent is to introduce these parameters *bottom-up*, using the
existing modules as training ground for each one, then consolidate
the cross-cutting concern in the dispatcher once the pattern is
stable.

### Phase 1 — per-module passthrough (training ground)

For each seam parameter:

1. Pick the most natural module to instrument first (e.g.,
   `temperature` lands first in 1b/1c where bilateral T=0.0 vs T=0.7
   teaches the right lesson; `voice` lands first in 1g where TTS
   already exists; `seed` lands first in 1i/1j where DiT
   reproducibility is visible).
2. Add the argparse flag to that module's CLI.
3. Wire it through the SDK call.
4. Prove the diff in a small smoke test.

This phase teaches the parameter at a single seam first, with the
existing module's lesson as anchor. It avoids introducing a knob at
the dispatcher level before any module knows what to do with it.

### Phase 2 — dispatcher consolidation

Once a parameter is plumbed through ≥2 modules and the SDK-mapping
quirks are understood:

1. Promote the flag to a `GenerationKnobs` field on `dispatch.py`.
2. Propagate it into every relevant module's argv at dispatch time.
3. Capability-filter the UI dropdown / slider the same way
   parser/composer dropdowns are filtered today.
4. Remove redundant per-module documentation; the canonical home is
   the dispatcher.

Some parameters skip Phase 1 if they are obviously universal from
day one (e.g., `cache_control` is a pure cost optimization with no
pedagogical anchor — it goes straight to dispatcher).

## SDK-mapping caveats

Several parameters are named or shaped differently across the three
labs the harness covers. The dispatcher abstracts the **harness-side
name**; each module's `_call_*` adapter does the per-SDK mapping.

| Parameter | Anthropic | OpenAI | Google |
|---|---|---|---|
| temperature | `temperature` | `temperature` | `temperature` |
| top_p | `top_p` | `top_p` | `top_p` |
| seed | not supported | `seed` | not supported on most chat surfaces; supported on Imagen/Veo |
| reasoning effort | `thinking={"type":"enabled","budget_tokens":N}` | `reasoning_effort="low|medium|high"` (o-series) | `thinking_config={"thinking_budget":N}` (2.5 series) |
| voice (TTS) | not supported | `voice="alloy|echo|…"` | not supported |
| CFG / guidance | n/a (not a DiT) | `guidance_scale` (Sora) | `guidance_scale` (Imagen/Veo, where exposed) |
| streaming | `stream=True` | `stream=True` | `stream=True` (older SDK), `generate_content_stream` (newer) |
| prompt caching | `cache_control` blocks | implicit (auto) | implicit (auto on 2.5) |

Where a lab does not support a knob, the module either silently
no-ops the flag or returns a typed error if the user asked for
something the substrate cannot do — same pattern as the existing
`SLOT_INPUT_CAPABILITIES` gate in 1h.

## What this lock means

- Module 1's curriculum is **closed at 1l** for the modality axis.
  No 1m, 1n, 1o, etc. for seam parameters.
- All seam parameters land first in existing modules (Phase 1) and
  consolidate into the dispatcher (Phase 2). Both phases live in
  files that already exist (or in `dispatch.py`'s growth).
- Tool-call output is **not** a seam parameter — it lives in
  Module 3.
- Embeddings are a seam parameter (different output shape, same
  measurement act) but if/when they earn first-class treatment they
  surface as a `GenerationKnobs.want_embedding` flag, not a new
  module.
- Streaming is a third control-flow primitive (alongside sync and
  async-job). It introduces a new delivery shape but not a new
  seam shape — also a dispatcher growth, not a curriculum module.

## What is still legitimately a new curriculum module

To stay honest about the boundary: things that **would** earn a new
module are things that change the seam *shape*, not the seam
*parameters*. Examples that are real new lessons:

- **Multi-asset input** (text + image + audio together) —
  `input_modality` becomes a *set*, capability matrix becomes
  set-cover. Genuine new lesson; would be Module 1m.
- **Persistent threads / memory** — Module L2.2, already on the
  roadmap.
- **Tool use loop** — Module 3.
- **Faculty-tagged evaluation** — Module 4.
- **Telemetry sink** — Module 5.
- **LIMBIC v0 routing** — Module L3.1.

Seam parameters are not in that list and never will be. They are
dispatcher growth.

## References

- [`measurement-seam.md`](measurement-seam.md) — the philosophical
  lens this doc is downstream of.
- [`limbic-image-video-generative.md`](limbic-image-video-generative.md)
  §4.1 — the modality-matrix-doubles framing this doc is orthogonal
  to.
- [`limbic-design.md`](limbic-design.md) — the multi-axis router
  these knobs eventually become inputs to.
- `level_2_strings/string_01_dispatch/dispatch.py` — the file that
  grows in Phase 2.
