"""Level-2 String 02 — The Witness (spans Modules 2–5).

Module 1 had a Gradio surface so you could *see* the seam. This is the same idea
for the agent loop, but what's worth seeing here is the machinery: a list
growing, tokens climbing, dollars accruing, history rewritten, decisions parsed
and dispatched. It runs the REAL kernels from `level_1_modules/` (nothing faked),
attaching each kernel's Observance `observer` to capture every internal event.

A Level-2 *string* (not a module): a cross-module surface. It is **mode-aware** —
the Module-mode selector routes a turn through the right kernel:
  • M2 → conversation loop      (module_02_conversation/conversation.py)
  • M3 → three-phase RTA loop   (module_03_three_phase/three_phase.py)
  • M4 / M5 → wired as they land.

Panels: Conversation · Harness meta-log · Telemetry (+ balloon) · Chain-of-thought
· Pre/Post compaction (M2) · Actions / Phases (M3) · Logs & Compare.

Every thread is serialized to `traces/witness/` as the Mind & Machine log
(JSON + Markdown + raw JSONL), with a derived `index.jsonl` for comparison.

Run:
    .venv/bin/python level_2_strings/string_02_witness/witness.py
                  [--host 127.0.0.1] [--port 7861] [--share]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MOD2 = REPO_ROOT / "level_1_modules" / "module_02_conversation"
MOD3 = REPO_ROOT / "level_1_modules" / "module_03_three_phase"
MOD4 = REPO_ROOT / "level_1_modules" / "module_04_native_tools"
MOD5 = REPO_ROOT / "level_1_modules" / "module_05_agent"
TRACES_DIR = REPO_ROOT / "traces" / "witness"

sys.path.insert(0, str(Path(__file__).parent))   # mindmachine_log
sys.path.insert(0, str(MOD2))
sys.path.insert(0, str(MOD3))
sys.path.insert(0, str(MOD4))
sys.path.insert(0, str(MOD5))
from conversation import Conversation, DEFAULT_MODEL  # noqa: E402
from three_phase import ThreePhaseAgent  # noqa: E402
from native_tools import NativeToolAgent  # noqa: E402
from agent import homework_agent  # noqa: E402
from mindmachine_log import MindMachineLog, build_index  # noqa: E402

import gradio as gr  # noqa: E402
import pandas as pd  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")
MODEL = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
DEFAULT_SYSTEM = "You are a concise, friendly assistant. Keep replies to a few sentences."
CATCH_PHRASE = "harness"   # the rate-limit guard, same as the Module-1 dispatcher

DEMOS: dict[str, dict] = {
    "compaction-fidelity": {
        "module_mode": "M2",
        "settings": {"compact_at": 200, "keep_last_turns": 2, "thinking": False, "summary_max_tokens": 512},
        "note": "M2 · Compaction fires, yet the summary PRESERVES the early facts. The happy path.",
        "script": [
            "My name is Alice. I'm building a video generation pipeline called Reel that turns scripts into short films.",
            "It has three stages: a parser, a composer, and a bilateral reviewer. What risk should I watch in the parser stage?",
            "Briefly: what's the tradeoff between running the parser at temperature 0 versus 0.7?",
            "What is my name, and what is my project called?",
        ],
    },
    "lost-in-the-middle": {
        "module_mode": "M2",
        "settings": {"compact_at": 1_000_000, "keep_last_turns": 2, "thinking": False, "summary_max_tokens": 512},
        "note": "M2 · A 'needle' stated at turn 1, buried, then queried. Position effect; frontier models often recall fine at this scale — the SETUP is the lesson.",
        "script": [
            "Remember this exact detail for later: the launch code for probe Theta is VERMILLION-77. Just acknowledge.",
            "Anyway — what's a sensible way to structure a small Python project?",
            "Thanks. How should I think about logging versus print statements?",
            "Fair enough. Is bothering with type hints worth the effort on a solo project?",
            "Okay. Suggest three names for a pet tortoise.",
            "Nice. What's a breakfast I can make in about five minutes?",
            "Last tangent: recommend a board game good for four players.",
            "Now — what was the exact launch code for probe Theta that I gave you at the very start?",
        ],
    },
    "compaction-loss": {
        "module_mode": "M2",
        "settings": {"compact_at": 150, "keep_last_turns": 1, "thinking": False, "summary_max_tokens": 48},
        "note": "M2 · A trivial aside buried among facts; a tiny summary budget drops it; a later query hits the hole → visible loss.",
        "script": [
            "Hi! I'm Priya, working on a project codenamed Halcyon — it turns podcasts into illustrated summaries. (Oh, and the office fern next to my desk is named Gus, but that's beside the point.) What's the riskiest part of that pipeline?",
            "Makes sense. How would you keep the illustration style consistent across episodes?",
            "Good. And how should I think about budgeting compute for the image-generation step?",
            "Random memory check: what did I say the office fern next to my desk is named?",
        ],
    },
    "m3-calculate": {
        "module_mode": "M3",
        "settings": {},
        "note": "M3 · Read→Think→Act with a hand-parsed ACTION grammar: the model calculates, gets the result back (Observe), then answers.",
        "script": [
            "What is 17% of 240, plus 13?",
            "If a recipe for 4 needs 300g flour, how much for 7 people?",
        ],
    },
    "m4-calculate": {
        "module_mode": "M4",
        "settings": {},
        "note": "M4 · Same problem, NATIVE tool calling: structured tool_use/tool_result, no regex. Compare its token cost to m3-calculate in the index — native tools cost more tokens, buy reliability.",
        "script": [
            "What is 17% of 240, plus 13?",
            "If a recipe for 4 needs 300g flour, how much for 7 people?",
        ],
    },
    "m5-agent": {
        "module_mode": "M5",
        "settings": {},
        "note": "M5 · The naive reusable Agent class — same native-tool loop as M4, but tools injected as data and dispatched generically. Multi-turn: the second prompt continues the same conversation.",
        "script": [
            "What is 17% of 240, plus 13?",
            "And what was that, rounded to the nearest ten?",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Recorder
# ─────────────────────────────────────────────────────────────────────────────


class Witness:
    def __init__(self, log: MindMachineLog, mode: str) -> None:
        self.log = log
        self.mode = mode
        self.display: list[dict] = []
        self.meta: list[str] = []
        self.cot_by_turn: dict[int, str] = {}
        self.telem_rows: list[dict] = []
        self.turns_tel: dict[int, dict] = {}
        self.compactions: list[dict] = []   # M2
        self.phases: list[dict] = []        # M3 runs, each with iterations
        self._turn = 0
        self._pending: dict = {}

    def handle(self, event: str, p: dict) -> None:
        self.log.event(event, p)
        # ── M2 conversation events ───────────────────────────────────────────
        if event == "turn_start":
            self._turn += 1
            self.meta.append(f"### ▶ turn {self._turn}\n- history **{p['messages_before']}** msgs; "
                             f"last ctx **{p['last_context_tokens']}** (threshold {p['threshold']})")
        elif event == "user_appended":
            self.meta.append(f"- appended user msg → **{p['messages_now']}** msgs; shipping the entire history")
        elif event == "compaction_start":
            self._pending = {"before": p["messages_before"], "summarizing": p["summarizing"], "kept": p["keeping"]}
            self.meta.append(f"- ⚠️ **COMPACTION** — summarizing **{p['summarizing']}**, keeping **{p['keeping']}**")
        elif event == "compaction_done":
            self.meta.append(f"- ✓ compaction: **{p['old_count']}** msgs → 1 summary (**${p['cost_usd']:.6f}**)")
            self.compactions.append({"turn": self._turn, "summarizing": self._pending.get("summarizing"),
                                     "kept": self._pending.get("kept"), "summary": p["summary"],
                                     "before": self._pending.get("before", []), "after": p["messages_after"],
                                     "cost_usd": p["cost_usd"]})
        elif event == "request":
            self.meta.append(f"- → API call with **{p['num_messages']}** messages"
                             + (" *(thinking ON)*" if p["thinking"] else ""))
        elif event == "thinking":
            self.cot_by_turn[self._turn] = p["text"]
        elif event == "response":
            flag = " · **COMPACTED first**" if p["compacted"] else ""
            self.meta.append(f"- ← reply: ctx **{p['context_tokens']}** · out {p['output_tokens']} · "
                             f"${p['cost_usd']:.6f} · {p['latency_seconds']:.2f}s · cum **${p['total_cost_usd']:.6f}**{flag}")
            self._tel(self._turn, p["context_tokens"], p["output_tokens"], p["cost_usd"],
                      p["total_cost_usd"], p["latency_seconds"], p["compacted"])
        # ── M3 three-phase (RTA) events ──────────────────────────────────────
        elif event == "run_start":
            self._turn += 1
            self.phases.append({"run": self._turn, "iterations": [], "final": None, "terminal": None})
            self.meta.append(f"### ▶ run {self._turn} — “{p['user_text'][:60]}”")
        elif event == "read":
            self.phases[-1]["iterations"].append({"i": p["iteration"], "think": "", "stop": "",
                                                   "verb": None, "arg": "", "status": "",
                                                   "tooluse": "", "tool": ""})
            self.meta.append(f"- iter {p['iteration']} · READ ({p['num_messages']} msgs)")
        elif event == "think":
            it = self.phases[-1]["iterations"][-1]
            it["think"] = p["text"]
            it["stop"] = p.get("stop_reason", "")
            sr = f" [{it['stop']}]" if it["stop"] else ""
            self.meta.append(f"- iter {p['iteration']} · THINK{sr} ({p['latency_seconds']:.2f}s)")
            self._tel(f"{self._turn}.{p['iteration']}", p["input_tokens"], p["output_tokens"],
                      None, p["total_cost_usd"], p["latency_seconds"], False)
        elif event == "action":   # M3 — parsed ACTION verb
            it = self.phases[-1]["iterations"][-1]
            it.update(verb=p["verb"], arg=p["arg"], status=p["status"])
            self.meta.append(f"- iter {p['iteration']} · ACT → **{p['verb']}**({p['arg'][:50]}) [{p['status']}]")
        elif event == "tool_use":  # M4 — native tool_use block
            self.phases[-1]["iterations"][-1]["tooluse"] = f"{p['name']}({p['input']})"
            self.meta.append(f"- iter {p['iteration']} · tool_use → **{p['name']}**({p['input']})")
        elif event == "tool_result":
            label = p.get("expr") or p.get("name") or "tool"
            self.phases[-1]["iterations"][-1]["tool"] = f"{label} = {p['result']}"
            self.meta.append(f"- iter {p['iteration']} · tool_result: {label} = {p['result']}")
        elif event == "parse_recovery":
            self.meta.append(f"- iter {p['iteration']} · ! {p['status']} — nudging back to the grammar")
        elif event == "done":
            self.phases[-1].update(final=p["final"], terminal=p["terminal"])
            self.meta.append(f"- ✓ DONE [{p['terminal']}] after {p['iterations']} iters · cum **${p['total_cost_usd']:.6f}**")

    def _tel(self, turn, ctx, out, cost, cum, lat, compacted):
        self.turns_tel[turn] = {"context_tokens": ctx, "output_tokens": out, "cost_usd": cost,
                                "total_cost_usd": cum, "latency_seconds": lat, "compacted": compacted}
        self.telem_rows.append({"turn": turn, "ctx (input tok)": ctx, "out tok": out,
                                "turn $": round(cost, 6) if cost is not None else "",
                                "cumulative $": round(cum, 6), "latency s": round(lat, 2),
                                "compacted": "yes" if compacted else ""})

    # ── record assembly ──────────────────────────────────────────────────────

    def build_record(self, engine, mode: str) -> dict:
        if mode in ("M3", "M4", "M5"):
            turns = []
            for i, ph in enumerate(self.phases, start=1):
                u = self.display[2 * (i - 1)]["content"] if len(self.display) >= 2 * i else ""
                turns.append({"turn": ph["run"], "user": u,
                              "assistant": f"[{ph['terminal']}] {ph['final']}",
                              "iterations": ph["iterations"]})
            num_comp = 0
        else:
            turns = []
            for i, tel in enumerate([r for r in self.telem_rows], start=1):
                tn = tel["turn"]
                u = self.display[2 * (i - 1)]["content"] if len(self.display) >= 2 * i else ""
                a = self.display[2 * (i - 1) + 1]["content"] if len(self.display) >= 2 * i else ""
                turns.append({"turn": tn, "user": u, "assistant": a,
                              "thinking": self.cot_by_turn.get(tn, ""),
                              "telemetry": self.turns_tel.get(tn, {})})
            num_comp = len(self.compactions)
        return {"turns": turns, "compactions": self.compactions,
                "summary": {"turns": len(self.display) // 2,
                            "total_in": engine.total_input_tokens,
                            "total_out": engine.total_output_tokens,
                            "total_cost": engine.total_cost_usd,
                            "num_compactions": num_comp}}

    # ── renderers ────────────────────────────────────────────────────────────

    def chat_value(self): return self.display
    def meta_value(self): return "\n".join(self.meta) if self.meta else "_No turns yet._"

    def telem_df(self):
        cols = ["turn", "ctx (input tok)", "out tok", "turn $", "cumulative $", "latency s", "compacted"]
        return pd.DataFrame(self.telem_rows) if self.telem_rows else pd.DataFrame(columns=cols)

    def balloon_df(self):
        if not self.telem_rows:
            return pd.DataFrame({"step": [], "ctx": []})
        return pd.DataFrame({"step": [str(r["turn"]) for r in self.telem_rows],
                             "ctx": [r["ctx (input tok)"] for r in self.telem_rows]})

    def cot_value(self):
        if not self.cot_by_turn:
            return "_Chain-of-thought (extended thinking) appears here for M2. M3's reasoning is in **Actions / Phases**._"
        return "\n\n---\n\n".join(f"### turn {t}\n\n{txt}" for t, txt in sorted(self.cot_by_turn.items()))

    def compaction_value(self):
        if not self.compactions:
            return "_No compaction yet._"
        out = []
        for c in self.compactions:
            out.append(f"## Compaction before turn {c['turn']}\n\n"
                       f"**BEFORE** ({len(c['before'])} msgs):\n```\n{_fmt(c['before'])}\n```\n\n"
                       f"**SUMMARY** (replaced the old msgs):\n```\n{c['summary']}\n```\n\n"
                       f"**AFTER** ({len(c['after'])} msgs):\n```\n{_fmt(c['after'])}\n```")
        return "\n\n---\n\n".join(out)

    def phases_value(self):
        if not self.phases:
            return "_The Read→Think→Act trace appears here in **M3 / M4** mode._"
        out = []
        for ph in self.phases:
            out.append(f"## Run {ph['run']} — terminal: **{ph['terminal']}**")
            for it in ph["iterations"]:
                think = (it.get("think") or "").strip()[:80]
                stop = f" [{it['stop']}]" if it.get("stop") else ""
                if it.get("verb"):           # M3 parsed action
                    act = f"ACT: **{it['verb']}**({(it.get('arg') or '')[:50]}) [{it.get('status')}]"
                elif it.get("tooluse"):      # M4 native tool_use
                    act = f"tool_use: **{it['tooluse'][:70]}**"
                else:
                    act = "→ answered"
                line = f"- **iter {it['i']}**{stop} · THINK: `{think}` · {act}"
                if it.get("tool"):
                    line += f"\n    - 🛠 {it['tool']}"
                out.append(line)
            out.append(f"  → **final:** {ph['final']}")
        return "\n".join(out)

    def logs_value(self):
        p = self.log.paths
        return (f"**This thread → `traces/witness/`:**\n\n- `{Path(p['json']).name}`\n"
                f"- `{Path(p['md']).name}`\n- `{Path(p['jsonl']).name}` (raw events)\n\n"
                f"_label_ `{self.log.label}` · _id_ `{self.log.session_id}` · _mode_ {self.log.module_mode}")


def _fmt(msgs, width=100):
    return "\n".join(f"[{m.get('role',''):9}] "
                     + (m.get('content','') if len(m.get('content','')) <= width
                        else m.get('content','')[:width - 1] + "…") for m in msgs)


def index_df() -> pd.DataFrame:
    rows = build_index(TRACES_DIR)
    cols = ["label", "id", "module", "turns", "in_tok", "out_tok", "cost_usd",
            "compactions", "thinking", "started", "file"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


# ─────────────────────────────────────────────────────────────────────────────
# Session + handlers
# ─────────────────────────────────────────────────────────────────────────────


def _new_session(system, *, label, module_mode, compact_at=200, thinking=True,
                 keep_last_turns=2, summary_max_tokens=512) -> dict:
    settings = {"compact_at": int(compact_at), "keep_last_turns": int(keep_last_turns),
                "thinking": bool(thinking), "summary_max_tokens": int(summary_max_tokens),
                "system": system or None, "mode": module_mode}
    log = MindMachineLog(TRACES_DIR, label=label, module_mode=module_mode, model=MODEL, settings=settings)
    w = Witness(log, mode=module_mode)
    if module_mode == "M3":
        engine = ThreePhaseAgent(model=MODEL, observer=w.handle)
    elif module_mode == "M4":
        engine = NativeToolAgent(model=MODEL, observer=w.handle)
    elif module_mode == "M5":
        engine = homework_agent(model=MODEL, observer=w.handle)
    else:
        engine = Conversation(system=system or None, model=MODEL, compact_at_tokens=int(compact_at),
                              thinking=bool(thinking), keep_last_turns=int(keep_last_turns),
                              summary_max_tokens=int(summary_max_tokens), observer=w.handle)
    return {"engine": engine, "w": w, "mode": module_mode}


def _render(state: dict):
    # order MUST match `outputs` in build_ui:
    # chat, meta, telem, balloon, phases, cot, compaction, logs, index, state
    w: Witness = state["w"]
    return (w.chat_value(), w.meta_value(), w.telem_df(), w.balloon_df(), w.phases_value(),
            w.cot_value(), w.compaction_value(), w.logs_value(), index_df(), state)


def _run_turn(state: dict, user_text: str) -> None:
    eng, w, mode = state["engine"], state["w"], state["mode"]
    if mode in ("M3", "M4", "M5"):
        r = eng.run(user_text)
        w.display.append({"role": "user", "content": user_text})
        w.display.append({"role": "assistant", "content": f"[{r.terminal}] {r.final}"})
    else:
        r = eng.send(user_text)
        w.display.append({"role": "user", "content": user_text})
        w.display.append({"role": "assistant", "content": r.text})
    w.log.snapshot(w.build_record(eng, mode))


def on_send(user_text, state, unlocked, system, compact_at, thinking, label, module_mode):
    state = state or {}
    # (re)create the session when none exists OR the mode changed (the dropdown
    # is live: switching mode + sending starts a fresh thread in that mode).
    if "engine" not in state or state.get("mode") != module_mode:
        state = _new_session(system, label=label, module_mode=module_mode,
                             compact_at=compact_at, thinking=thinking)
    if not unlocked:
        return _render(state) + ("",)
    if state["mode"] == "M2":
        state["engine"].compact_at_tokens = int(compact_at)
        state["engine"].thinking = bool(thinking)
    if user_text.strip():
        _run_turn(state, user_text)
    return _render(state) + ("",)


def on_seed(state, unlocked, demo_name, system):
    d = DEMOS[demo_name]
    state = _new_session(system, label=demo_name, module_mode=d["module_mode"], **d["settings"])
    if not unlocked:
        yield _render(state) + ("",)
        return
    for line in d["script"]:
        _run_turn(state, line)
        yield _render(state) + ("",)


def on_reset(system, label, module_mode, compact_at, thinking):
    state = _new_session(system, label=label or "scratch", module_mode=module_mode,
                         compact_at=compact_at, thinking=thinking)
    return _render(state) + ("",)


def _check_phrase(phrase):
    if (phrase or "").strip().lower() == CATCH_PHRASE:
        return (gr.update(visible=False), gr.update(visible=True), "", True)
    return (gr.update(visible=True), gr.update(visible=False), "Wrong phrase. Try again.", False)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Witness — Mind & Machine log") as demo:
        gr.Markdown("# The Witness — Mind & Machine log\n"
                    "The agent loop, made observable (Modules 2–5). Pick a **Module mode**: "
                    "M2 = conversation loop, M3 = Read→Think→Act. Every thread is serialized to "
                    "`traces/witness/`.")
        state = gr.State({})
        unlocked = gr.State(value=False)

        with gr.Group(visible=True) as gate:
            gr.Markdown("### Enter catch phrase to continue")
            phrase_in = gr.Textbox(label="Catch phrase", type="password", placeholder="(it's a single word)")
            unlock_btn = gr.Button("Unlock", variant="primary")
            phrase_msg = gr.Markdown("")

        with gr.Group(visible=False) as app:
            with gr.Row():
                with gr.Column(scale=2):
                    chat = gr.Chatbot(label="Conversation (Mind)", height=340)
                    msg = gr.Textbox(label="Your message", placeholder="Type and press Enter…")
                    with gr.Row():
                        send_btn = gr.Button("Send", variant="primary")
                        reset_btn = gr.Button("New thread")
                    with gr.Row():
                        demo_dd = gr.Dropdown(label="Demo thread", choices=list(DEMOS), value="m3-calculate")
                        seed_btn = gr.Button("Run demo")
                with gr.Column(scale=1):
                    gr.Markdown("### Controls")
                    module_dd = gr.Dropdown(label="Module mode", value="M2", choices=["M2", "M3", "M4", "M5"])
                    label_box = gr.Textbox(label="Thread label", value="scratch")
                    system_box = gr.Textbox(label="System prompt (M2)", value=DEFAULT_SYSTEM, lines=2)
                    compact_slider = gr.Slider(50, 4000, value=200, step=50, label="Compaction threshold (M2)")
                    thinking_chk = gr.Checkbox(label="Extended thinking (M2 chain-of-thought)", value=True)
                    demo_note = gr.Markdown("")

            with gr.Tabs():
                with gr.Tab("Harness meta-log"):
                    meta_md = gr.Markdown("_No turns yet._")
                with gr.Tab("Telemetry"):
                    telem_t = gr.Dataframe(label="Per-step ledger (Machine)", interactive=False, wrap=True)
                    balloon = gr.LinePlot(x="step", y="ctx", height=240,
                                          title="The balloon — input tokens shipped per step")
                with gr.Tab("Actions / Phases (M3)"):
                    phases_md = gr.Markdown("_Read→Think→Act trace appears here in M3 mode._")
                with gr.Tab("Chain-of-thought"):
                    cot_md = gr.Markdown("_Extended-thinking CoT (M2)._")
                with gr.Tab("Pre / Post compaction"):
                    compaction_md = gr.Markdown("_No compaction yet._")
                with gr.Tab("Logs & Compare"):
                    logs_md = gr.Markdown("_No active thread._")
                    gr.Markdown("**All serialized threads** (the comparison index):")
                    index_t = gr.Dataframe(label="traces/witness/index.jsonl", interactive=False, wrap=True)
                    refresh_btn = gr.Button("Refresh index")

        outputs = [chat, meta_md, telem_t, balloon, phases_md, cot_md, compaction_md, logs_md, index_t, state]
        send_in = [msg, state, unlocked, system_box, compact_slider, thinking_chk, label_box, module_dd]
        send_btn.click(on_send, send_in, outputs + [msg])
        msg.submit(on_send, send_in, outputs + [msg])
        seed_btn.click(on_seed, [state, unlocked, demo_dd, system_box], outputs + [msg])
        reset_btn.click(on_reset, [system_box, label_box, module_dd, compact_slider, thinking_chk], outputs + [msg])
        demo_dd.change(lambda n: DEMOS[n]["note"], demo_dd, demo_note)
        refresh_btn.click(lambda: index_df(), None, index_t)
        unlock_btn.click(_check_phrase, phrase_in, [gate, app, phrase_msg, unlocked])
        phrase_in.submit(_check_phrase, phrase_in, [gate, app, phrase_msg, unlocked])

    return demo


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7861)
    ap.add_argument("--share", action="store_true")
    args = ap.parse_args()
    os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
    build_ui().launch(server_name=args.host, server_port=args.port,
                      share=args.share, theme=gr.themes.Soft())
