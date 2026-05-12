"""Tests for the filter engine — the heart of the system.

These tests use hand-built Papers so they exercise the filter without any
network calls. The fixtures hand back a real Config from config/.
"""
from __future__ import annotations
from datetime import datetime, timezone
import pytest

from paper_radar.filter import Filter
from paper_radar.types import Affiliation, Author, Paper


def make_paper(
    *,
    title: str = "A paper",
    abstract: str = "abstract body",
    categories: list[str] | None = None,
    authors: list[Author] | None = None,
    source: str = "arxiv",
) -> Paper:
    return Paper(
        id="arxiv:fake.0001",
        source=source,
        title=title,
        abstract=abstract,
        authors=authors or [],
        categories=categories or ["cs.CL"],
        url="https://arxiv.org/abs/fake.0001",
        pdf_url="https://arxiv.org/pdf/fake.0001",
        published_at=datetime.now(timezone.utc),
        raw={"arxiv_id": "fake.0001"},
    )


def aff(name: str) -> Affiliation:
    return Affiliation(name=name, raw=name)


# --- tier 1 ------------------------------------------------------------------

def test_tier1_any_author_accepts(config):
    paper = make_paper(authors=[
        Author(name="Random Person", affiliations=[aff("Some Small University")]),
        Author(name="Lab Person", affiliations=[aff("Google DeepMind")]),
    ])
    decision = Filter(config).evaluate(paper)
    assert decision.accepted
    assert "Google DeepMind" in decision.tier1_matches


def test_tier1_no_match_rejects(config):
    paper = make_paper(authors=[
        Author(name="X", affiliations=[aff("Tiny College")]),
    ])
    decision = Filter(config).evaluate(paper)
    assert not decision.accepted
    assert decision.tier1_matches == []


def test_anthropic_matches_for_blog(config):
    paper = make_paper(authors=[
        Author(name="Researcher", affiliations=[aff("Anthropic")]),
    ], source="anthropic")
    decision = Filter(config).evaluate(paper)
    assert decision.accepted
    assert "Anthropic" in decision.tier1_matches


# --- tier 2 senior-only ------------------------------------------------------

def test_tier2_grad_student_no_senior_rejected(config):
    """First author at Stanford, no senior-author signal anywhere → rejected."""
    paper = make_paper(authors=[
        Author(name="Junior X", affiliations=[aff("Stanford University")],
               h_index=3, cited_by_count=20),
        Author(name="Other", affiliations=[aff("Stanford University")],
               h_index=5, cited_by_count=100),
    ])
    decision = Filter(config).evaluate(paper)
    assert not decision.accepted, "tier-2 with no senior author should be rejected"
    assert "Stanford" in decision.tier2_matches  # matched the lab but didn't accept
    assert decision.senior_authors == []


def test_tier2_with_senior_last_author_accepted(config):
    """Last author is senior + at Stanford → accepted."""
    paper = make_paper(authors=[
        Author(name="Junior", affiliations=[aff("Stanford University")],
               h_index=3, cited_by_count=10),
        Author(name="Senior Prof", affiliations=[aff("Stanford University")],
               h_index=80, cited_by_count=50000),
    ])
    decision = Filter(config).evaluate(paper)
    assert decision.accepted
    assert "Stanford" in decision.tier2_matches
    assert "Senior Prof" in decision.senior_authors


def test_tier2_senior_middle_author_rejected_in_first_or_last_mode(config):
    """Middle author is senior but config requires first/last position senior."""
    paper = make_paper(authors=[
        Author(name="A", affiliations=[aff("Stanford University")], h_index=3),
        Author(name="Senior Middle", affiliations=[aff("Stanford University")], h_index=80, cited_by_count=50000),
        Author(name="B", affiliations=[aff("Stanford University")], h_index=3),
    ])
    decision = Filter(config).evaluate(paper)
    # senior_positions is [first, last] by default → middle senior shouldn't count.
    assert "Senior Middle" not in decision.senior_authors
    assert not decision.accepted


# --- routing -----------------------------------------------------------------

def test_routes_to_relevant_feeds(config):
    """A tier-1 alignment-themed paper should land in alignment-safety + everything."""
    paper = make_paper(
        title="Sleeper agents and constitutional AI alignment",
        abstract="We study interpretability and red-team scenarios for RLHF-trained models.",
        categories=["cs.LG"],
        authors=[Author(name="X", affiliations=[aff("Anthropic")])],
    )
    decision = Filter(config).evaluate(paper)
    assert decision.accepted
    assert "alignment-safety" in decision.feeds
    assert "everything" in decision.feeds


def test_excluded_keyword_drops_from_feed(config):
    paper = make_paper(
        title="A survey of language models",
        abstract="We survey recent work in LLMs.",
        categories=["cs.CL"],
        authors=[Author(name="X", affiliations=[aff("Anthropic")])],
    )
    decision = Filter(config).evaluate(paper)
    # Accepted overall but excluded from frontier-llm
    assert decision.accepted
    assert "frontier-llm" not in decision.feeds  # "survey" excluded
    # `everything` always present
    assert "everything" in decision.feeds


def test_no_arxiv_category_match_excluded_from_topical_feed(config):
    paper = make_paper(
        title="A robotics paper",
        abstract="manipulation control",
        categories=["cs.RO"],
        authors=[Author(name="X", affiliations=[aff("Anthropic")])],
    )
    decision = Filter(config).evaluate(paper)
    assert decision.accepted
    assert "robotics-embodied" in decision.feeds
    assert "frontier-llm" not in decision.feeds


# --- manual override ---------------------------------------------------------

def test_manual_must_include_overrides_rejection(config):
    config.enrich.manual_must_include = ["Famous Researcher"]
    paper = make_paper(authors=[
        Author(name="Famous Researcher", affiliations=[aff("Tiny College")]),
    ])
    decision = Filter(config).evaluate(paper)
    assert decision.accepted
    assert any("manual must-include" in r for r in decision.reasons)


# --- explain output ----------------------------------------------------------

def test_explain_renders_readable_output(config):
    paper = make_paper(authors=[
        Author(name="Senior Prof", affiliations=[aff("Stanford University")],
               h_index=70, cited_by_count=50000),
    ])
    text = Filter(config).explain(paper)
    assert "Senior Prof" in text
    assert "Stanford" in text
    assert "ACCEPTED" in text
    assert "Stanford" in text
