"""Witness — observance for the runtime, in API/serialization form (no UI).

Two affordances, both pure observance (SCHEMA.md: the witness never mutates the
Mind):

  • `event_printer()` — an `observer(event, payload)` you attach to a step/resume
    to watch the faculties flow live (to stderr). The same seam an API consumer
    would use to stream observance.
  • `render_md(config, state)` — the documentary Mind & Machine log of a persisted
    Mind: its identity (config) + its continuum (faculty transcript + ledger).
    The canonical `.json` is just the stored state itself.

This is the witness the user asked to keep wired — serialized, not a panel.
"""

from __future__ import annotations

import sys


def event_printer(stream=sys.stderr):
    """Live observance: print each faculty event as it happens."""
    def obs(event: str, p: dict) -> None:
        if event == "turn_start":
            print(f"\n— turn {p['turn']} —", file=stream)
        elif event == "perceive":
            print(f"  PERCEPTION ({p['origin']}): {str(p['content'])[:100]}", file=stream)
        elif event == "think":
            print(f"  · think [{p['stop_reason']}] in={p['in']} out={p['out']} "
                  f"cum=${p['cost']:.6f}", file=stream)
        elif event == "reasoning":
            print(f"  REASONING: {str(p['content'])[:100]}", file=stream)
        elif event == "action":
            print(f"  ACTION → {p['engine']}({p['input']})", file=stream)
        elif event == "observe":
            ok = "ok" if p["ok"] else "ERR"
            print(f"  PERCEPTION (engine,{ok}): {str(p['content'])[:80]}", file=stream)
        elif event == "suspend":
            print(f"  EXPRESSION (ask, suspending): {str(p['question'])[:100]}", file=stream)
        elif event == "expression":
            print(f"  EXPRESSION (conclusive): {str(p['content'])[:100]}", file=stream)
        elif event == "checkpoint":
            print(f"  [checkpoint: status={p['status']} seq={p['seq']}]", file=stream)
    return obs


def render_md(config: dict, state: dict) -> str:
    m = config["model"]
    out = [
        f"# Mind & Machine log — {config.get('label')} (`{config['mind_id']}`)",
        "",
        "## Identity (config — the ends, read-only to the mind)",
        f"- **purpose:** {config['purpose']['system']}",
        f"- **model:** {m['provider']}/{m['name']} (max_tokens={m['max_tokens']}, temp={m['temperature']})",
        f"- **declared tools:** {', '.join(t['name'] for t in config.get('tools', []))}",
        f"- **policies:** {config.get('policies')}",
        "",
        "## Continuum (state)",
        f"- **status:** {state['status']} · turn {state['cursor']['turn']} · "
        f"iter {state['cursor']['iteration']}",
        f"- **ledger:** in={state['ledger']['input_tokens']} out={state['ledger']['output_tokens']} "
        f"cost=${state['ledger']['cost_usd']:.6f}",
        "",
        "## Transcript (faculties: perception → reasoning → action → perception → expression)",
    ]
    for e in state["transcript"]:
        f = e["faculty"]
        c = str(e.get("content", "")).replace("\n", " ")
        if f == "perception" and e.get("origin") == "human":
            out += ["", f"**[{e['seq']}] PERCEPTION (human):** {c}"]
        elif f == "perception":
            out.append(f"- [{e['seq']}] perception (engine{'' if e.get('ok') else ', ERROR'}): `{c[:120]}`")
        elif f == "reasoning":
            out.append(f"- [{e['seq']}] reasoning: {c[:200]}")
        elif f == "action":
            out.append(f"- [{e['seq']}] action → **{e['engine']}**({e.get('input')})")
        elif f == "expression":
            out += [f"**[{e['seq']}] EXPRESSION{' (conclusive)' if e.get('conclusive') else ''}:** {c}"]
    return "\n".join(out)
