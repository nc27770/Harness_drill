# Creator Role & Instantiation — what M6–M11 unlock, and how we reasoned to the goal

*(Forward framing, 2026-05-27. The **charter statement** lives in meta-agent `docs/MOTHERSHIP.md` §7 + P18; this doc records the **derivation** — why the goal sits where it does. Epistemic frame: [`../epistemic-engineering.md`](../epistemic-engineering.md).)*

## The goal (stated first)

The Master is, at the top, a **creator**. It brings into being three things — and a fourth that watches:

| Creation | Is | Curriculum | Status |
|---|---|---|---|
| **Player** | the being/agent (the canonical mind) | M1–M5 + M10 | ✅ built |
| **Playfield** | the environment: *world from outside* (M6) + *self memory* (M7) | M6 + M7 | next |
| **Game** | inter-player dynamics — the shared world where players couple | M8 + M9 | pending |
| **Observance** | the witness over the play | M11 | ✅ visited |

The **apex**, deferred until those are built: a **declarative being-manifest + a universal instantiator** that *grows a being from a declared genome* rather than assembling one in code and invoking it.

## How we reasoned to it (the derivation)

1. **The inventory.** Building the canonical agent, we made nearly everything declarative: identity / purpose / DNA (config), tools (motor organs), and the body (resources, via templatized IaC). **Code was the lone holdout** — because code *is* how the runtime works.
2. **The aspiration.** Make code declarative too — so the *whole* being is declared, not hand-assembled.
3. **The clarification (a fork avoided).** "Declarative" here does **not** mean declarative-*programming* style (pure, effect-free) — that loses full capability. It means: take an **imperative, full-capability program** and make *it* a **declared, addressable artifact** — its internals stay imperative; its *binding* becomes declarative. The model is Kubernetes: a Pod spec (declarative) references a container *image* (imperative code, packaged). meta-agent already does this for the **body**.
4. **Invocation vs. instantiation.** *Invocation* calls a thing assembled in code. **Instantiation** grows the being from its genome (the manifest) — morphogenesis: DNA + body + nervous-system-code + motor organs + memory, all resolved from one declaration.
5. **The irreducible residue.** Code can never be *fully* declarative: there is always an interpreter at the bottom (the bottom turtle). Here it is precisely the **instantiator** — it cannot live in the manifest it reads (the bootstrap). And that residue **is the true harness / the seam** — the part that can't be declared away is, by construction, the machine↔model boundary the whole project hunts.
6. **The sequencing principle.** *You cannot design the genome until you have discovered all the organs it must declare.* The manifest must declare world-knowledge, memory, inter-player coupling, and observance — so **M6/M7 → M8/M9 → M11 come first; the creator/instantiator is designed last**, with full knowledge of what it composes.

## The shape that repeats (the unifying observation)

Each creation splits into a *combinable mechanical layer* (where engineering succeeds) and a *deferred epistemic frontier* (where it must become **epistemic** engineering):

| creation | mechanical (combinable) | epistemic frontier (deferred) |
|---|---|---|
| **playfield** (M6/M7) | retrieval / recall | the **sufficiency gate** (the North Star) |
| **game** (M8/M9) | topologies (message-passing patterns) | the **shared reference / collective state** — does the *group* know enough? |
| **creator** | assembly / binding | the **being-manifest + universal instantiator** + code-artifact trust |

So M6/M7 *combine* (one retrieval/recall faculty feeding the perception edge, parameterized by `origin: world | self`); M8/M9 *combine* (topologies = orchestration policies over one substrate — and that substrate is **already built in meta-agent**: spawn, address, message-pass, lifecycle); and the creator's apex is the being-manifest. In every case the combinable mechanics are the easy half; the frontier is the work.

## The convergence

The being-manifest is where the **two repos meet**: meta-agent's body-spawn (IaC + image) ⊕ Harness_drill's mind-SCHEMA (config + state + tools) → **one being-manifest** `{DNA + state + tools + code-as-artifact + IaC}`, resolved by one instantiator. Hard parts to face *then*: code-artifact **trust/provenance** (injected code is *means*; it must not smuggle *ends* past the constitutional lock), **ABI stability**, and **runnability resolution**.

## Status / next

Deferred to **post-M11**. Next: **M6/M7 together**, under the sufficiency North Star — the playfield, with the sufficiency-gate as the real content.
