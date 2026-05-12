"""Test the arXiv OAI-PMH XML parser using a saved fixture.

This lets us exercise the parser without hitting the live network.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path

from paper_radar.sources.arxiv import _record_to_paper, NS


def test_parses_one_record(fixtures_dir: Path):
    fixture = fixtures_dir / "arxiv_one_record.xml"
    xml = ET.fromstring(fixture.read_text())
    rec = xml.find("oai:ListRecords/oai:record", NS)
    assert rec is not None
    paper = _record_to_paper(rec)
    assert paper is not None
    assert paper.id.startswith("arxiv:")
    assert paper.title
    assert paper.abstract
    assert len(paper.authors) >= 1
    assert paper.url.startswith("https://arxiv.org/abs/")
    assert paper.categories
