"""The Store — durable home for a Mind (SCHEMA.md, invariant 4: identity = config + state).

Pure persistence of the declarative data. Two JSON documents per mind, keyed by
`mind_id`: the config (written once, the identity) and the state (checkpointed
continuously, the continuum). SQLite so it's queryable and survives any process;
JSON columns so the documents stay diffable and S3-syncable later.

No behavior here beyond save/load — this is the boundary where the Mind rests
when no body is animating it.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Store:
    def __init__(self, db_path: str | Path):
        self.db = sqlite3.connect(str(db_path))
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS minds "
            "(mind_id TEXT PRIMARY KEY, config_json TEXT, created_at TEXT)")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS states "
            "(mind_id TEXT PRIMARY KEY, state_json TEXT, updated_at TEXT)")
        self.db.commit()

    # config — write-once identity (we never UPDATE it from the runtime: the
    # ontological lock lives one layer up, but storing it via a create-only path
    # keeps the discipline visible).
    def save_config(self, config: dict) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO minds VALUES (?,?,?)",
            (config["mind_id"], json.dumps(config), config.get("created_at", now_iso())))
        self.db.commit()

    def load_config(self, mind_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT config_json FROM minds WHERE mind_id=?", (mind_id,)).fetchone()
        return json.loads(row[0]) if row else None

    # state — checkpointed continuously.
    def save_state(self, state: dict) -> None:
        state["updated_at"] = now_iso()
        self.db.execute(
            "INSERT OR REPLACE INTO states VALUES (?,?,?)",
            (state["mind_id"], json.dumps(state), state["updated_at"]))
        self.db.commit()

    def load_state(self, mind_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT state_json FROM states WHERE mind_id=?", (mind_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_minds(self) -> list[dict]:
        out = []
        for mid, label, created in self.db.execute(
                "SELECT m.mind_id, m.config_json, m.created_at FROM minds m"):
            cfg = json.loads(label)
            st = self.load_state(mid) or {}
            out.append({"mind_id": mid, "label": cfg.get("label"),
                        "status": st.get("status"), "created_at": created})
        return out
