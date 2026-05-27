"""Module 3 — The Three-Phase Loop, By Hand.

Module 2's loop was passive: append, ship the history, print whatever text came
back. The model only ever *talked*. This module changes one thing, and it is the
kernel of every agent ever built:

    the model's text is no longer the answer — it's a DECISION the loop parses
    and acts on.

Read → Think → Act, made explicit and by hand:

  • READ  — assemble the prompt: a system message that teaches the available
            actions and their exact grammar, plus the running history.
  • THINK — one model call. Out comes text containing an `ACTION: verb(arg)`.
  • ACT   — parse that text, dispatch on the verb:
              answer(text)     → terminal: hand it to the user, stop.
              ask(question)    → terminal: we need the user, stop.
              calculate(expr)  → run a tool, feed the result back, LOOP.

The deliberate pain of this module is the parsing. The model is a text
generator; "structured output" is a fiction you impose with a regex, and the
regex breaks — the model adds commentary, malforms the call, or invents an
action you never defined. Producing those failures, then handling them, is the
lesson. Module 4 replaces this hand-rolled grammar with the provider's native
tool calling and you feel exactly what that buys you.

Read top to bottom. The diff against `module_02_conversation/conversation.py`
is the ACT phase: a parse-and-dispatch step where M2 just printed.
"""

from __future__ import annotations

import ast
import json
import operator
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic
from dotenv import load_dotenv

load_dotenv()

PRICE_PER_MTOK_INPUT = 3.00
PRICE_PER_MTOK_OUTPUT = 15.00
DEFAULT_MODEL = "claude-sonnet-4-6"

# The three actions this agent may take. Naming them in ONE place keeps the
# system prompt (what the model is told) and the dispatcher (what the loop
# accepts) honestly in sync — drift between those two is a classic bug source.
ACTIONS = ("answer", "ask", "calculate")

# The grammar we ask the model to emit, taught by example in the system prompt.
SYSTEM_PROMPT = f"""\
You are a careful homework helper for arithmetic word problems. You do not answer
in free text. On every turn you emit EXACTLY ONE action, on its own line, in this
form:

    ACTION: answer(<your final answer to the user>)
    ACTION: ask(<a clarifying question, when the problem is ambiguous>)
    ACTION: calculate(<a pure arithmetic expression, e.g. 17/100*240 + 13>)

Rules:
- Choose `calculate` when a number must be computed; you will be given the result
  and may then `answer`. Do arithmetic with the tool, not in your head.
- Choose `ask` only when you genuinely cannot proceed without more information.
- Choose `answer` when you can state the final answer.
- Emit the ACTION line and nothing after it. No commentary.

Available actions: {', '.join(ACTIONS)}.
"""

# ── the calculator tool ──────────────────────────────────────────────────────
# A real tool, not a mock: a SAFE arithmetic evaluator (no eval(); only numbers
# and a fixed operator set parsed from the AST). Module 4's stretch is to make a
# tool that fails sometimes — this one fails loudly on anything non-arithmetic,
# which is itself a useful failure for the loop to handle.
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def calculate(expr: str) -> str:
    """Evaluate a pure arithmetic expression, or return an error string."""
    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("unsupported expression")
    try:
        return str(ev(ast.parse(expr.strip(), mode="eval").body))
    except Exception as e:
        return f"ERROR: cannot evaluate {expr!r} ({e})"


# ── parsing the model's action (the brittle seam) ─────────────────────────────

_ACTION_RE = re.compile(r"ACTION:\s*(\w+)\s*\((.*)\)\s*$", re.IGNORECASE | re.DOTALL)


@dataclass
class ParsedAction:
    verb: str | None      # answer/ask/calculate, or None if unparseable
    arg: str
    status: str           # "ok" | "unparseable" | "unknown_action"
    raw: str


def parse_action(text: str) -> ParsedAction:
    """Find the ACTION line. This is where structured output is a fiction we
    impose — and where it breaks."""
    # Search line-by-line from the end: the model sometimes prepends commentary
    # despite instructions, so the last ACTION-looking line is the real one.
    for line in reversed(text.strip().splitlines()):
        m = _ACTION_RE.match(line.strip())
        if m:
            verb, arg = m.group(1).lower(), m.group(2).strip()
            if verb in ACTIONS:
                return ParsedAction(verb, arg, "ok", text)
            return ParsedAction(verb, arg, "unknown_action", text)  # invented action
    return ParsedAction(None, "", "unparseable", text)              # no ACTION at all


# ── telemetry ─────────────────────────────────────────────────────────────────


@dataclass
class RunResult:
    final: str            # the answer, or an ask, or a give-up notice
    terminal: str         # "answer" | "ask" | "max_iterations"
    iterations: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float


# ── the agent: Read → Think → Act, looped ─────────────────────────────────────


