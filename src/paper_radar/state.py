"""SQLite-backed state: which papers have been emitted, and per-feed history.

Used for cross-run dedupe and to power `paper-radar stats --since 7d`.
"""
from __future__ import annotations
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Iterable

from paper_radar.types import Decision, Paper


class State:
    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.state_dir / "seen.sqlite")
        self.db.row_factory = sqlite3.Row
        self._init_schema()

    def __enter__(self): return self
    def __exit__(self, *a): self.close()
    def close(self): self.db.close()

    def _init_schema(self):
        with closing(self.db.cursor()) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS seen (
                    paper_id TEXT PRIMARY KEY,
                    title TEXT,
                    feeds_json TEXT,
                    first_seen_at INTEGER
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    started_at INTEGER PRIMARY KEY,
                    finished_at INTEGER,
                    n_seen INTEGER,
                    n_accepted INTEGER,
                    payload_json TEXT
                )
            """)
        self.db.commit()

    # --- public API ----------------------------------------------------------

    def has_seen(self, paper_id: str) -> bool:
        with closing(self.db.cursor()) as c:
            r = c.execute("SELECT 1 FROM seen WHERE paper_id=?", (paper_id,)).fetchone()
        return r is not None

    def mark_seen(self, paper: Paper, feeds: list[str]):
        with closing(self.db.cursor()) as c:
            c.execute("""INSERT OR REPLACE INTO seen (paper_id, title, feeds_json, first_seen_at)
                         VALUES (?, ?, ?, COALESCE((SELECT first_seen_at FROM seen WHERE paper_id=?), ?))""",
                      (paper.id, paper.title, json.dumps(feeds), paper.id, int(time.time())))
        self.db.commit()

    def record_run(self, started_at: int, n_seen: int, n_accepted: int, payload: dict):
        with closing(self.db.cursor()) as c:
            c.execute("""INSERT OR REPLACE INTO runs
                         (started_at, finished_at, n_seen, n_accepted, payload_json)
                         VALUES (?, ?, ?, ?, ?)""",
                      (started_at, int(time.time()), n_seen, n_accepted, json.dumps(payload)))
        self.db.commit()

    def recent_runs(self, limit: int = 30) -> Iterable[dict]:
        with closing(self.db.cursor()) as c:
            rows = c.execute("""SELECT started_at, finished_at, n_seen, n_accepted, payload_json
                                FROM runs ORDER BY started_at DESC LIMIT ?""", (limit,)).fetchall()
        for r in rows:
            yield {
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "n_seen": r["n_seen"],
                "n_accepted": r["n_accepted"],
                "payload": json.loads(r["payload_json"] or "{}"),
            }
