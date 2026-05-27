"""The runtime — a body that animates a Mind, and can put it down and pick it up again.

This is pure code (the body). It consumes the declarative data (config + state),
produces new data, and checkpoints after every step so the Mind survives the
process. Kill the body mid-thought; a fresh body loads `(config, state)` by
`mind_id` and resumes *as the same mind*.

Pieces: `Body` (binds isolated engines + a model client + the Store, and refuses
to host a Mind it isn't capable of), `animate_to_terminal` (the M4 native-tool
loop, faculty-tagging every entry, checkpointing each step), and `step`/`resume`.

v0 note: extended thinking is intentionally OFF here — replaying signed thinking
blocks across tool-use turns is a real edge we defer (SCHEMA stays ready for it).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from store import Store, now_iso          # noqa: E402
from engines import Registry, default_registry  # noqa: E402
from projection import to_anthropic_messages     # noqa: E402
from witness import event_printer, render_md     # noqa: E402

PRICE_IN, PRICE_OUT = 3.00, 15.00
DEFAULT_MODEL = "claude-sonnet-4-6"
RUNTIME_HANDLED = {"ask_user"}   # control-flow signals the runtime handles, not engines
TRACES_DIR = REPO_ROOT / "traces" / "minds"


def _emit(observer, event, **p):
    if observer is not None:
        observer(event, p)


# ── declarative templates (data) ─────────────────────────────────────────────

CALC_TOOL = {
    "name": "calculate",
    "description": "Evaluate a pure arithmetic expression and return the result.",
    "input_schema": {"type": "object",
                     "properties": {"expression": {"type": "string"}},
                     "required": ["expression"]},
}
ASK_TOOL = {
    "name": "ask_user",
    "description": "Ask the user a clarifying question when the problem is ambiguous.",
    "input_schema": {"type": "object",
                     "properties": {"question": {"type": "string"}},
                     "required": ["question"]},
}


def make_homework_mind(mind_id: str, label: str = "homework-helper",
                       model: str = DEFAULT_MODEL) -> dict:
    return {
        "schema_version": "0.1", "mind_id": mind_id, "label": label,
        "created_at": now_iso(),
        "purpose": {  # ENDS — read-only to the running mind
            "system": ("You are a careful homework helper for arithmetic word problems. "
                       "Use the calculate tool for any arithmetic — never compute in your head. "
                       "Use ask_user only when genuinely ambiguous. Otherwise answer plainly."),
            "goal": None,
        },
        "model": {"provider": "anthropic", "name": model, "max_tokens": 512,
                  "temperature": 0.0, "thinking": {"enabled": False, "budget_tokens": 1024}},
        "tools": [CALC_TOOL, ASK_TOOL],
        "policies": {"max_iterations": 6},
    }


def fresh_state(mind_id: str) -> dict:
    return {"schema_version": "0.1", "mind_id": mind_id, "status": "ready",
            "cursor": {"turn": 0, "iteration": 0}, "transcript": [],
            "pending": {"type": None, "question": None},
            "ledger": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "turns": 0},
            "updated_at": now_iso()}


# ── helpers (mutate STATE only — never config: the ontological lock) ──────────

def _append(state: dict, **fields) -> None:
    fields["seq"] = len(state["transcript"])
    state["transcript"].append(fields)


def _account(state: dict, resp, model: dict) -> None:
    i, o = resp.usage.input_tokens, resp.usage.output_tokens
    L = state["ledger"]
    L["input_tokens"] += i
    L["output_tokens"] += o
    L["cost_usd"] += (i * PRICE_IN + o * PRICE_OUT) / 1_000_000


def _summary(state: dict) -> dict:
    if state["status"] == "awaiting_input":
        final = state["pending"]["question"]
    else:
        final = next((e["content"] for e in reversed(state["transcript"])
                      if e["faculty"] == "expression"), None)
    return {"status": state["status"], "final": final,
            "iterations": state["cursor"]["iteration"],
            "cost_usd": round(state["ledger"]["cost_usd"], 6)}


# ── the loop ──────────────────────────────────────────────────────────────────

def animate_to_terminal(config: dict, state: dict, registry: Registry, client,
                        checkpoint, observer=None) -> None:
    model = config["model"]
    max_iter = config.get("policies", {}).get("max_iterations", 6)
    state["status"] = "running"
    checkpoint()

    while state["cursor"]["iteration"] < max_iter:
        state["cursor"]["iteration"] += 1
        resp = client.messages.create(
            model=model["name"], max_tokens=model["max_tokens"],
            temperature=model["temperature"], system=config["purpose"]["system"],
            tools=config["tools"], messages=to_anthropic_messages(state["transcript"]),
        )
        _account(state, resp, model)
        text = "".join(b.text for b in resp.content if b.type == "text")
        _emit(observer, "think", stop_reason=resp.stop_reason,
              **{"in": resp.usage.input_tokens, "out": resp.usage.output_tokens,
                 "cost": state["ledger"]["cost_usd"]})

        if resp.stop_reason == "tool_use":
            if text.strip():
                _append(state, faculty="reasoning", content=text)
                _emit(observer, "reasoning", content=text)
            suspended = False
            for b in resp.content:
                if b.type != "tool_use":
                    continue
                _append(state, faculty="action", engine=b.name, input=dict(b.input), ref=b.id)
                _emit(observer, "action", engine=b.name, input=dict(b.input))
                checkpoint()  # the action is durable before the engine fires
                if b.name in RUNTIME_HANDLED:        # ask_user → suspend for the human
                    q = dict(b.input).get("question", "")
                    state["pending"] = {"type": "ask", "question": q, "ref": b.id}
                    state["status"] = "awaiting_input"
                    checkpoint()
                    _emit(observer, "suspend", question=q)
                    suspended = True
                else:                                 # real tool → isolated engine
                    res = registry.run(b.name, dict(b.input))
                    _append(state, faculty="perception", origin="engine", ref=b.id,
                            ok=res.ok, content=res.content)
                    checkpoint()  # ← THE RESUME POINT: the observation is durable
                    _emit(observer, "observe", ok=res.ok, content=res.content)
                    if os.environ.get("HARNESS_CRASH_AFTER_TOOL"):
                        print("[simulated body crash, mid-thought, after tool result]",
                              file=sys.stderr)
                        os._exit(7)
            if suspended:
                return
        else:                                         # end_turn → conclusive expression
            _append(state, faculty="expression", conclusive=True, content=text)
            state["status"] = "done"
            state["pending"] = {"type": None, "question": None}
            checkpoint()
            _emit(observer, "expression", content=text)
            return

    _append(state, faculty="expression", conclusive=True, content="[gave up: max iterations]")
    state["status"] = "done"
    checkpoint()
    _emit(observer, "expression", content="[gave up: max iterations]")


# ── the body ──────────────────────────────────────────────────────────────────

class Body:
    def __init__(self, store: Store, registry: Registry, client, observer=None):
        self.store, self.registry, self.client = store, registry, client
        self.observer = observer   # the witness seam — pure observance, may be None

    def can_host(self, config: dict) -> tuple[bool, set]:
        needs = {t["name"] for t in config.get("tools", [])} - RUNTIME_HANDLED
        missing = needs - self.registry.provisions()
        return (not missing), missing

    def install(self, config: dict) -> None:
        ok, missing = self.can_host(config)
        if not ok:
            raise RuntimeError(f"this body cannot host '{config['mind_id']}': "
                               f"missing engines {missing} (needs ⊄ provisions)")
        self.store.save_config(config)
        self.store.save_state(fresh_state(config["mind_id"]))

    def _load(self, mind_id):
        config, state = self.store.load_config(mind_id), self.store.load_state(mind_id)
        if config is None or state is None:
            raise RuntimeError(f"no such mind: {mind_id}")
        return config, state

    def step(self, mind_id: str, user_input: str) -> dict:
        config, state = self._load(mind_id)        # config is READ-ONLY from here
        if state.get("pending", {}).get("type") == "ask":   # answering a pending ask
            _append(state, faculty="perception", origin="human",
                    ref=state["pending"]["ref"], ok=True, content=user_input)
            state["pending"] = {"type": None, "question": None}
        else:                                       # a fresh turn
            state["cursor"]["turn"] += 1
            state["cursor"]["iteration"] = 0
            state["ledger"]["turns"] += 1
            _append(state, faculty="perception", origin="human", content=user_input)
        _emit(self.observer, "turn_start", turn=state["cursor"]["turn"])
        _emit(self.observer, "perceive", origin="human", content=user_input)
        self.store.save_state(state)
        animate_to_terminal(config, state, self.registry, self.client,
                            lambda: self.store.save_state(state), observer=self.observer)
        return _summary(state)

    def resume(self, mind_id: str) -> dict:
        config, state = self._load(mind_id)
        _emit(self.observer, "turn_start", turn=state["cursor"]["turn"])
        animate_to_terminal(config, state, self.registry, self.client,
                            lambda: self.store.save_state(state), observer=self.observer)
        return _summary(state)


# ── CLI — create / step / resume / show / list ───────────────────────────────

def _body(db: str, observer=None) -> Body:
    import anthropic
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    return Body(Store(db), default_registry(), anthropic.Anthropic(), observer=observer)


def _print_state(store: Store, mind_id: str) -> None:
    state = store.load_state(mind_id)
    if not state:
        print("(no such mind)"); return
    print(f"mind={mind_id} status={state['status']} turn={state['cursor']['turn']} "
          f"iter={state['cursor']['iteration']} cost=${state['ledger']['cost_usd']:.6f}")
    for e in state["transcript"]:
        tag = e["faculty"][:4].upper()
        extra = ""
        if e["faculty"] == "action":
            extra = f" {e['engine']}({e.get('input')})"
        c = str(e.get("content", "")).replace("\n", " ")[:90]
        print(f"  [{e['seq']:>2}] {tag:5} {extra}{(' ' if extra else '')}{c}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["create", "step", "resume", "show", "list", "witness"])
    ap.add_argument("mind_id", nargs="?")
    ap.add_argument("text", nargs="*")
    ap.add_argument("--db", default=str(HERE / "minds.db"))
    args = ap.parse_args()
    # live observance (the witness seam) on the acts that animate the mind
    obs = event_printer() if args.cmd in ("step", "resume") else None
    body = _body(args.db, observer=obs)

    if args.cmd == "create":
        body.install(make_homework_mind(args.mind_id))
        print(f"installed mind '{args.mind_id}' (body provisions: {body.registry.provisions()})")
    elif args.cmd == "step":
        print(json.dumps(body.step(args.mind_id, " ".join(args.text)), indent=2))
    elif args.cmd == "resume":
        print(json.dumps(body.resume(args.mind_id), indent=2))
    elif args.cmd == "show":
        _print_state(body.store, args.mind_id)
    elif args.cmd == "list":
        for m in body.store.list_minds():
            print(m)
    elif args.cmd == "witness":
        config, state = body.store.load_config(args.mind_id), body.store.load_state(args.mind_id)
        if not config:
            print("(no such mind)")
        else:
            TRACES_DIR.mkdir(parents=True, exist_ok=True)
            md = render_md(config, state)
            (TRACES_DIR / f"{args.mind_id}.md").write_text(md)
            (TRACES_DIR / f"{args.mind_id}.json").write_text(
                json.dumps({"config": config, "state": state}, indent=2))
            print(md)
            print(f"\n[serialized: traces/minds/{args.mind_id}.md + .json]", file=sys.stderr)
