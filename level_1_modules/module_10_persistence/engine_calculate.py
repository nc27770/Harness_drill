"""An engine — runs in its OWN process (SCHEMA.md invariant 2: tool isolation).

This file is never imported by the runtime. The body launches it as a separate
PID; it reads a tool input as JSON on stdin and prints the result on stdout. If
the expression is bad it prints an ERROR line (exit 0); if it were to crash or
hang, the body's runner contains that as a perception error — the mind never
dies with it.
"""

from __future__ import annotations

import ast
import json
import operator
import sys

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def calc(expr: str) -> str:
    def ev(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("unsupported expression")
    return str(ev(ast.parse(expr.strip(), mode="eval").body))


if __name__ == "__main__":
    data = json.load(sys.stdin)
    try:
        print(calc(data.get("expression", "")))
    except Exception as e:
        print(f"ERROR: cannot evaluate {data.get('expression')!r} ({e})")
