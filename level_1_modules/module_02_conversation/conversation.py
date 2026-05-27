"""Module 2 — The Conversation Loop.

Module 1 was one call: prompt in, text out, no memory. This module changes
exactly one thing, and that one thing is the entire lesson:

    you carry the history.

The model is still stateless (Module 1's hard-won fact). It remembers nothing
between calls. So a "conversation" is an illusion you maintain by hand: a list
of messages that you grow every turn and re-send in full on every call. The
model never sees the past — it sees a transcript you hand it, fresh, each time.

Two consequences fall out of that single fact, and they are the reason context
management is the central engineering problem of this whole field:

  1. The list grows without bound. Every turn appends two messages (yours and
     the model's), and every turn re-ships the WHOLE list. Input tokens — which
     you pay for — climb turn over turn even when your messages stay short. You
     are paying, repeatedly, to re-tell the model everything it "already knows."

  2. Eventually the list won't fit. Each model has a context window. Cross it
     and the API errors. Before you cross it, you must decide what to keep,
     what to throw away, and what to compress. This module implements the
     cheapest such strategy — summarize-and-compact — and shows that it is
     itself a lossy, paid operation. There is no free memory.

Read top to bottom. The diff against `module_01_bare_call/bare_call.py` IS the
lesson: a `messages` list that persists across calls, and the machinery to keep
it from eating you alive.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic
from dotenv import load_dotenv


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Same as Module 1: keys and model come from the environment, never from source.
load_dotenv()

# Pricing snapshot for Sonnet 4.6 as of 2026-04. Verify against
# console.anthropic.com before trusting these. We print cost so the "input
# tokens climb every turn" effect is something you feel in dollars, not just
# a number you're told about.
PRICE_PER_MTOK_INPUT = 3.00    # USD per 1,000,000 input tokens
PRICE_PER_MTOK_OUTPUT = 15.00  # USD per 1,000,000 output tokens

DEFAULT_MODEL = "claude-sonnet-4-6"

# When the MEASURED context (the input_tokens the server charged us on the last
# turn) crosses this line, we compact before the next turn. Default is low on
# purpose so you can trigger compaction inside a short demo session. Real
# windows are 100k+; the lesson is the *mechanism*, not the number. Override
# with HARNESS_COMPACT_AT to watch it fire after 2-3 turns.
DEFAULT_COMPACT_AT_TOKENS = 2000

# How many of the most recent turns to keep verbatim when we compact. Recent
# turns carry the live thread of the conversation; older turns get distilled
# into a summary. This is the crudest possible "what to keep" policy — and the
# fact that it's a *policy*, a judgment call with consequences, is the point.
DEFAULT_KEEP_LAST_TURNS = 2


# ─────────────────────────────────────────────────────────────────────────────
# Per-turn telemetry
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class TurnResult:
    """What one turn of the conversation cost and produced.

    Note `context_tokens`: this is `input_tokens`, renamed to make the point
    that on turn N the "input" is the ENTIRE conversation so far, not just the
    user's latest line. Watching this field climb is the module's core demo.
    """

    text: str
    context_tokens: int   # == input_tokens: the whole history we shipped
    output_tokens: int
    latency_seconds: float
    cost_usd: float
    compacted: bool = False  # did we summarize-and-shrink before this turn?
    thinking: str = ""       # the model's chain-of-thought, if thinking is on


# ─────────────────────────────────────────────────────────────────────────────
# The conversation — a list you carry, and the machinery to keep it bounded
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Conversation:
    """A multi-turn conversation against a stateless model.

    The ONE field that didn't exist in Module 1 is `messages`. Everything else
    in this class exists to serve it: to grow it (`send`), to measure it, and
    to stop it from growing forever (`compact`).
    """

    system: str | None = None
    model: str = DEFAULT_MODEL
    max_tokens: int = 1024
    temperature: float = 0.0
    compact_at_tokens: int = DEFAULT_COMPACT_AT_TOKENS
    keep_last_turns: int = DEFAULT_KEEP_LAST_TURNS

    # Token budget for the summary the compactor produces. Lower it and the
    # summary MUST drop detail — the lever the compaction-loss demo turns to
    # force visible forgetting. Real systems tune this against fidelity.
    summary_max_tokens: int = 512

    # ── the Observance seam (treatise Part VII; previews Module 11) ──────────
    # An optional callback the loop fires at every interesting internal moment:
    #   observer(event_name: str, payload: dict)
    # The plain CLI leaves this None, so the loop behaves EXACTLY as before —
    # observability is a thing you attach, never something the kernel pays for
    # when nobody is watching. The witness app (witness.py) attaches one to
    # render the meta-level log, the CoT, and the pre/post-compaction views.
    observer: Callable[[str, dict[str, Any]], None] | None = None

    # Optional extended thinking. Off by default (Module 2's lesson is the
    # loop, not reasoning). When on, the model emits a chain-of-thought we can
    # witness; the API requires temperature=1.0 in that mode, so we force it.
    thinking: bool = False
    thinking_budget_tokens: int = 1024

    # THE memory. In Module 1 this list was rebuilt from scratch on every call
    # and thrown away. Here it persists across calls — and that persistence,
    # nothing more, is what makes a pile of stateless calls into a conversation.
    messages: list[dict] = field(default_factory=list)

    # The last server-measured context size. We use the API's own accounting
    # (Module 1's rule: trust the server, not a client-side tokenizer) to decide
    # when to compact. Set after every send.
    last_context_tokens: int = 0

    # Cumulative ledger, so the cost of "re-sending everything every turn" is
    # visible as a running total, not just a per-call blip.
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0

    # We instantiate the client once and reuse it. (Module 1 made one per call;
    # for a loop, one is tidier. The SDK still reads ANTHROPIC_API_KEY from the
    # environment — we never pass it.)
    _client: anthropic.Anthropic = field(default_factory=anthropic.Anthropic, repr=False)

    def _emit(self, event: str, **payload: Any) -> None:
        """Fire one observability event, if anyone is listening. No-op otherwise."""
        if self.observer is not None:
            self.observer(event, payload)

    # ── sending a turn ──────────────────────────────────────────────────────

    def send(self, user_text: str) -> TurnResult:
        """Append the user's message, ship the WHOLE history, append the reply.

        This is the conversation loop's body. Compare to Module 1's `call_model`:
        the only structural change is that we don't build a fresh one-element
        `messages` list — we append to a list that outlives the call.
        """
        self._emit(
            "turn_start",
            user_text=user_text,
            messages_before=len(self.messages),
            last_context_tokens=self.last_context_tokens,
            threshold=self.compact_at_tokens,
        )

        # Compact BEFORE we add the new turn, if the last turn pushed us over
        # the line. Doing it here (rather than after) means the upcoming call
        # ships the already-shrunk history — you pay the smaller bill on the
        # very next turn, which is the whole point of compacting.
        compacted = False
        if self.last_context_tokens >= self.compact_at_tokens:
            self.compact()
            compacted = True

        # Grow the memory. THIS is the line that didn't exist in Module 1.
        self.messages.append({"role": "user", "content": user_text})
        self._emit("user_appended", messages_now=len(self.messages))

        request: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            # The entire conversation, every time. The API is stateless: this
            # list is the model's complete universe for this call. There is no
            # server-side "session" doing the remembering for you.
            "messages": self.messages,
        }
        if self.system is not None:
            request["system"] = self.system

        # Extended thinking (off by default). When on, the API requires
        # temperature=1.0 and a scratchpad token budget; the model then emits
        # `thinking` content blocks — the chain-of-thought we can witness.
        if self.thinking:
            request["temperature"] = 1.0
            request["max_tokens"] = max(self.max_tokens, self.thinking_budget_tokens + 256)
            request["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget_tokens,
            }

        self._emit("request", num_messages=len(self.messages), thinking=self.thinking)

        # The "alchemy window" from Module 1, now far more instructive: turn on
        # CONVERSATION_TRACE=1 and watch the `messages` array in the request
        # grow turn by turn. The growth you see IS the cost you pay.
        trace = os.environ.get("CONVERSATION_TRACE")
        if trace:
            print("\n--- REQUEST (full history shipped this turn) ---", file=sys.stderr)
            print(json.dumps(request, indent=2), file=sys.stderr)

        started_at = time.perf_counter()
        response = self._client.messages.create(**request)
        elapsed = time.perf_counter() - started_at

        if trace:
            print("\n--- RESPONSE (raw) ---", file=sys.stderr)
            print(response.model_dump_json(indent=2), file=sys.stderr)
            print("--- end trace ---\n", file=sys.stderr)

        text = "".join(b.text for b in response.content if b.type == "text")
        thinking_text = "".join(
            b.thinking for b in response.content if b.type == "thinking"
        )
        if thinking_text:
            self._emit("thinking", text=thinking_text)

        # Append the model's reply, so the NEXT turn includes it. If you forget
        # this line, the model never sees its own prior answers — a classic and
        # baffling bug (the assistant keeps "forgetting" what it just said).
        self.messages.append({"role": "assistant", "content": text})

        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        cost = (
            in_tok * PRICE_PER_MTOK_INPUT / 1_000_000
            + out_tok * PRICE_PER_MTOK_OUTPUT / 1_000_000
        )

        # Update the ledger and the compaction trigger.
        self.last_context_tokens = in_tok
        self.total_input_tokens += in_tok
        self.total_output_tokens += out_tok
        self.total_cost_usd += cost

        self._emit(
            "response",
            text=text,
            context_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            latency_seconds=elapsed,
            total_cost_usd=self.total_cost_usd,
            messages_now=len(self.messages),
            compacted=compacted,
        )

        return TurnResult(
            text=text,
            context_tokens=in_tok,
            output_tokens=out_tok,
            latency_seconds=elapsed,
            cost_usd=cost,
            compacted=compacted,
            thinking=thinking_text,
        )

    # ── keeping the list bounded ──────────────────────────────────────────────

    def compact(self) -> None:
        """Summarize the older turns into one message; keep the recent ones raw.

        This is the curriculum's "summarize and compress" made concrete. Note
        three things it teaches:

          1. Compaction is LOSSY. The summary is a smaller, blurrier copy of the
             past. Whatever the summarizer drops, the conversation has now truly
             forgotten — even though, to the user, nothing visibly happened.

          2. Compaction is NOT FREE. We spend a whole extra model call (input +
             output tokens, real dollars) to *save* future tokens. We fold that
             cost into the running total so the trade-off is honest.

          3. Compaction is a POLICY. "Keep the last N turns, summarize the rest"
             is one choice among many (summarize everything; drop instead of
             summarize; keep a rolling summary; semantic dedup). The shape of
             the policy shapes what the conversation can still do later.
        """
        # A "turn" is a (user, assistant) pair = 2 messages. Keep the last
        # `keep_last_turns` of them verbatim; everything before is fair game.
        keep_msgs = self.keep_last_turns * 2
        if len(self.messages) <= keep_msgs:
            return  # nothing old enough to be worth summarizing

        older, recent = self.messages[:-keep_msgs], self.messages[-keep_msgs:]

        self._emit(
            "compaction_start",
            messages_before=list(self.messages),
            summarizing=len(older),
            keeping=len(recent),
        )

        # Render the older turns as plain text for the summarizer to read.
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in older
        )

        # A separate, focused call. This summary is NOT part of the conversation
        # history — it's a tool we run *on* the history. We use temperature 0 so
        # the distillation is as faithful and reproducible as a model gets.
        summary_resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.summary_max_tokens,
            temperature=0.0,
            system=(
                "You compress conversation transcripts. Produce a terse summary "
                "that preserves: facts established, decisions made, names and "
                "identifiers, user preferences, and any open/unfinished threads. "
                "Drop pleasantries and filler. Write in the third person as notes."
            ),
            messages=[{"role": "user", "content": transcript}],
        )
        summary = "".join(
            b.text for b in summary_resp.content if b.type == "text"
        )

        # Pay for the compaction. Saving tokens later costs tokens now.
        s_in, s_out = summary_resp.usage.input_tokens, summary_resp.usage.output_tokens
        self.total_input_tokens += s_in
        self.total_output_tokens += s_out
        self.total_cost_usd += (
            s_in * PRICE_PER_MTOK_INPUT / 1_000_000
            + s_out * PRICE_PER_MTOK_OUTPUT / 1_000_000
        )

        # Rebuild the history: a synthetic exchange that injects the summary as
        # context, then the recent turns verbatim. We use a user/assistant pair
        # (not the system prompt) so the persona in `system` stays clean and
        # stable, and so the alternation the API expects is preserved.
        primer = [
            {
                "role": "user",
                "content": (
                    "Summary of our conversation so far:\n\n"
                    f"{summary}\n\n"
                    "Continue naturally from here."
                ),
            },
            {"role": "assistant", "content": "Understood — I have the context."},
        ]
        self.messages = primer + recent

        self._emit(
            "compaction_done",
            summary=summary,
            messages_after=list(self.messages),
            old_count=len(older),
            summary_in_tokens=s_in,
            summary_out_tokens=s_out,
            cost_usd=(s_in * PRICE_PER_MTOK_INPUT + s_out * PRICE_PER_MTOK_OUTPUT) / 1_000_000,
        )

        # The next send() will re-measure the (now smaller) context, so reset the
        # trigger to a value below the threshold to avoid compacting again
        # immediately on the next turn.
        self.last_context_tokens = 0

        print(
            f"\n[compacted: {len(older)} old messages → 1 summary "
            f"({s_in}+{s_out} tok, ${(s_in*PRICE_PER_MTOK_INPUT + s_out*PRICE_PER_MTOK_OUTPUT)/1_000_000:.6f}); "
            f"kept last {self.keep_last_turns} turns verbatim]",
            file=sys.stderr,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLI — a REPL chatbot
# ─────────────────────────────────────────────────────────────────────────────

_HELP = """\
Commands:
  /exit, /quit   end the conversation
  /dump          print the raw messages list (the memory you carry)
  /compact       force a summarize-and-compact right now
  /help          show this
