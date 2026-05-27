"""The Mind & Machine log — serialize a witnessed conversation to disk.

Named by the user: *Mind* = the model's interior (conversation + chain-of-
thought); *Machine* = the harness exterior (tokens, cost, latency, the
compaction mechanics). One conversation = one uniquely-identified thread,
written three ways:

  <ts>_<id>_<label>.jsonl   append-only raw event stream — crash-safe truth
  <ts>_<id>_<label>.json    structured record (rewritten each turn, always whole)
  <ts>_<id>_<label>.md      human-readable transcript, for reading / sharing

Comparison across threads is served by a DERIVED index (`index.jsonl`), rebuilt
on demand by scanning the .json files — so the per-thread files stay the single
source of truth and nothing is ever appended into a shared, corruptible log.

This is treatise Part VII (Observance) / curriculum Module 11 (traces &
telemetry), reached early because the user wants a documentary record now —
explicitly NOT resumable session state (that's Module 7/10, deferred).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path


def short_id() -> str:
    """A short, sortable-enough unique id (no uuid dependency needed)."""
    return f"{int(time.time() * 1000) % 0x1000000:06x}"


def _slug(s: str, n: int = 32) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").strip()).strip("-").lower()
    return (s or "untitled")[:n]


def _ts() -> str:
    return time.strftime("%Y%m%dT%H%M%S")


class MindMachineLog:
    def __init__(self, traces_dir: Path, *, label: str, module_mode: str,
                 model: str, settings: dict):
        self.dir = Path(traces_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.session_id = short_id()
        self.label = label or "untitled"
        self.module_mode = module_mode
        self.model = model
        self.settings = settings
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.base = self.dir / f"{_ts()}_{self.session_id}_{_slug(self.label)}"
        # touch the raw stream immediately so a crash before turn 1 still leaves
        # a trace with the header.
        self.event("session_start", {
            "session_id": self.session_id, "label": self.label,
            "module_mode": module_mode, "model": model, "settings": settings,
        })

    # ── raw append-only event stream (source of truth) ───────────────────────

    def event(self, name: str, payload: dict) -> None:
        line = {"t": time.time(), "event": name, **payload}
        with open(f"{self.base}.jsonl", "a") as f:
            # default=str so message lists / odd objects never break the write
            f.write(json.dumps(line, default=str) + "\n")

    # ── structured record + rendered transcript (rewritten each turn) ────────

    def snapshot(self, record: dict) -> None:
        record = {**record,
                  "session_id": self.session_id, "label": self.label,
                  "module_mode": self.module_mode, "model": self.model,
                  "started_at": self.started_at, "settings": self.settings}
        with open(f"{self.base}.json", "w") as f:
            json.dump(record, f, indent=2, default=str)
        with open(f"{self.base}.md", "w") as f:
            f.write(render_md(record))

    @property
    def paths(self) -> dict:
        return {"json": f"{self.base}.json", "md": f"{self.base}.md",
                "jsonl": f"{self.base}.jsonl"}


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────


def render_md(r: dict) -> str:
    s = r.get("settings", {})
    out = [
        f"# Mind & Machine log — {r.get('label','untitled')}",
        "",
        f"- **session id:** `{r.get('session_id','')}`",
        f"- **module mode:** {r.get('module_mode','')}",
        f"- **model:** {r.get('model','')}",
        f"- **started:** {r.get('started_at','')}",
        f"- **settings:** compact_at={s.get('compact_at')} · "
        f"keep_last_turns={s.get('keep_last_turns')} · thinking={s.get('thinking')} · "
        f"summary_max_tokens={s.get('summary_max_tokens')}",
        "",
    ]
    summ = r.get("summary", {})
    if summ:
        out += [
            "## Totals",
            f"- turns: {summ.get('turns')} · in: {summ.get('total_in')} tok · "
            f"out: {summ.get('total_out')} tok · cost: ${summ.get('total_cost', 0):.6f} · "
            f"compactions: {summ.get('num_compactions')}",
            "",
        ]
    out.append("## Conversation (Mind) + telemetry (Machine)")
    for t in r.get("turns", []):
        tel = t.get("telemetry", {})
        flag = " · **COMPACTED before this turn**" if tel.get("compacted") else ""
        out += [
            "",
            f"### Turn {t.get('turn')}{flag}",
            f"**you:** {t.get('user','')}",
            "",
            f"**bot:** {t.get('assistant','')}",
        ]
        if t.get("thinking"):
            out += ["", "<details><summary>chain-of-thought</summary>", "",
                    "```", t["thinking"], "```", "</details>"]
        # M3: the Read→Think→Act iterations within this turn.
        if t.get("iterations"):
            out += ["", "_phases (Read→Think→Act):_"]
            for it in t["iterations"]:
                stop = f" [{it['stop']}]" if it.get("stop") else ""
                if it.get("verb"):          # M3 parsed action
                    act = f"ACT {it.get('verb')}({(it.get('arg') or '')[:50]}) [{it.get('status')}]"
                elif it.get("tooluse"):     # M4 native tool_use
                    act = f"tool_use {it['tooluse'][:70]}"
                else:
                    act = "answered"
                line = f"  - iter {it.get('i')}{stop}: THINK `{(it.get('think') or '').strip()[:80]}` · {act}"
                if it.get("tool"):
                    line += f"  · tool: {it['tool']}"
                out.append(line)
        if tel:
            out += ["",
                    f"_machine: ctx={tel.get('context_tokens')} tok · out={tel.get('output_tokens')} "
                    f"· turn=${tel.get('cost_usd', 0):.6f} · cumulative=${tel.get('total_cost_usd', 0):.6f} "
                    f"· {tel.get('latency_seconds', 0):.2f}s_"]
    comps = r.get("compactions", [])
    if comps:
        out += ["", "## Compactions (history rewritten)"]
        for c in comps:
            out += [
                "",
                f"### before turn {c.get('turn')} — {c.get('summarizing')} msgs summarized, "
                f"{c.get('kept')} kept (${c.get('cost_usd', 0):.6f})",
                "**summary that replaced the older turns:**",
                "```", c.get("summary", ""), "```",
            ]
    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# Derived comparison index — rebuilt by scanning the per-thread .json files
# ─────────────────────────────────────────────────────────────────────────────


def build_index(traces_dir: Path) -> list[dict]:
    """Scan every <thread>.json and write index.jsonl. Returns the rows."""
    traces_dir = Path(traces_dir)
    rows = []
    for jf in sorted(traces_dir.glob("*.json")):
        if jf.name == "index.json":
            continue
        try:
            r = json.loads(jf.read_text())
        except Exception:
            continue
        summ = r.get("summary", {})
        rows.append({
            "label": r.get("label"),
            "id": r.get("session_id"),
            "module": r.get("module_mode"),
            "model": r.get("model"),
            "turns": summ.get("turns"),
            "in_tok": summ.get("total_in"),
            "out_tok": summ.get("total_out"),
            "cost_usd": round(summ.get("total_cost", 0) or 0, 6),
            "compactions": summ.get("num_compactions"),
            "thinking": (r.get("settings", {}) or {}).get("thinking"),
            "started": r.get("started_at"),
            "file": jf.name,
        })
    with open(traces_dir / "index.jsonl", "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return rows


if __name__ == "__main__":
    # CLI: rebuild + print the comparison index.
    import sys
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("traces/witness")
    rows = build_index(d)
    print(f"{len(rows)} threads in {d}")
    for r in rows:
        print(f"  [{r['module']}] {r['label']:<22} {r['id']}  "
              f"turns={r['turns']} in={r['in_tok']} out={r['out_tok']} "
              f"${r['cost_usd']:.6f} compactions={r['compactions']}")
