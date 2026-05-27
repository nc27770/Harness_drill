# Module 5 — The Naive Agent Class

> **Curriculum:** Movement One, Module 5 — *The Naive Agent Class*. The close of the kernel: wrap M2–M4 into a reusable object. See [`docs/curriculum.md`](../../docs/curriculum.md#module-5--the-naive-agent-class) and [`docs/treatise.md`](../../docs/treatise.md) Part II.

**Goal:** notice that Modules 2–4 were the same agent written three times, and
extract **one reusable `Agent` object**. This is the moment you've built your own
micro-framework.

## The diff is the wrap

| Module 4 (a script) | Module 5 (a framework) |
|---|---|
| `TOOLS` constant baked into the module | `tools=[Tool(...)]` injected at construction |
| `if block.name == "calculate"` dispatch | generic dispatch via a `{name: fn}` registry |
| a `__main__` you run | an `Agent` you instantiate and reuse |
| one behavior | `run()` (one goal) + multi-turn (history carried on the instance) |

Pass a different `tools` list and the *same* `Agent` class is a weather bot, a SQL
helper, anything. **Tools are data, independent of the agent** — that decoupling
is what makes this a framework, not a program.

## Run

```sh
# one goal
python level_1_modules/module_05_agent/agent.py "What is 17% of 240, plus 13?"
# multi-turn REPL (history carried across turns)
python level_1_modules/module_05_agent/agent.py
```

```python
from agent import Agent, Tool, calculate_tool
a = Agent(system="…", tools=[calculate_tool(), my_other_tool])   # reconfigure by swapping tools
a.run("…");  a.run("…")   # second run continues the same conversation
```

## "Naive" — on purpose

This agent is deliberately the *minimal* reusable kernel:
- **single provider** (Anthropic) wired in (the stretch: abstract it — a tiny LiteLLM);
- **in-memory state** — close the process and the agent is gone;
- **in-process tools** — `Tool.fn` runs in *this* process, so a raising tool would
  crash the agent.

Those three naiveties are exactly what **Module 10's durable Mind** fixes
(externalized state, isolated out-of-process tools, resumable across a crash).
Build this first to feel *why* M10 exists — M5 is the agent; M10 is the agent that
outlasts its machine.

## Pitfalls deliberately within reach

- **Hardcode a provider deep in `run()`** — then try to swap; feel why the stretch
  (one interface, many providers) matters.
- **A tool that raises** — give `Tool.fn` a bug; watch it take the whole agent
  down (no isolation here). That crash is M10's motivation.
- **Share one `Agent` instance across two conversations** — the carried `messages`
  bleed together. State lives on the instance; use two instances.

## What you should be able to explain

1. What does the `Agent` hold — config, state, behavior — and which is which?
2. How does generic dispatch work without the agent naming any specific tool?
3. How does a second `run()` continue the same conversation?
4. Name the three ways this agent is "naive," and which Module 10 invariant fixes each.

When you can answer all four, Movement One is complete — you have a micro-framework.

## Observability

Emits the same `observer(event, payload)` events as M4 (`run_start`, `read`,
`think` with `stop_reason`, `tool_use`, `tool_result`, `done`), so the Witness
(`level_2_strings/string_02_witness/`) animates it under module mode `M5` with no
new event handling.
