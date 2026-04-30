# Framework potential — trust, verification, accountability

> **Status:** Documented framing of what Harness Drill prepares the
> builder for, on the framework-author axis. Not a build plan. Useful
> as input if the curriculum's substrate is ever projected forward
> into a domain-specific framework where deep state management,
> verification, accountability, and trust are load-bearing.

## Subject

Completing the curriculum makes you framework-author-level on the
*harness* axis. That is the curriculum's terminal goal — Module 5
literally builds your own micro-framework by hand, and Module 12
positions LangGraph as a thing to compare against your own work, not
a thing to learn first. The 8 Deeper Territories add the disciplines
(state design, inter-agent protocols, failure modes, evals, cost) a
framework author needs.

This document maps where that substrate is **load-bearing for**
domains demanding deep state management, verification, accountability,
and trust — and where the curriculum stops short of those disciplines
as separate territories that would attach to the harness rather than
live inside it.

## Companion docs

- [`curriculum.md`](../curriculum.md) §"Movement Two" / §"The Eight Deeper
  Territories" — the harness-side coverage.
- [`treatise.md`](../treatise.md) Parts III, IV, VI, VII — state, tools,
  continuity, observance, all of which a trust framework rests on.
- [`measurement-seam.md`](../measurement-seam.md) — the seam framing that
  makes refusal-as-typed-outcome a first-class concept rather than an
  exception path.
- [`limbic-design.md`](../limbic-design.md) — forward-design for the
  multi-axis router. A trust framework is the same shape: routing
  decisions tagged by attestation requirements rather than only cost
  and capability.
- [`seam-parameters.md`](../seam-parameters.md) — the discipline of
  separating dispatcher growth from new lessons; the same discipline
  applies to trust-axis growth.

---

## What the curriculum prepares you to author

By Module 5 you have written your own micro-framework. By Module 11
you have written your own observability layer. By Module 13 you can
read LangGraph source critically. The disciplines that distinguish
*framework author* from *framework user* are exactly the Deeper
Territories.

| Discipline | Module / Territory | What it gives you |
|---|---|---|
| **State design across 4 temporal layers** | M7, DT2 | Working / episodic / session / long-term as distinct primitives, not conflated |
| **Persistence and checkpoint-and-resume** | M10 | Resumable agents are not a feature, they're a kernel property |
| **Designed pauses / human-in-loop gates** | M14 | Pause as state, not event |
| **Inter-agent communication protocols** | DT3 | Protocol design, distinct from API design |
| **Tool design discipline** | DT4 | What models need from tools to use them well |
| **Failure modes and recovery** | DT7 | Operational reality of agents in production |
| **Observability** | M11, DT6 | Per-Think / per-loop / per-session traces; eval as continuous engineering |
| **Cost engineering** | DT8 | Cost as architectural concern |

That set is the harness-engineering substrate every agentic framework
rests on. After completing the curriculum you can design the
abstractions, not just consume them.

---

## Where the curriculum stops short for trust-anchored domains

Trust, verification, and accountability are not single missing pieces
— they are *adjacent disciplines* that attach to the harness layer.
The curriculum is non-adversarial by design. It assumes benign users
and cooperative models. Trust-demanding domains require capabilities
the curriculum touches but does not develop into territories of their
own.

| Capability | Curriculum coverage | Gap to fill |
|---|---|---|
| Deep state management | Strong — M7, M10, DT2 | None worth naming. |
| Observability / replay | Strong — M11, DT7 | Cryptographic chain-of-custody; immutable audit logs. |
| Eval / regression | Partial — DT6 | Formal property-based testing; semantic invariants; safety cases. |
| Recovery / fallback | Partial — DT7 | Multi-party attestation; designed graceful degradation under partial trust. |
| Policy enforcement | Touched — M14 designed pauses | Constitutional behavior at the harness layer (not only at the model). |
| Adversarial robustness | Absent | Red-teaming as continuous discipline; prompt-injection containment. |
| Provenance / attribution | Absent | Cryptographic signing of model outputs; citation enforcement. |
| Regulatory grounding | Absent | HIPAA / SOC2 / EU AI Act / FedRAMP-specific harness primitives. |
| Formal methods | Absent | Property-based testing of agent behaviors; safety cases. |

