"""Module 5 — The Naive Agent Class.

Modules 2–4 were three scripts with near-identical skeletons. This is the refactor
where you notice that and extract ONE reusable object — the moment you've written
your own micro-framework.

The diff against `module_04_native_tools/native_tools.py` is the wrap:

  M4                                        M5
  ──                                        ──
  TOOLS constant baked into the module       →  `tools=[Tool(...)]` injected at construction
  `if block.name == "calculate"` dispatch    →  generic dispatch via a {name: fn} registry
  a script with a __main__                    →  an `Agent` you instantiate and reuse
  one behavior                                →  `run()` (one goal) + multi-turn (history carried)

Pass a different `tools` list and the SAME class is a weather bot, a SQL helper,
anything. That decoupling — tools as data, independent of the agent — is what
makes this a framework and not a program.

It is **naive on purpose**: single provider, in-memory state, and tools run
*in this process* (a raising tool takes the agent down; close the laptop and the
agent is gone). Those exact naiveties are what Module 10's durable Mind fixes —
build this first to feel why that one exists.
"""

from __future__ import annotations

import ast
import operator
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic
from dotenv import load_dotenv

load_dotenv()

PRICE_IN, PRICE_OUT = 3.00, 15.00
DEFAULT_MODEL = "claude-sonnet-4-6"


# ── a tool = a declared contract + an in-process implementation ───────────────


@dataclass
class Tool:
    """What the model sees (name/description/input_schema) bound to what runs (fn).

    `fn` takes the parsed input dict and returns a string the model perceives.
    In this naive agent it's called *in-process* — the deliberate contrast with
    Module 10's isolated, out-of-process engines.
    """
    name: str
    description: str
    input_schema: dict
    fn: Callable[[dict], str]

    @property
    def schema(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": self.input_schema}


@dataclass
class RunResult:
    final: str
    terminal: str        # "answer" | "max_iterations"
    iterations: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float


# ── the agent: configure once, run many; tools are data ───────────────────────


@dataclass
class Agent:
    system: str
    tools: list[Tool] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    max_tokens: int = 512
    temperature: float = 0.0
    max_iterations: int = 6
    observer: Callable[[str, dict[str, Any]], None] | None = None

    messages: list[dict] = field(default_factory=list)   # carried history → multi-turn
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    _client: anthropic.Anthropic = field(default_factory=anthropic.Anthropic, repr=False)

    def __post_init__(self) -> None:
        # The two things derived from the injected tools: the schemas the model
        # sees, and the name→fn registry the loop dispatches through. Generic —
        # the agent code never names a specific tool.
        self._schemas = [t.schema for t in self.tools]
        self._dispatch = {t.name: t.fn for t in self.tools}

    def _emit(self, event: str, **p: Any) -> None:
        if self.observer is not None:
            self.observer(event, p)

    def run(self, user_input: str) -> RunResult:
        """One goal-oriented loop to a terminal answer. History persists on the
        instance, so a second run() continues the same conversation."""
        self.messages.append({"role": "user", "content": user_input})
        self._emit("run_start", user_text=user_input)

        for i in range(1, self.max_iterations + 1):
            self._emit("read", iteration=i, num_messages=len(self.messages))
            started = time.perf_counter()
            resp = self._client.messages.create(
                model=self.model, max_tokens=self.max_tokens,
                temperature=self.temperature, system=self.system,
                tools=self._schemas or anthropic.NOT_GIVEN, messages=self.messages,
            )
            latency = time.perf_counter() - started
            i_tok, o_tok = self._account(resp)
            text = "".join(b.text for b in resp.content if b.type == "text")
            self._emit("think", iteration=i, text=text, stop_reason=resp.stop_reason,
                       latency_seconds=latency, input_tokens=i_tok, output_tokens=o_tok,
                       total_cost_usd=self.total_cost_usd)

            if resp.stop_reason != "tool_use":            # the model answered
                return self._done(text or "(no text)", "answer", i)

            self.messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for b in resp.content:
                if b.type != "tool_use":
                    continue
                self._emit("tool_use", iteration=i, name=b.name, input=dict(b.input))
                fn = self._dispatch.get(b.name)
                # Generic dispatch — no tool name hardcoded. (Naive: fn runs in
                # this process; an exception here would crash the agent.)
                result = fn(dict(b.input)) if fn else f"ERROR: no tool named '{b.name}'"
                self._emit("tool_result", iteration=i, name=b.name, result=result)
                tool_results.append({"type": "tool_result", "tool_use_id": b.id,
                                     "content": result})
            self.messages.append({"role": "user", "content": tool_results})

        return self._done("[gave up: reached the iteration limit]", "max_iterations",
                          self.max_iterations)

    def chat(self) -> None:
        """Multi-turn REPL — run() in a loop, history carried across turns."""
        print(f"Agent ready (model={self.model}, tools={list(self._dispatch)}). /exit to quit.")
        while True:
            try:
                line = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print(); break
            if line in ("/exit", "/quit"):
                break
            if not line:
                continue
            r = self.run(line)
            print(f"bot> {r.final}")

    def _account(self, resp) -> tuple[int, int]:
        i, o = resp.usage.input_tokens, resp.usage.output_tokens
        self.total_input_tokens += i
        self.total_output_tokens += o
        self.total_cost_usd += (i * PRICE_IN + o * PRICE_OUT) / 1_000_000
        return i, o

    def _done(self, final: str, terminal: str, iterations: int) -> RunResult:
        self._emit("done", terminal=terminal, final=final, iterations=iterations,
                   total_cost_usd=self.total_cost_usd)
        return RunResult(final, terminal, iterations, self.total_input_tokens,
                         self.total_output_tokens, self.total_cost_usd)


# ── a tool to inject (the agent doesn't know about it until you pass it in) ────

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def _calculate(inp: dict) -> str:
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError("unsupported expression")
    expr = inp.get("expression", "")
    try:
        return str(ev(ast.parse(expr.strip(), mode="eval").body))
    except Exception as e:
        return f"ERROR: cannot evaluate {expr!r} ({e})"


def calculate_tool() -> Tool:
    return Tool(
        name="calculate",
        description="Evaluate a pure arithmetic expression and return the result.",
        input_schema={"type": "object",
                      "properties": {"expression": {"type": "string"}},
                      "required": ["expression"]},
        fn=_calculate,
    )


def homework_agent(model: str = DEFAULT_MODEL, observer=None) -> Agent:
    return Agent(
        system=("You are a careful homework helper for arithmetic. Use the calculate "
                "tool for any arithmetic; if a problem is ambiguous, ask in plain text. "
                "Otherwise answer plainly."),
        tools=[calculate_tool()],
        model=model, observer=observer,
    )


if __name__ == "__main__":
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

    def trace(event, p):
        if event == "think":
            print(f"[iter {p['iteration']}] THINK [{p['stop_reason']}] "
                  f"{p['text'].strip()[:120] or '(tool call)'}", file=sys.stderr)
        elif event == "tool_use":
            print(f"           tool_use: {p['name']}({p['input']})", file=sys.stderr)
        elif event == "tool_result":
            print(f"           tool_result: {p['result']}", file=sys.stderr)

    agent = homework_agent(model=model, observer=trace)
    if len(sys.argv) > 1:
        r = agent.run(" ".join(sys.argv[1:]))
        print(f"\n[{r.terminal.upper()}] {r.final}")
        print(f"\n[iters={r.iterations} in={r.total_input_tokens} out={r.total_output_tokens} "
              f"cost=${r.total_cost_usd:.6f}]", file=sys.stderr)
    else:
        agent.chat()
