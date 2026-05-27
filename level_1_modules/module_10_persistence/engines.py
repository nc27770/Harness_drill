"""The body's hands — isolated tool runners (SCHEMA.md invariant 2).

A `Registry` is the body's *provisions*: the set of tool names it can actually
run, each bound to a command that executes **out-of-process**, sandboxed by a
timeout and captured I/O. Any failure — bad exit, timeout, launch error —
becomes a contained `EngineResult(ok=False, …)`, which the runtime records as a
*perception* the mind reasons about. A tool can never crash the mind.

`provisions()` is what the runtime checks against a Mind's declared `tools`
(needs ⊆ provisions). `ask_user` is deliberately NOT an engine — it's a
control-flow signal (suspend for the human), handled by the runtime, not run.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


@dataclass
class EngineResult:
    ok: bool
    content: str   # the string the mind will perceive


class Registry:
    def __init__(self) -> None:
        self._argv: dict[str, list[str]] = {}

    def provide(self, name: str, argv: list[str]) -> None:
        """Bind a tool name to a command run as a separate process."""
        self._argv[name] = argv

    def provisions(self) -> set[str]:
        return set(self._argv)

    def run(self, name: str, tool_input: dict, timeout: float = 10.0) -> EngineResult:
        if name not in self._argv:
            return EngineResult(False, f"ERROR: this body provides no engine named '{name}'")
        try:
            proc = subprocess.run(
                self._argv[name],
                input=json.dumps(tool_input),
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode != 0:
                return EngineResult(False, f"ERROR: engine '{name}' exited {proc.returncode}: "
                                           f"{proc.stderr.strip()[:200]}")
            return EngineResult(True, proc.stdout.strip())
        except subprocess.TimeoutExpired:
            return EngineResult(False, f"ERROR: engine '{name}' timed out after {timeout}s")
        except Exception as e:  # launch failure — still contained
            return EngineResult(False, f"ERROR: engine '{name}' could not launch: {e}")


def default_registry() -> Registry:
    """The provisions this particular body offers."""
    r = Registry()
    r.provide("calculate", [sys.executable, str(HERE / "engine_calculate.py")])
    return r