@dataclass
class ThreePhaseAgent:
    system: str = SYSTEM_PROMPT
    model: str = DEFAULT_MODEL
    max_tokens: int = 512
    temperature: float = 0.0
    max_iterations: int = 6     # the loop's stop guard — agents loop forever without one
    observer: Callable[[str, dict[str, Any]], None] | None = None

    messages: list[dict] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    _client: anthropic.Anthropic = field(default_factory=anthropic.Anthropic, repr=False)

    def _emit(self, event: str, **p: Any) -> None:
        if self.observer is not None:
            self.observer(event, p)

    def run(self, user_text: str) -> RunResult:
        self.messages.append({"role": "user", "content": user_text})
        self._emit("run_start", user_text=user_text)

        for i in range(1, self.max_iterations + 1):
            # ── READ ──────────────────────────────────────────────────────────
            request = {
                "model": self.model, "max_tokens": self.max_tokens,
                "temperature": self.temperature, "system": self.system,
                "messages": self.messages,
            }
            self._emit("read", iteration=i, num_messages=len(self.messages))

            # ── THINK ─────────────────────────────────────────────────────────
            started = time.perf_counter()
            resp = self._client.messages.create(**request)
            latency = time.perf_counter() - started
            text = "".join(b.text for b in resp.content if b.type == "text")
            self.messages.append({"role": "assistant", "content": text})
            i_tok, o_tok = self._account(resp)
            self._emit("think", iteration=i, text=text, latency_seconds=latency,
                       input_tokens=i_tok, output_tokens=o_tok,
                       total_cost_usd=self.total_cost_usd)

            # ── ACT ───────────────────────────────────────────────────────────
            action = parse_action(text)
            self._emit("action", iteration=i, verb=action.verb, arg=action.arg,
                       status=action.status)

            if action.status == "ok" and action.verb == "answer":
                return self._done(action.arg, "answer", i)

            if action.status == "ok" and action.verb == "ask":
                return self._done(action.arg, "ask", i)

            if action.status == "ok" and action.verb == "calculate":
                result = calculate(action.arg)
                self._emit("tool_result", iteration=i, expr=action.arg, result=result)
                # Feed the tool result back as the next turn's input, then LOOP.
                self.messages.append({
                    "role": "user",
                    "content": f"CALCULATION RESULT for {action.arg}: {result}\n"
                               f"Continue: emit your next ACTION.",
                })
                continue

            # Parse failure or invented action — correct the model and loop. This
            # is the brittleness made operational: we nudge it back to the grammar.
            self._emit("parse_recovery", iteration=i, status=action.status)
            self.messages.append({
                "role": "user",
                "content": (
                    "Your last message had no valid ACTION. Reply with exactly one "
                    f"line: ACTION: <{'|'.join(ACTIONS)}>(...). Nothing else."
                ),
            })

        # Ran out of iterations without a terminal action.
        return self._done(
            "[gave up: reached the iteration limit without a final answer]",
            "max_iterations", self.max_iterations)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _account(self, resp: anthropic.types.Message) -> tuple[int, int]:
        i, o = resp.usage.input_tokens, resp.usage.output_tokens
        self.total_input_tokens += i
        self.total_output_tokens += o
        self.total_cost_usd += (i * PRICE_PER_MTOK_INPUT + o * PRICE_PER_MTOK_OUTPUT) / 1_000_000
        return i, o

    def _done(self, final: str, terminal: str, iterations: int) -> RunResult:
        self._emit("done", terminal=terminal, final=final, iterations=iterations,
                   total_cost_usd=self.total_cost_usd)
        return RunResult(final, terminal, iterations, self.total_input_tokens,
                         self.total_output_tokens, self.total_cost_usd)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _read_question() -> str:
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:])
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    print("usage: three_phase.py 'a homework arithmetic question'", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    question = _read_question()
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

    # A tracing observer so the phases are visible on stderr (the witness will
    # later attach a richer one to the same hook).
    def trace(event: str, p: dict) -> None:
        if event == "read":
            print(f"\n[iter {p['iteration']}] READ  ({p['num_messages']} msgs)", file=sys.stderr)
        elif event == "think":
            print(f"[iter {p['iteration']}] THINK ({p['latency_seconds']:.2f}s): "
                  f"{p['text'].strip()[:200]}", file=sys.stderr)
        elif event == "action":
            print(f"[iter {p['iteration']}] ACT   -> {p['verb']}({p['arg'][:60]}) "
                  f"[{p['status']}]", file=sys.stderr)
        elif event == "tool_result":
            print(f"           calculate({p['expr']}) = {p['result']}", file=sys.stderr)
        elif event == "parse_recovery":
            print(f"           ! {p['status']} — nudging back to the grammar", file=sys.stderr)

    agent = ThreePhaseAgent(model=model, observer=trace)
    result = agent.run(question)

    print(f"\n[{result.terminal.upper()}] {result.final}")
    print(f"\n[iters={result.iterations} in={result.total_input_tokens} "
          f"out={result.total_output_tokens} cost=${result.total_cost_usd:.6f}]",
          file=sys.stderr)
