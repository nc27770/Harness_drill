# Epistemic Engineering — The Sufficiency Frontier

**Subject:** the North Star for Movement Two (Modules 6–7 and beyond). Everything
through Module 5 (the loop) and Module 10 (the durable Mind) is *harness* —
engineering with no epistemic content. This document names what comes after, and
insists it is **not** a retrieval problem.

**Companion docs:**
- [`measurement-seam.md`](measurement-seam.md) — the seed: frozen-weight inference as a *measurement act*. This doc takes the next step the seam doc does not: a measurement is an **instrument reading**, so engineer it like metrology, not like a function.
- [`treatise.md`](treatise.md) Part II (metabolic anatomy) and Part VII (observance).
- [`../level_1_modules/module_10_persistence/SCHEMA.md`](../level_1_modules/module_10_persistence/SCHEMA.md) — the ontological lock and the faculty ontology this doc builds on.
- meta-agent `docs/MOTHERSHIP.md` — the **constitutional** charter; §"The constitutional floor" states the means/ends principle that §6 below depends on.

---

## 0. The harness is solved; the frontier is sufficiency

Map the agent biologically — model = brain, machine = body/metabolism, code =
nervous system, configuration = DNA (read-only to the soma — the ontological
lock), persistence = the *substrate* of memory, tools = motor organs. Every one
of those is **engineering**: it moves, stores, routes, and acts on tokens. None
of it *knows* anything. The only locus of knowing is the model's weights
(training-time) plus the context (situated, this session).

So the post-Module-5 frontier is not a missing organ. It is a single question the
organs cannot answer: **does the mind know *enough* — about itself and about the
world — to reason and act, or must it go get more?** That is the **sufficiency**
judgment, and it is where engineering succeeds on paper and fails epistemically.

## 1. Sufficiency is a prior, not a volume

The industry's answer to context is *throw* — bigger windows, more retrieval,
cleverer compression. All of it addresses **volume**. Sufficiency is not a volume
problem. At infinite context, with nothing ever compacted away, the mind still
has no way to know whether what it holds is *enough* to decide. Sufficiency is a
**prior** — a belief about the adequacy of one's own knowing — and no amount of
holding capacity supplies it. (Module 2's compaction merely *leaked* the issue
through a mechanical token threshold; remove the threshold and the problem is
untouched, not solved.)

## 2. The prior cannot be installed — only a process can

A prior is a belief held *before* evidence. But for an open world, adequacy often
cannot be known before acting: you do not know whether you know enough until you
try (and the **self is partly opaque** — a mind cannot introspect its own weights,
only its config and its transcript; competence is discovered behaviorally). So
"hand the mind a sufficiency prior" is the wrong object. What can be installed
from outside is a **process**: a loop that acts tentatively, lets the world talk
back, and *earns* "enough / not-enough" as a **posterior**. This is exactly what
RL does — sufficiency learned from reward — and exactly what a frozen model cannot
do in-session. Tool use is the embryo: when the mind distrusts its own arithmetic
it externalizes the check; `calculate()` is sufficiency outsourced to a verifier.

## 3. The verifiability split — where the process works, and where it can't

The acting-and-being-corrected loop calibrates **only where the world offers a
cheap, truthful verifier**: arithmetic, code that runs, a fact that can be
retrieved and checked. There is no `calculate()` for *judgment, intent, value,*
or *"do I understand this person well enough."* The flood of retrieval
architectures works precisely in the verifiable quadrant — which is why it looks
like progress — and leaves the unverifiable quadrant untouched. The million cuts
are all on one side of a line the field does not name.

## 4. Why no guarantee is possible — defeasibility

Software engineering stands on a tower of guarantees: sugar → AST → IR → ISA →
bytecode, each layer a *monotone, meaning-preserving lowering with a checkable
proof*. Knowing has no such tower, because justification is **defeasible** —
non-monotonic: new evidence can overturn a belief. (Train a model that 2+2=5 and
the weights hold no *defeater*; abduction — best-fit to samples — has no floor
that says "this could be wrong.") You cannot build a guarantee stack on a
defeasible relation. **There is no epistemic compiler** — not for want of tooling,
but as a category fact. This is why engineering cannot *guarantee* sufficiency; it
can only *bound* it.

## 5. The tradition to import — metrology, not the compiler

Engineers reach for the compiler tradition (guarantee) and, finding none, reach
for more retrieval. The wrong instinct. There **is** a human discipline built for
*engineering under irreducible uncertainty with no guarantee at the bottom*:
**metrology and safety-critical engineering** — calibration, error bars,
confidence-gated action, redundancy, fail-safe escalation. They never guarantee a
reading; they *bound* it and gate the decision on the bound. That is the
[`measurement-seam`](measurement-seam.md) made operational: **the model call is an
instrument reading, not a function return.** The industry's root error is the
category mistake — function-call expectations on an instrument — reaching for
retrieval to "fix the value" when the discipline needed is to *characterize the
error and gate on it*. Retrieval enriches the reading; it does nothing for the
error bar.

## 6. Sufficiency = means × ends — and why the bar is constitutional

Sufficiency is never absolute. It is sufficiency *for this decision, at this cost
of being wrong*: the same knowing is enough to guess trivia and catastrophically
short to authorize a payment. So **sufficiency = epistemic state (a *means*) × a
stakes threshold (an *end*).** By the ontological lock (SCHEMA invariant 1), a
mind cannot author its own ends — therefore it *structurally cannot set its own
sufficiency bar*. Where to put the bar is supplied by the creator.

This is the seam where epistemics becomes **constitutional**, and the stakes are
not academic. The industry equates AGI/ASI with a system that can **set its own
objective function**. But a mind that authors its own ends *while lacking any
prior to know its own insufficiency* would act with objective and power on
knowledge it cannot tell is inadequate. That is not error — it is **existential
self-immolation** (of humanity, not the machine). The peril is the conjunction:
self-authored ends **+** structural blindness to one's own insufficiency. Remove
either and it is survivable; together they are not. This is precisely *why* "no
mind authors its own ends" is not a design preference but a **constitutional
floor** — see meta-agent `docs/MOTHERSHIP.md`, §"The constitutional floor."

## 7. The mandate for Modules 6 & 7

Therefore M6 (retrieval) and M7 (memory) are **not** retrieval-plus-storage
plumbing. Built honestly, they are **instrumentation**:

1. **Estimate the confidence of the reading** — treat each model act as an
   instrument output with an error envelope, not a trusted value.
2. **Gate the act on a creator-set stakes threshold** — the bar is an *end*,
   inscribed from outside, never self-authored.
3. **Let the world calibrate where a cheap verifier exists** — earn the posterior
   by acting against arithmetic, code, retrievable fact.
4. **Escalate rather than emit where it does not** — in the unverifiable quadrant,
   the disciplined act is to *decline / ask / hand back*, not to confidently
   produce.

The discipline is not "know more." It is **know your error, and refuse to act past
it.** That is the epistemic engineering the field is not doing — because it grew up
on a tower that never once had an error bar.
