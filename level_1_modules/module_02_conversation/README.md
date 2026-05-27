# Module 2 — The Conversation Loop

> **Curriculum:** Movement One, Module 2 — *The Conversation Loop*. See [`docs/curriculum.md`](../../docs/curriculum.md#module-2--the-conversation-loop) and [`docs/treatise.md`](../../docs/treatise.md) Part III (State as Nervous System).

**Goal:** understand why **context-window management is the central engineering
problem** of agentic systems. You learn it by building the smallest possible
memory — a list you grow by hand — and then watching it try to eat you alive.

The model is still stateless (Module 1's fact). A "conversation" is an illusion
*you* maintain: a `messages` list you grow every turn and re-ship in full on
every call. That single change — a list that persists across calls — is the
entire diff from Module 1, and everything hard about state flows from it.

If you can read every line of `conversation.py` and explain *why* it's there —
especially why `ctx=` climbs every turn and why `compact()` costs money — you've
completed this module.

## Setup

From the repo root (same env as Module 1):

```sh
source .venv/bin/activate
# .env already has ANTHROPIC_API_KEY from Module 1
```

## Run

It's a REPL. Talk to it; watch the stderr telemetry after every turn.

```sh
python level_1_modules/module_02_conversation/conversation.py
```

### 1. Memory is the list you carry

```
you> My name is Alice and I'm building a video pipeline.
bot> Nice to meet you, Alice! ...
you> What's my name and what am I building?
bot> You're Alice, and you're building a video pipeline.
```

Contrast with Module 1, where the second invocation had no idea. Nothing
changed in the *model* — it's still stateless. What changed is that you kept
the first exchange in `messages` and re-sent it. Run `/dump` to see the literal
list. That list **is** the memory. There is nothing else.

### 2. The balloon — watch `ctx=` climb

Every turn's telemetry shows `ctx=` (the input tokens you were charged for):

```
[turn=1 ctx=38  out=22 cost=$0.000... | cumulative: cost=$0.000... msgs=2]
[turn=2 ctx=96  out=30 cost=$0.000... | cumulative: cost=$0.000... msgs=4]
[turn=3 ctx=171 out=18 cost=$0.000... | cumulative: cost=$0.000... msgs=6]
```

`ctx=` grows every turn **even when your message is short**, because you re-ship
the entire history each time. This is the visceral lesson: you pay, repeatedly,
to re-tell the model everything it already "knows." Cost is quadratic-ish over a
long chat. Turn on the trace to watch the request itself grow:

```sh
CONVERSATION_TRACE=1 python level_1_modules/module_02_conversation/conversation.py
```

### 3. Compaction — bounding the list, and paying for it

The default compaction threshold is low (2000 tokens) so you can trigger it in a
short session. To see it fire after just 2-3 turns, set it lower and feed it a
couple of long messages (paste a paragraph or two):

```sh
HARNESS_COMPACT_AT=400 python level_1_modules/module_02_conversation/conversation.py
```

When `ctx=` crosses the line, the next turn compacts first — you'll see:

```
[compacted: 6 old messages → 1 summary (210+88 tok, $0.0019...); kept last 2 turns verbatim]
[turn=4 COMPACTED ctx=140 out=25 ...]
```

Two things to notice and sit with:
- `ctx=` **can drop** after compaction — but only when the summarized turns
  outweighed the ones kept verbatim. In a short session where compaction
  summarizes just one small early turn while keeping two large recent ones,
  `ctx=` may *not* drop (or may even rise from the summary primer). The drop
  materializes over a *longer* chat as many turns pile up behind the kept
  window. (The Witness's `lost-in-the-middle` / `compaction-loss` demo threads
  make this concrete.) The naive "compaction shrinks context" model is
  conditional on *which* turns get summarized — that's the real lesson.
- The summary call **cost tokens** (folded into the cumulative total). You spent
  money *now* to save money *later*. Memory is never free.

Force it manually any time with `/compact`, then ask about something only
mentioned in an early turn — see whether the summary preserved it.

## Pitfalls deliberately within reach

- **Drop the `assistant` append.** Comment out the line that appends the model's
  reply to `messages`. The bot will "forget" everything it just said — it only
  ever sees your messages, never its own. A baffling bug until you see why.
- **Drop the system prompt.** Start the `Conversation` with `system=None`.
  Watch personality drift: with no role-typed anchor, tone wanders turn to turn.
- **Set `keep_last_turns=0` and compact aggressively.** The conversation loses
  its live thread — the model leans entirely on a lossy summary and starts
  contradicting recent turns. This is *why* the policy keeps recent turns raw.
- **Let it run with no compaction on a long chat.** Set `HARNESS_COMPACT_AT`
  very high and keep talking. Watch cumulative cost climb super-linearly, then
  eventually hit the model's context limit and error. That error is the wall
  every memory strategy exists to avoid.

## What you should be able to explain

1. The model is stateless — so where does the conversation's "memory" live?
2. Why does `ctx=` climb every turn even when your messages stay the same length?
3. What breaks if you forget to append the assistant's reply to `messages`?
4. Why does `compact()` run *before* appending the new turn, not after?
5. In what three ways is compaction costly or lossy? (dollars, forgetting, policy)
6. Why is the summary injected as a user/assistant pair rather than into the
   system prompt?

When you can answer all six without looking, you're ready for Module 3 (the
three-phase Read-Think-Act loop, by hand).