The harness fluency built by the curriculum means you know exactly
*where in the harness* each of these primitives attaches. That is the
framework-author advantage. The disciplines themselves — formal
methods, adversarial robustness, regulatory engineering — are
adjacent fields, deliberately scoped out of the curriculum.

---

## The market shape today (April 2026)

Two distinct tool categories, neither solving the trust problem at
the kernel level:

- **General-purpose orchestration frameworks** — LangGraph, AutoGen,
  CrewAI, Strands, Anthropic Agent SDK. Trust is not a kernel
  concept; it is an application-layer concern callers must engineer
  themselves.
- **Bolted-on observability / eval tools** — LangSmith, Langfuse,
  Patronus, Braintrust, Galileo. These sit *outside* the harness,
  observing it. Audit and verification are *post hoc*, not
  load-bearing in the control flow.

The gap is a framework where **trust, verification, and
accountability are load-bearing in the kernel, not layered on top.**
Concretely:

- Audit trails as a state primitive, not a logging concern.
- Policy gates as first-class control-flow nodes, not middleware.
- Provenance as a typed field on every model output, not an
  annotation.
- Refusal-as-typed-outcome (already built in 1j/1l) generalized to a
  whole vocabulary of trust-relevant terminal states (`refused`,
  `attested`, `requires_review`, `policy_violation`,
  `provenance_broken`, etc.).
- Multi-party attestation as a graph-edge type, not custom plumbing.

---

## Domains where this is underserved and procurement-ready

| Domain | Trust demand | Current gap |
|---|---|---|
| **Healthcare** | HIPAA, FDA SaMD, clinical liability chains | Vertical SaaS; no harness-level trust framework |
| **Legal** | Privilege preservation, mandatory citation, hallucination consequences | LLM-with-citations products; no framework with privilege as a kernel primitive |
| **Finance** | Audit trails, fiduciary duty, model risk management (SR 11-7, EU MiFID) | Compliance bolted onto general LLM frameworks |
| **Defense / intelligence** | Provenance, classification, multi-level security | Effectively no public framework; bespoke per-program |
| **Critical infrastructure** | Safety cases, formal methods, ISO 26262-style assurance | LLM-in-the-loop is mostly research, not productized |

These domains have procurement budgets that do not look like the SaaS
market. They are framework-shaped opportunities, not product-shaped
ones, because each enterprise needs to compose their own application
on top of trust primitives they trust.

---

## How LIMBIC's design generalizes here

[`limbic-design.md`](../limbic-design.md) sketches a multi-axis router
(direction × faculty × modality × cost). A trust framework is the
same shape with one axis swapped: **direction × faculty × modality ×
attestation-class**. Every routing decision LIMBIC makes for cost can
also be made for *required attestation level*.

That isomorphism means:

- The dispatcher in
  [`string_01_dispatch`](../../level_2_strings/string_01_dispatch/) is
  already the right architectural shape for a trust router; it just
  needs an attestation axis added to its capability matrix.
- The "decline to modulate" first-class outcome
  ([`limbic-design.md` §3.7](../limbic-design.md)) generalizes directly
  to "decline to dispatch — escalate to human review" as a typed
  terminal state.
- Refusal-as-typed-outcome (already wired into 1j/1l per
  [`measurement-seam.md`](../measurement-seam.md)) generalizes to a full
  vocabulary of policy-driven terminal states.

The curriculum's substrate — including the LIMBIC forward design and
the seam-parameter discipline — already has trust-framework shape.
What's missing is the trust discipline itself, and that gap is
*studyable*, not *architectural*.

---

## Honest single-line summary

The curriculum puts you at framework-author level for the **harness**
layer, which is the substrate every domain-specific trust framework
needs. Trust / verification / accountability primitives are adjacent
disciplines you'd add deliberately. The framework you build will not
be a clone of LangGraph with policy middleware bolted on — it will be
a kernel where trust is structural.
