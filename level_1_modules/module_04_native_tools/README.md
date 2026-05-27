# Module 4 — Native Tool Calling

> **Curriculum:** Movement One, Module 4 — *Native Tool Calling*. See [`docs/curriculum.md`](../../docs/curriculum.md#module-4--native-tool-calling) and [`docs/treatise.md`](../../docs/treatise.md) Part IV (Tools as Motor Organs).

**Goal:** replace Module 3's hand-parsed `ACTION:` grammar with the provider's
**native tool calling**, and feel exactly what it buys. The model returns a
*structured*, schema-validated `tool_use` block; you dispatch and return a
`tool_result` block; you loop on `stop_reason`, not on a regex.

## The diff is the lesson

| Module 3 (by hand) | Module 4 (native) |
|---|---|
| system prompt teaches an `ACTION:` grammar | `tools=[…]` JSON Schema in the request |
| `parse_action()` regex on the model's text | the model returns typed `tool_use` blocks |
| parse failures + recovery nudges | the provider validates the shape — none needed |
| one text reply, hand-parsed | history carries `tool_use`/`tool_result` blocks, distinct roles |
| loop on the verb you parsed | loop on `stop_reason == "tool_use"` |

Same `calculate` underneath. What changed is that the **call mechanism became a
validated contract** instead of text you hope to parse. That's "structured
parsing, for free."

## Run

```sh
# native tool_use round-trip: calculate -> answer
python level_1_modules/module_04_native_tools/native_tools.py "What is 17% of 240, plus 13?"

# ambiguous -> the ask_user tool
python level_1_modules/module_04_native_tools/native_tools.py "If I split the bill evenly, how much does each pay?"
```

stderr shows `THINK [stop_reason]`, `tool_use: name(input)`, `tool_result: …`.
When `stop_reason` is `end_turn`, the text is the answer; when it's `tool_use`,
the loop runs the tool and continues.

## What it costs — the honest trade

Native tools are not free. The tool **schemas** ride in every request, and the
`tool_use`/`tool_result` blocks add structure. In a side-by-side on the same
problem, M4 used ~3× the input tokens of M3's terse `ACTION:` grammar. You pay
those tokens to *buy* reliability: the model is far better at producing a valid
tool call than your homemade format, and you delete the entire parse-and-recover
surface. (Compare the two threads in the Witness index to see it.)

## Documented learning — the evolution of the Act

*(Captured 2026-05-27. ReAct lives on; what changed is how the **Act** is made
reliable on a probabilistic substrate.)*

Module 3 layered a **deterministic parser on top of a probabilistic generator** —
a regex contract over stochastic text. That is rung zero, and it was always a
stopgap: the model can phrase an action a hundred ways, any drift breaks the
parse, and the fragility **compounds** with every tool and every turn. Recovery
nudges only paper over a failure rate that grows. The field abandoned it the
instant a structured alternative existed — that jump *is* M3 → M4.

What endures is **ReAct** — *Reason → Act* — the cognitive skeleton. What has
*evolved* is the **Act half**: how the action is made deterministic. The ladder:

| rung | mechanism | who enforces the shape | ~era |
|---|---|---|---|
| 0 | hand-parsed text (M3) | *your* regex — brittle | ReAct, 2022–early '23 |
| 1 | **function call** | the provider, against a function signature | OpenAI, 2023 |
| 2 | **schematic call** (M4) | strict JSON-Schema tool contracts; typed `tool_use`/`tool_result` | 2023–24 |
| 3 | **standardized protocol** (MCP) | a shared protocol — tools become discoverable, reusable servers | Nov 2024 |
| 4 | **bundled invocations** (Skills) | packaged capabilities (instructions + tools + resources) loaded on demand | 2025 |

The through-line: the **Reason** half — the model choosing *what* to do — barely
changed; the **Act** half climbed a determinism ladder, `text → function →
schema → protocol → bundle`, each rung pulling more brittleness out of the seam
that a stochastic model otherwise forces on you. M3 is rung 0 *on purpose*: you
build it once to feel exactly why every rung above it had to exist.

## Pitfalls deliberately within reach

- **Vague tool description.** Blank the `calculate` description; watch the model
  misuse it or stop calling it. The description *is* the model's manual.
- **Wrong `tool_result` shape.** Return a dict where a string is expected, or
  forget the `tool_use_id`; the API rejects the turn. The contract cuts both ways.
- **Dangling `tool_use`.** Terminate a run with a `tool_use` in history but no
  matching `tool_result`, then send another turn — the API errors. (That's why
  even the terminal `ask_user` gets a `tool_result` here.)
- **`tool_choice`.** Add `tool_choice={"type":"any"}` and the model is *forced*
  to call a tool even when it should just answer. Policy lives here.

## What you should be able to explain

1. Where did the regex go, and what replaced it?
2. What does `stop_reason == "tool_use"` tell you, and what drives the loop now?
3. Why must the assistant's `tool_use` be appended to history *before* its
   `tool_result`?
4. Why does even a terminal `ask_user` still get a `tool_result`?
5. Why does M4 cost more tokens than M3 — and why is that often worth it?

When you can answer all five, you're ready for Module 5 (wrap this loop into a
reusable `Agent` class — your own micro-framework).

## Observability

Emits `observer(event, payload)` events — `run_start`, `read`, `think`
(with `stop_reason`), `tool_use`, `tool_result`, `done` — so the Witness
(`level_2_strings/string_02_witness/`) attaches the same way it does for M3.
Module mode `M4` routes a turn through this agent.
