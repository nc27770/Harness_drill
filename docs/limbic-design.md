# LIMBIC — Design Notes

**LIMBIC** = *LLM Interchange Modulator for Bilateral (input/output) Intelligence Compute.*

A future-project sketch. Not for immediate build. The purpose of this document
is to preserve the full design intuition — the parts that look right, the parts
that look hard, and the staged path toward making LIMBIC fall out of work the
curriculum is doing anyway. If we build LIMBIC well, it will not feel like a
bolt-on framework; it will feel like the natural conclusion of the pieces we
built first.

This document is a sibling to `docs/benchmark-lens.md` (the faculty-aware
benchmark audit) — both treat the model as a component in a larger system, and
both insist the system designer (the harness) is the right vantage point, not
the model.

---

## 1. The Premise

Existing multi-provider routers (OpenRouter, LiteLLM, Portkey, etc.) make a
single decision per call: *which model handles this turn?* They route at
**call granularity**.

LIMBIC routes at **faculty × modality × direction granularity** — that is, it
treats a single user-facing turn as the composition of multiple smaller calls,
each of which can be dispatched to a different model based on:

1. **Direction** — is this a *parsing/perceptive* step (input) or a
   *composing/expressive* step (output)?
2. **Faculty** — which of the five faculties dominates this step?
   (Deductive, Inductive, Abductive, Perceptive, Expressive — see the
   curriculum addendum.)
3. **Modality** — what input/output modalities are involved (text, image,
   audio, video)?
4. **Cost-per-token of the candidate model on the dominant faculty.**

The router (the "modulator") composes these into a per-turn execution plan and
dispatches each step to the model best suited to it — capability-optimized
where it matters, cost-optimized everywhere else.

Three labs (Anthropic, OpenAI, Google) are the initial scope. Same-API-shape
cross-provider work has already been onboarded in the curriculum, so adapter
work is not blocking.

---

## 2. What Makes LIMBIC Genuinely Novel

These are the load-bearing claims. If any of them fail to hold up under a
prototype, the design changes.

### 2.1 Bilateral split — input parser ≠ output composer

The strongest single piece of the idea. Today, every router I know of asks
"which model handles this call." LIMBIC asks "which model **understands** the
input, and which model **composes** the output." Those can be — and often
should be — different models.

The asymmetry is real:

- **GPT-4o** is the strongest audio-input parser in our three-lab universe,
  but Sonnet 4.6 often produces better written prose for the same task.
  Forcing one model to do both means paying a premium for an unused
  competence.
- **Gemini 2.5 Pro** has the largest context window, making it the natural
  parser for very long input documents — but its output has different stylistic
  defaults than Claude. Splitting parser from composer lets you use Gemini's
  context capacity *without* inheriting its prose style.
- **Claude Sonnet 4.6** has the cleanest tool-use semantics (typed content
  blocks), making it the natural composer when the output must include
  structured tool calls — even if the input parsing was done elsewhere.

**Bilateral split is the thing worth prototyping first** (Module 1b). It
either confirms or kills the rest of the design before we sink weeks into the
full router.

### 2.2 Faculty-aware routing

Most existing routers use coarse task buckets: "code," "math," "creative."
That partition is leaky — the same surface task can require very different
faculties (a math problem can be deductive *or* abductive depending on
problem shape).

The five-faculty decomposition — *Deductive, Inductive, Abductive,
Perceptive, Expressive* — collapses superficial task differences into the
underlying capability axis. Routing on faculty rather than task means:

- "Summarize this argument" and "draft this email" both route through the
  expressive lane.
- "Solve this proof" and "verify this contract clause" both route through
  the deductive lane.
- The same lane can be served by the cheapest model that meets the bar for
  that faculty, regardless of surface task.

The benchmark-lens document already argues that benchmark scores conflate
faculties; LIMBIC argues that *routing decisions* should not.

### 2.3 Cost-per-faculty (not just cost-per-call) is the real lever

The five faculties have radically different cost profiles when matched to
appropriate machinery:

| Faculty | Cheap path | Expensive path |
|---|---|---|
| Deductive | Run the test, parse the JSON, call the rule engine | Use the LLM as a reasoner |
| Perceptive | RAG, lookup table, structured DB | Long-context LLM |
| Inductive | Cached small-model classification | Large-model freshness |
| Abductive | (no cheap path — this is where you pay) | Frontier reasoning model |
| Expressive | Smaller fine-tuned writer | Top-tier composer with style control |

A naïve "always Sonnet 4.6" strategy pays Sonnet rates for faculties where
Haiku, Flash, or non-LLM machinery would suffice. LIMBIC's job is to never
pay that overage.

### 2.4 Modality routing is forced, not optional

Already true today, before LIMBIC exists:

- Video input → only Gemini accepts it natively.
- Audio output → only OpenAI's GPT-4o emits it.
- 1M-token contexts → Gemini 2.5 Pro is the only practical option in our
  three-lab set.

