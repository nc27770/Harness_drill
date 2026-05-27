# Layer 3 — Purpose-built Agents

> **Curriculum:** Layer 3 of the three-layer code organization. See [`docs/curriculum.md`](../docs/curriculum.md#code-organization--three-layers).

**Status:** placeholder. No agents built yet. This directory exists to make
the three-layer organization visible on disk; it will be occupied as the
curriculum reaches the modules whose lessons are full agent loops.

## What lives here

A *Layer-3 agent* is a complete Read-Think-Act loop with tools, memory,
recovery, and a specific use case it serves end-to-end. It uses Layer-1
modules (the seam primitives) and Layer-2 strings (compositions like the
dispatcher) as building blocks, but its top-level shape is the agent loop
itself — not a CLI, not a routing surface.

Examples that would land here once the muscle is built:

- A research-assistant agent (Module 8 supervisor pattern, real use case)
- A persistent-thread chat agent on top of `string_01_dispatch`
- A LangGraph reimplementation of any of the above (Module 13)

## Distinction from Layer 2

- **Layer 2** (`level_2_strings/`) — composition / dispatch. No agent loop.
  The dispatcher in `string_01_dispatch/` routes one request to one module
  and returns. No iteration, no tools, no memory.
- **Layer 3** (here) — full agent loop. Iteration, tools, memory, recovery
  shape the surface. May be built using a hand-rolled `Agent` class
  (Module 5) or a framework (Modules 12–15) once Movement Three is done.

## When to build the first one

Per the curriculum, the natural moment is after Module 5 (the naive agent
class) — the first agent earns its slot here once the kernel is in hand.
Earlier construction is premature; later construction is fine.
