# Module 3 — The Three-Phase Loop, By Hand

> **Curriculum:** Movement One, Module 3 — *The Three-Phase Loop, By Hand*. See [`docs/curriculum.md`](../../docs/curriculum.md#module-3--the-three-phase-loop-by-hand) and [`docs/treatise.md`](../../docs/treatise.md) Part II (Metabolic Anatomy).

**Goal:** implement Read → Think → Act explicitly. This is the kernel of every
agent. The model's text stops being the answer and becomes a **decision the loop
parses and acts on**.

The diff against Module 2 is the **ACT** phase: where M2 printed the model's
text, M3 parses it for an `ACTION: verb(arg)`, dispatches, and (for tool calls)
loops with the result fed back.

## The lesson is the brittleness

The model is a text generator; "structured output" here is a *fiction you impose
with a regex*. That fiction breaks — the model adds commentary, malforms the
call, or invents an action you never defined. `parse_action()` is the seam where
it breaks, and the loop's recovery nudge is how you live with it. Module 4
replaces this hand-rolled grammar with the provider's native tool calling, and
you feel exactly what that buys.

## Documented learning — a conversation *turn* vs. a goal-oriented agent *loop*

*(Captured 2026-05-26, from working the distinction through by hand. This is the
conceptual core of why M3 ≠ M2.)*

Module 2 is a **conversation**: take a message, return a response. One inference
pass per turn; control always hands straight back to the user. Module 3 is the
**agent loop**: the model's output stops being *the answer* and becomes *a
decision the loop acts on*, and the model can choose to **keep the loop spinning**
before it answers. That choice — to retain control and take another step — is the
whole difference between a chatbot and a goal-oriented agent.

The precise mechanics, stated exactly (the easy mental models are subtly wrong):

1. **The model *requests*; the harness *acts*.** An inference pass emits a
   decision (`ACTION: verb(arg)`). The model can't run anything — the harness
   executes the tool and feeds the result back. The model decides; the machine is
   the hand. (The model↔harness seam: the model never touches the world.)

2. **Every inference pass is the *same* operation — "produce a decision."** There
   is no special "think pass" and separate "answer pass": each pass just emits an
   action. The pass we casually call "the response" is simply the one whose chosen
   verb happens to be `answer`. All the loop's structure comes from *which verb*
   each identical decision names; a tiny router does the rest.

3. **Terminal conditions = "where does control go next."**

   | verb | control goes | loop |
   |---|---|---|
   | `answer` | outward, to the user (goal reached) | **stops** |
   | `ask` | outward, to the user (needs info) | **stops** |
   | `calculate` (any tool) | inward, to a tool then back to itself | **continues** |
   | *(none)* | `max_iterations` guard trips | **stops** (by exhaustion) |

   An agent *is* precisely the thing that can choose to keep control inward and
   take another step. `ask` completing the turn the same way `answer` does is the
   tell: the loop's real axis is *hand-off vs. keep-spinning*, not *done vs.
   not-done*.

4. **One user turn = N inference passes**, each `Read → (model) Think →
   (harness) Act → Observe`, looping while control stays inward and ending when it
   yields outward (or the guard trips). N = 1 for a direct answer, 2 for one tool
   round-trip, more for chained tool use.

**"Isn't think→act just a clever way to *measure* one response?"** Within a single
pass — yes. Splitting one generation into "think" then "act" is a framing we
impose; the model emitted one decision and the parse is deterministic. But
*across* passes it is **not** measurement: when the action is a tool, the harness
does something the model cannot (exact arithmetic, fetch, side effect) and
**injects information the model did not have** into the next pass. That next pass
is a genuinely new measurement on new evidence — not the first one re-labelled.

In the [`measurement-seam`](../../docs/measurement-seam.md) vocabulary: a turn is
**not one measurement split into think+act — it is a _chain_ of measurements,
linked by external acts**, each measurement's output triggering an operation in
the world whose result conditions the next. The conversation loop (M2) is a chain
of length one that always hands back; the agent loop (M3) is a chain the model can
*extend* until its goal is met.

## Documented learning — why hand-parsing was always a stopgap

*(Captured 2026-05-27.)*

M3 layers a **deterministic parser on a probabilistic substrate** — a regex
contract over stochastic text. That compounds two fragilities at once: the model
can phrase the action countless ways, and any drift breaks the parse — so the
failure rate **grows with every tool and every turn**. The `parse_action()`
recovery nudge papers over it; it does not fix it. On an inherently probabilistic
generator, a brittle deterministic contract was never going to hold.

This is *why* the real world abandoned hand-parsing the instant native structured
calls arrived. **ReAct survives** as the Reason→Act skeleton; what evolved is the
*Act* — its determinism climbed `text → function → schema → protocol → bundle`.
The full ladder (function call → schematic call → standardized protocol/MCP →
bundled invocations/Skills) is captured in
[Module 4's "evolution of the Act"](../module_04_native_tools/README.md#documented-learning--the-evolution-of-the-act).

## Run

```sh
# calculate -> answer (watch the two iterations + the tool feedback)
python level_1_modules/module_03_three_phase/three_phase.py "What is 17% of 240, plus 13?"

# ambiguous -> ask
python level_1_modules/module_03_three_phase/three_phase.py "If I split the bill evenly, how much does each pay?"

# direct -> answer
python level_1_modules/module_03_three_phase/three_phase.py "What is 12 times 12?"
```

stderr shows each phase: `READ (n msgs) → THINK (text) → ACT -> verb(arg) [status]`,
and `calculate(...) = result` when the tool runs. stdout carries the final
`[ANSWER]` / `[ASK]`.

## The three actions

| Action | Effect |
|---|---|
| `answer(text)` | terminal — hand to the user, stop |
| `ask(question)` | terminal — we need the user, stop |
| `calculate(expr)` | run the (real, AST-safe) arithmetic tool, feed the result back, **loop** |

## Pitfalls deliberately within reach

- **Force a parse failure.** Loosen the system prompt so the model adds prose
  around the ACTION, and watch `parse_action` fall back to the recovery nudge.
- **Invented action.** Ask something that tempts a `search()` or `lookup()` it
  doesn't have; see `status="unknown_action"` and the correction loop.
- **Infinite loop.** Remove `max_iterations` and craft a prompt where the model
  keeps calling `calculate` without ever answering. The guard is why it exists.
- **Tool failure.** Feed `calculate("two plus two")` (non-arithmetic) — the tool
  returns an `ERROR:` string and the model must cope.

## What you should be able to explain

1. What are the three phases, and which line of code is each?
2. Why is the model's output parsed rather than trusted as structured?
3. What are the loop's terminal conditions, and why is `max_iterations` essential?
4. How does a tool result re-enter the loop as the next Think's input?
5. What happens on a parse failure or an invented action — and why nudge rather
   than crash?

When you can answer all five, you're ready for Module 4 (native tool calling),
where the parsing fiction becomes a real contract.

## Observability

The loop emits the same `observer(event, payload)` events as the Module 2 kernel
(`run_start`, `read`, `think`, `action`, `tool_result`, `parse_recovery`,
`done`), so the Witness (`level_2_strings/string_02_witness/`) attaches to it the
same way — the Actions/phases panel lights up from these events. Module mode
`M3` in the witness routes the conversation through this agent.
