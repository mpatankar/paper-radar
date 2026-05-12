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