Anything else is sent to the model as your next turn.
"""


def _telemetry(turn_no: int, r: TurnResult, convo: Conversation) -> str:
    """One stderr line per turn. `ctx=` is the star: watch it climb."""
    flag = " COMPACTED" if r.compacted else ""
    return (
        f"[turn={turn_no}{flag} "
        f"ctx={r.context_tokens} out={r.output_tokens} "
        f"cost=${r.cost_usd:.6f} latency={r.latency_seconds:.2f}s "
        f"| cumulative: cost=${convo.total_cost_usd:.6f} "
        f"msgs={len(convo.messages)}]"
    )


if __name__ == "__main__":
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    compact_at = int(os.environ.get("HARNESS_COMPACT_AT", DEFAULT_COMPACT_AT_TOKENS))

    convo = Conversation(
        # A tiny persona so you can watch "personality drift" appear if you
        # were to drop the system prompt (try it — see the README pitfalls).
        system="You are a concise, friendly assistant. Keep replies to a few sentences.",
        model=model,
        compact_at_tokens=compact_at,
    )

    print(f"Module 2 — conversation loop (model={model}, compact_at={compact_at} tok)")
    print("Type /help for commands, /exit to quit.\n", file=sys.stderr)

    turn_no = 0
    while True:
        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()  # newline after ^D / ^C
            break

        if not user_text:
            continue
        if user_text in ("/exit", "/quit"):
            break
        if user_text == "/help":
            print(_HELP, file=sys.stderr)
            continue
        if user_text == "/dump":
            # Show the actual list. This demystifies "memory": it's just this.
            print(json.dumps(convo.messages, indent=2), file=sys.stderr)
            continue
        if user_text == "/compact":
            convo.compact()
            continue

        turn_no += 1
        result = convo.send(user_text)

        # Reply to stdout (pipe-friendly), telemetry to stderr — same split as
        # Module 1, so the program stays well-behaved in Unix terms.
        print(f"bot> {result.text}")
        print(_telemetry(turn_no, result, convo), file=sys.stderr)

    # Final ledger: the whole session's bill in one line. This number is the
    # answer to "what did carrying the conversation actually cost?"
    print(
        f"\n[session over: {turn_no} turns, "
        f"in={convo.total_input_tokens} out={convo.total_output_tokens} "
        f"total=${convo.total_cost_usd:.6f}]",
        file=sys.stderr,
    )
