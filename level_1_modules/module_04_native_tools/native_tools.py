"""Module 4 — Native Tool Calling.

Module 3 made the model emit `ACTION: calculate(...)` as text, and we parsed it
with a regex. That parse was a fiction we imposed, and it broke: commentary,
malformed calls, invented actions, recovery nudges. This module deletes the
fiction. We declare our tools to the provider as JSON Schema, the model returns
a **structured `tool_use` block** the API guarantees the shape of, we run the
tool and hand back a **`tool_result` block**, and we loop until the model stops
calling tools and just answers.

The diff against `module_03_three_phase/three_phase.py` is the whole point:

  M3                                     M4
  ──                                     ──
  system prompt teaches an ACTION grammar  →  `tools=[…]` JSON Schema in the request
  regex `parse_action()`                   →  the model returns typed `tool_use` blocks
  parse failures + recovery nudge          →  the provider validates the shape; none needed
  one text reply, hand-parsed              →  history carries `tool_use`/`tool_result` blocks
  loop on the verb you parsed              →  loop on `stop_reason == "tool_use"`

Same `calculate` underneath. What changes is that the *call mechanism* is now a
real, validated contract instead of text you hope to parse. That's what "native
tool calling buys you" — structured parsing, for free.

Read top to bottom. The brittleness M3 spent its energy on simply isn't here.
"""

from __future__ import annotations

import ast
import json
import operator
import os
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

SYSTEM_PROMPT = (
    "You are a careful homework helper for arithmetic word problems. Use the "
    "`calculate` tool for any arithmetic — do not compute in your head. Use "
    "`ask_user` only when the problem is genuinely ambiguous. Otherwise, answer "
    "directly in plain text."
)

# ── the tools, declared as JSON Schema (the contract the provider validates) ──
# This is the M4 replacement for M3's system-prompt grammar. The provider reads
# these schemas, and any `tool_use` it returns is guaranteed to match — name and
# input shape — so there is nothing to parse and nothing to recover from.
TOOLS = [
    {
        "name": "calculate",
        "description": "Evaluate a pure arithmetic expression and return the result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "A pure arithmetic expression, e.g. '17/100*240 + 13'.",
                }
            },
            "required": ["expression"],
        },
    },
    {
        "name": "ask_user",
        "description": "Ask the user a clarifying question when the problem is ambiguous.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The clarifying question."}
            },
            "required": ["question"],
        },
    },
]

# ── the calculator tool (identical AST-safe evaluator as M3) ──────────────────
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def calculate(expr: str) -> str:
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


@dataclass
class RunResult:
    final: str
    terminal: str         # "answer" | "ask" | "max_iterations"
    iterations: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float


@dataclass
class NativeToolAgent:
    system: str = SYSTEM_PROMPT
    model: str = DEFAULT_MODEL
    max_tokens: int = 512
    temperature: float = 0.0
    max_iterations: int = 6
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
            self._emit("read", iteration=i, num_messages=len(self.messages))

            started = time.perf_counter()
            resp = self._client.messages.create(
                model=self.model, max_tokens=self.max_tokens,
                temperature=self.temperature, system=self.system,
                tools=TOOLS, messages=self.messages,
            )
            latency = time.perf_counter() - started
            i_tok, o_tok = self._account(resp)
            text = "".join(b.text for b in resp.content if b.type == "text")
            self._emit("think", iteration=i, text=text, stop_reason=resp.stop_reason,
                       latency_seconds=latency, input_tokens=i_tok, output_tokens=o_tok,
                       total_cost_usd=self.total_cost_usd)

            # No tool requested → the model answered. Terminal. (M3 had to PARSE
            # to learn this; here it's a flag the provider sets: stop_reason.)
            if resp.stop_reason != "tool_use":
                return self._done(text or "(no text)", "answer", i)

            # Record the assistant turn verbatim (text + tool_use blocks) — the
            # API requires the tool_use to be in history before its tool_result.
            self.messages.append({"role": "assistant", "content": resp.content})

            tool_results, ask_question = [], None
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                self._emit("tool_use", iteration=i, name=block.name, input=dict(block.input))
                if block.name == "calculate":
                    result = calculate(block.input.get("expression", ""))
                    self._emit("tool_result", iteration=i, name="calculate", result=result)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id,
                                         "content": result})
                elif block.name == "ask_user":
                    ask_question = block.input.get("question", "")
                    # Even for a terminal ask, every tool_use needs a matching
                    # tool_result or the history is invalid for any later turn.
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id,
                                         "content": "(asked the user; reply will arrive next turn)"})

            # Hand the results back as the next user turn — distinct content
            # blocks, distinct roles. This is the loop, native-style.
            self.messages.append({"role": "user", "content": tool_results})

            if ask_question is not None:
                return self._done(ask_question, "ask", i)
            # otherwise loop: the model sees the tool_result and continues.

        return self._done("[gave up: reached the iteration limit]", "max_iterations",
                          self.max_iterations)

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
    print("usage: native_tools.py 'a homework arithmetic question'", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    question = _read_question()
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

    def trace(event: str, p: dict) -> None:
        if event == "read":
            print(f"\n[iter {p['iteration']}] READ ({p['num_messages']} msgs)", file=sys.stderr)
        elif event == "think":
            note = p["text"].strip()[:160] or "(no text — tool call)"
            print(f"[iter {p['iteration']}] THINK [{p['stop_reason']}] {note}", file=sys.stderr)
        elif event == "tool_use":
            print(f"           tool_use: {p['name']}({p['input']})", file=sys.stderr)
        elif event == "tool_result":
            print(f"           tool_result: {p['result']}", file=sys.stderr)

    agent = NativeToolAgent(model=model, observer=trace)
    result = agent.run(question)

    print(f"\n[{result.terminal.upper()}] {result.final}")
    print(f"\n[iters={result.iterations} in={result.total_input_tokens} "
          f"out={result.total_output_tokens} cost=${result.total_cost_usd:.6f}]",
          file=sys.stderr)
