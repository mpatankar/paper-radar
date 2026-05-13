"""RSS validity tests: ensure feed XML parses and has the right structure."""
from __future__ import annotations
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from paper_radar.config import FeedSpec
from paper_radar.feed import write_feed
from paper_radar.types import Author, Decision, Paper, Affiliation


def test_writes_valid_rss(tmp_path: Path):
    feed = FeedSpec(id="test", title="Test Feed", description="just a test")
    paper = Paper(
        id="arxiv:1234.5678",
        source="arxiv",
        title="A & B's <Funky> Paper",  # tests escaping
        abstract="Body with <tags> & ampersands.",
        authors=[Author(name="Test One", affiliations=[Affiliation(name="Anthropic")])],
        categories=["cs.LG", "cs.AI"],
        url="https://arxiv.org/abs/1234.5678",
        pdf_url="https://arxiv.org/pdf/1234.5678",
        published_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
    )
    decision = Decision(paper_id=paper.id, title=paper.title, accepted=True,
                        tier1_matches=["Anthropic"], feeds=["test"])
    path = write_feed(feed, [(paper, decision)], tmp_path)
    body = path.read_text()
    # parses cleanly
    root = ET.fromstring(body)
    channel = root.find("channel")
    assert channel is not None
    items = channel.findall("item")
    assert len(items) == 1
    item = items[0]
    assert "Funky" in (item.findtext("title") or "")
    assert item.findtext("link") == paper.url
    # categories present
    cats = [c.text for c in item.findall("category")]
    assert "cs.LG" in cats and "cs.AI" in cats
    # description is CDATA-wrapped HTML containing the abstract
    desc = item.findtext("description") or ""
    assert "ampersands" in desc
    assert "Anthropic" in desc


def test_max_items_truncation(tmp_path: Path):
    feed = FeedSpec(id="t", title="t", description="t")
    items = []
    for i in range(50):
        p = Paper(
            id=f"arxiv:{i}",
            source="arxiv",
            title=f"Paper {i}",
            abstract="",
            authors=[],
            categories=["cs.AI"],
            url=f"https://arxiv.org/abs/{i}",
            published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        d = Decision(paper_id=p.id, title=p.title, accepted=True)
        items.append((p, d))
    path = write_feed(feed, items, tmp_path, max_items=10)
    root = ET.fromstring(path.read_text())
    assert len(root.find("channel").findall("item")) == 10


def test_accumulates_across_runs(tmp_path: Path):
    """A second call to write_feed must NOT drop the prior run's items."""
    feed = FeedSpec(id="accumulate", title="t", description="t")

    def mk(idx: int, day: int) -> tuple[Paper, Decision]:
        p = Paper(
            id=f"arxiv:{idx}",
            source="arxiv",
            title=f"Paper {idx}",
            abstract="",
            authors=[],
            categories=["cs.AI"],
            url=f"https://arxiv.org/abs/{idx}",
            published_at=datetime(2026, 5, day, tzinfo=timezone.utc),
        )
        d = Decision(paper_id=p.id, title=p.title, accepted=True)
        return p, d

    # Yesterday's run emits papers 1, 2, 3 (May 1)
    write_feed(feed, [mk(1, 1), mk(2, 1), mk(3, 1)], tmp_path)
    # Today's run emits papers 4, 5 (May 2). Should not drop 1, 2, 3.
    path = write_feed(feed, [mk(4, 2), mk(5, 2)], tmp_path)
    items = ET.fromstring(path.read_text()).find("channel").findall("item")
    guids = [i.findtext("guid") for i in items]
    assert set(guids) == {"arxiv:1", "arxiv:2", "arxiv:3", "arxiv:4", "arxiv:5"}
    # Newest (May 2) should come first.
    assert guids[0] in ("arxiv:4", "arxiv:5")
    assert guids[-1] in ("arxiv:1", "arxiv:2", "arxiv:3")


def test_new_run_overwrites_same_guid(tmp_path: Path):
    """If a paper appears in both runs (same guid), the newer render wins."""
    feed = FeedSpec(id="overwrite", title="t", description="t")
    p1 = Paper(id="arxiv:42", source="arxiv", title="Old title", abstract="old", authors=[],
               categories=[], url="https://arxiv.org/abs/42",
               published_at=datetime(2026, 5, 1, tzinfo=timezone.utc))
    d1 = Decision(paper_id=p1.id, title=p1.title, accepted=True)
    write_feed(feed, [(p1, d1)], tmp_path)

    p2 = Paper(id="arxiv:42", source="arxiv", title="New title", abstract="new", authors=[],
               categories=[], url="https://arxiv.org/abs/42",
               published_at=datetime(2026, 5, 2, tzinfo=timezone.utc))
    d2 = Decision(paper_id=p2.id, title=p2.title, accepted=True)
    path = write_feed(feed, [(p2, d2)], tmp_path)

    items = ET.fromstring(path.read_text()).find("channel").findall("item")
    assert len(items) == 1
    assert items[0].findtext("title") == "New title"


def test_handles_missing_existing_file(tmp_path: Path):
    """First-ever run: no existing file. Should just write fresh."""
    feed = FeedSpec(id="fresh", title="t", description="t")
    p = Paper(id="arxiv:1", source="arxiv", title="P", abstract="", authors=[],
              categories=[], url="https://arxiv.org/abs/1",
              published_at=datetime(2026, 5, 1, tzinfo=timezone.utc))
    d = Decision(paper_id=p.id, title=p.title, accepted=True)
    path = write_feed(feed, [(p, d)], tmp_path)
    items = ET.fromstring(path.read_text()).find("channel").findall("item")
    assert len(items) == 1