A single-provider harness either picks the lowest-common-denominator model
(missing modalities entirely) or does unnatural transcription gymnastics
(audio → Whisper → text → Claude → text → TTS, paying for each step).
LIMBIC's modality routing is just *making explicit* the dispatch that
already has to happen — turning gymnastic workarounds into first-class
routing decisions.

---

## 3. Where LIMBIC Will Fight You

The complications. None disqualifying. All require deliberate design.

### 3.1 Faculty classification of the input is itself an abductive task

Before LIMBIC can route by faculty, it has to *decide* which faculty
dominates the prompt. That decision is the same kind of judgment LIMBIC is
trying to outsource — there's a recursion problem.

Two coping strategies:

- **Cheap recursion:** a small model (Haiku, Flash) does coarse faculty
  classification, a routed model handles execution. Adds one cheap call per
  turn but solves the recursion in practice.
- **Harness annotation:** the harness *tells* LIMBIC which faculty applies,
  via prompt templates or per-tool metadata. Loses generality but is far
  cheaper and more predictable.

Start with annotation. Add classification only if and when the workload
shows real benefit.

### 3.2 Routing has its own failure modes

Three providers ≈ 3× the surface area for outages, rate limits, deprecated
models, schema drift. LIMBIC must include:

- **Modality validation** (don't send audio to a text-only model).
- **Fallback chains per faculty** (if Gemini is down, what's the substitute?).
- **Circuit breakers** (don't keep dispatching to a degraded provider).
- **Telemetry** (every routed call tagged with chosen model, faculty, outcome).

None of this is hard; all of it is tax that single-provider harnesses don't
pay.

### 3.3 API drift at the boundary

Already felt in the curriculum: each lab serializes content blocks
differently, returns usage metrics differently, has different `max_tokens`
semantics. (The Gemini 2.5 Pro hidden-thinking-tokens episode is the most
recent example.)

LIMBIC needs:

- A **uniform internal IR** for prompts and responses (probably a typed
  block model — closer to Anthropic's than OpenAI's, since Anthropic's is
  most expressive).
- **Per-provider adapters** that translate IR ↔ wire format.
- **Versioned mappings** so a provider's schema change is one adapter
  update, not a system-wide refactor.

This is its own multi-week project. Probably a Level-2 string in the
curriculum.

### 3.4 You don't yet have the data to route well

Routing decisions need empirical evidence: *for faculty F, on prompts of
shape S, with modality M, model X beats model Y by Z% at $W per call.*

That evidence only exists if the harness has been calling all candidate
models on real workload and tagging outcomes. Right now the curriculum has
one smoke test. **Designing LIMBIC without this data is designing for
hypothetical traffic.**

The curriculum's Module 4 (faculty-aware evals + telemetry) is the
prerequisite. LIMBIC depends on Module 4 the way Module 4 depends on
Modules 1–3.

### 3.5 The curriculum's pedagogy already disagrees with starting here

The repo's thesis is *"build patterns by hand before adopting frameworks."*
LIMBIC is a framework. Building LIMBIC first means every later module
retrofits to it; building it last means it falls out naturally from
primitives we already trust.

This is not a complication of LIMBIC per se — it's a complication of
*building LIMBIC first*. Solved by deferring it to Level 3.

---

## 3.6 The perception / intellect / expression triad

After Modules 1d–1g instrumented the input *and* output modality axes, a
sharper routing model emerged. The 5-faculty taxonomy from
`docs/benchmark-lens.md` is the right lens for *grading* benchmarks (it
distinguishes deductive from abductive output cleanly). For *routing*, a
3-faculty triad is more usable:

| Faculty | Pipeline location | What its tier choice is reacting to |
|---|---|---|
| **Perception** | parser stage | input hardness — modality, noise, ambiguity, length |
| **Intellect** | wherever the reasoning happens | reasoning depth required to produce the right answer |
| **Expression** | composer stage | output modality + prose/voice quality required |

This triad lets LIMBIC make three orthogonal Goldilocks decisions per
call, each consulting per-faculty empirical data:

- *Perception fast/deep?* — driven by input hardness on this call.
- *Intellect fast/deep?* — driven by reasoning depth required.
- *Expression fast/deep?* — driven by output modality and prose
  expectations.

Cross-faculty interactions matter (e.g., a model that thinks heavily by
default makes fast-Expression artificially expensive), but the triad is
the right axis-set to negotiate them.

## 3.7 "Decline to modulate" must be a first-class routing outcome

A surprising recurring pattern across Modules 1c–1g: **bilateral routing
loses on a meaningful fraction of inputs**. The two clearest categories:

1. **Trivial prompts** — single-call baseline produces the right answer
   in fewer tokens with lower latency. The parser stage is pure overhead.
2. **Cheap baselines that no bilateral can beat on cost** — e.g.,
   `gpt-4o-mini` baseline at $0.000049 (Module 1d), where any 2-call
   bilateral is structurally 10–60× more expensive on input alone.

The wrong response is to call this "LIMBIC's failure mode." The right
response is to make **"dispatch single-call baseline"** a first-class
routing outcome equal in standing to bilateral. LIMBIC's *first*
decision is whether to modulate at all.

Implications for the staged build path (§5):

- **Module 4 evals must include the no-modulation path explicitly.** If
  baselines and bilaterals are both candidate routes, the eval must
  measure both and let the data choose.
- **The router's policy must include "no-op" routes.** A learned
  dispatcher whose only verbs are "bilateral A→B" cannot represent
  "skip the parser entirely."
- **The cost telemetry must be unified across both modes.** A 1-call
  baseline and a 2-call bilateral need the same accounting shape so
  their costs are directly comparable.

This reframes LIMBIC's value from *"smart bilateral routing"* to
*"smart routing, where bilateral is one of several choices and
sometimes the right choice is no choice at all."*

## 4. The Two-Axis Reduction (for the Module 1b prototype)

The full LIMBIC design has four routing axes (direction, faculty, modality,
cost). For the Module 1b prototype we collapse to two:

| Axis | Values | Purpose |
|---|---|---|
| **Direction (bilateral)** | parser \| composer | Tests the seam — does separating input understanding from output composition produce better/cheaper outputs than monolithic calls? |
| **Speed/depth** | fast \| deep | Tests cost/quality tradeoff per direction. Coarsest possible cost dial. |

Result: 4 configurations (parser ∈ {fast, deep} × composer ∈ {fast, deep}),
plus a baseline single-call run for comparison.

**Faculty and modality are out of scope for 1b.** They re-enter in 1c
(modality, cross-provider) and Module 4+ (faculty classification, telemetry,
evals).

This is deliberate. We're testing whether the bilateral split itself yields
a meaningful cost/quality crossover before we add more dimensions on top.
If 1b shows no benefit, the rest of the design must change.

---

## 5. Build Path

Staged so each step produces standalone value, with LIMBIC emerging from the
accumulation rather than being assembled top-down.

```
Module 1   — bare call (DONE — single provider, single call)
Module 1b  — bilateral split (NEXT — Anthropic only, fast/deep tiers)
Module 1c  — bilateral × cross-provider (parser ∈ Anthropic|OpenAI|Google,
              composer ∈ same; manual modality routing)
Module 2   — memory / multi-turn (single provider)
Module 2b  — provider-agnostic memory (uniform IR across the three labs)
Module 3   — tool use (Anthropic, since their typed blocks are richest)
Module 4   — eval harness with faculty tagging  ←  CRITICAL PREREQUISITE
              (this is where LIMBIC's data starts being collected)
Module 5   — telemetry layer (every call tagged with faculty, modality,
              cost, latency, outcome)
─── now there is data to route on ───
Module L2.1 — rule-based router: hard-coded decision tree on
              modality + length + faculty-hint. No LLM in the routing layer.
Module L2.2 — failure-handling: fallbacks, circuit breakers, retries.
Module L3.1 — LIMBIC v0: faculty classifier + cost-aware bilateral router
              composed on top of L2.1/L2.2.
Module L3.2 — LIMBIC v1: empirical routing policy fitted from
              Module-4 telemetry (replaces hand-coded rules with learned
              dispatch).
```

The crucial insight: **everything before Module 4 is generating the data
LIMBIC needs to be built well.** Skipping ahead to L3.1 means hand-coding a
policy that the data would have told us — and probably hand-coding it
wrong.

---

## 6. Open Questions

These do not yet have good answers. Each is a deferred decision; each will
need a real answer before LIMBIC v0 ships.

1. **What is the IR between parser and composer?** Free-text "structured
   analysis"? Typed schema (JSON with named fields)? Embedding + extracted
   key facts? Each choice has tradeoffs in expressiveness, model-friction,
   and adapter cost.

2. **How does LIMBIC handle multi-turn conversations?** Each turn has its
   own routing decision, but earlier turns' choices affect later context.
   Does the *parser* see prior turns? The *composer*? Both? At what cost?

3. **When do faculties compose vs sequence?** A turn that requires
   perception *and* abduction — does LIMBIC dispatch them in parallel
   (both models see the prompt) or in series (perception's output feeds
   abduction's input)? Probably workload-dependent.

4. **What's the unit of routing — turn, step, or token?** Turn-level
   routing is what's described above. Step-level (intra-turn tool calls
   routed independently) is more powerful but more complex. Token-level
   (mid-generation handoff) is research, not engineering.

5. **How does LIMBIC degrade gracefully?** If only one provider is up,
   does LIMBIC fall back to single-provider single-call mode? Does it
   refuse modalities it can't serve? What's the user-visible behavior?

6. **What's the right boundary between LIMBIC and the application?** Is
   LIMBIC a library imported by the app, a sidecar service, a gateway?
   Each affects deployment story and observability.

---

## 7. Closing

LIMBIC is not too much complication *as a goal*. It is too much complication
*as the next thing to build*. The novelty (bilateral split, faculty
awareness, modality routing) is real. The engineering depth (IR design,
failure handling, faculty classification) is also real.

The right path is incremental, evidence-driven, and deferred. Build the
primitives that LIMBIC will route over. Generate the data that LIMBIC will
route on. Then assemble the router from parts whose behavior is already
understood.

Module 1b is the first test of the most novel piece. Everything else
follows from what it shows.
