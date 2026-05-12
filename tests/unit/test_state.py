"""Basic tests for the dedupe / run-tracking state."""
from __future__ import annotations
from pathlib import Path

from paper_radar.state import State
from paper_radar.types import Paper


def make_paper(pid):
    return Paper(id=pid, source="arxiv", title="t", abstract="", authors=[], categories=[], url="x")


def test_has_seen_round_trips(tmp_path: Path):
    with State(tmp_path) as s:
        p = make_paper("arxiv:1.1")
        assert not s.has_seen(p.id)
        s.mark_seen(p, feeds=["everything"])
        assert s.has_seen(p.id)


def test_record_and_recent_runs(tmp_path: Path):
    with State(tmp_path) as s:
        s.record_run(started_at=1000, n_seen=10, n_accepted=4, payload={"per_feed_counts": {"everything": 4}})
        s.record_run(started_at=2000, n_seen=20, n_accepted=8, payload={"per_feed_counts": {"everything": 8}})
        runs = list(s.recent_runs(limit=10))
    assert len(runs) == 2
    assert runs[0]["started_at"] == 2000   # most recent first
    assert runs[0]["payload"]["per_feed_counts"]["everything"] == 8
