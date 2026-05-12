"""Filter engine.

Given an enriched Paper + Config, decide:
  1. Does it pass the global allowlist filter?
     - Tier 1 (frontier labs): any-author match by default
     - Tier 2 (academic labs): senior-author match (first OR last + h-index/cites threshold)
  2. If accepted, which feeds does it route to?

Every paper gets a `Decision` record. Decisions are written to a JSONL log so
you can introspect after the fact:
    paper-radar explain arxiv:2501.12345
    grep '"accepted": true' data/decisions.jsonl | wc -l

The filter is intentionally one-class / pure-function-style: it doesn't talk
to the network. Easy to unit test.
"""
from __future__ import annotations
import logging
from typing import Iterable

from paper_radar.config import Config, FeedSpec, FilterConfig, Institution
from paper_radar.types import Author, Decision, Paper

log = logging.getLogger(__name__)


class Filter:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.tier1 = cfg.tier_1
        self.tier2 = cfg.tier_2
        self.feeds = cfg.feeds

    # --- public API ----------------------------------------------------------

    def evaluate(self, paper: Paper) -> Decision:
        """Run the full pipeline for one Paper, returning a Decision.

        A Decision always exists, even when the paper is rejected — that's how
        we keep the explainability story honest.
        """
        decision = Decision(paper_id=paper.id, title=paper.title, accepted=False)
        self._annotate_authors(paper, decision)

        t1 = decision.tier1_matches
        t2_senior = [a.name for a in paper.authors if a.is_senior and self._matched_tier(a, 2)]
        decision.senior_authors = list(set(t2_senior))

        # Tier 1: any author from a tier-1 lab
        passes_t1 = bool(t1) and self.cfg.filter.tier_1_mode != "disabled"

        # Tier 2: needs at least one senior-position author at a tier-2 lab.
        passes_t2 = False
        if self.cfg.filter.tier_2_mode == "any_author":
            passes_t2 = bool(decision.tier2_matches)
        elif self.cfg.filter.tier_2_mode == "senior_only":
            passes_t2 = self._has_senior_at_tier(paper, 2)
        elif self.cfg.filter.tier_2_mode == "first_or_last_senior":
            passes_t2 = self._has_senior_at_position(paper, 2, self.cfg.filter.senior_positions)
        elif self.cfg.filter.tier_2_mode == "disabled":
            passes_t2 = False

        # Manual override: any name on the must-include list also passes.
        manual = [a.name for a in paper.authors
                  if a.name in (self.cfg.enrich.manual_must_include or [])]
        if manual:
            decision.reasons.append(f"manual must-include: {', '.join(manual)}")

        if passes_t1:
            decision.reasons.append(f"tier-1 match: {', '.join(sorted(set(t1)))}")
        if passes_t2:
            decision.reasons.append(
                f"tier-2 senior author at {', '.join(sorted(set(decision.tier2_matches)))}"
            )

        decision.accepted = bool(passes_t1 or passes_t2 or manual)
        if not decision.accepted:
            decision.reasons.append("no tier-1 author and no tier-2 senior author")
            return decision

        # Route to feeds.
        for feed in self.feeds:
            included, why = self._route_to_feed(paper, feed)
            if included:
                decision.feeds.append(feed.id)
                if why:
                    decision.matched_keywords.setdefault(feed.id, []).extend(why)
            else:
                decision.rejected_by_feed[feed.id] = why or "did not match"

        # Always-include everything (if enabled and not already there)
        if self.cfg.output.always_emit_everything and "everything" not in decision.feeds:
            if any(f.id == "everything" for f in self.feeds):
                decision.feeds.append("everything")

        return decision

    def explain(self, paper: Paper) -> str:
        """Human-readable narration of the full decision. For CLI introspection."""
        d = self.evaluate(paper)
        lines = []
        lines.append(f"Paper:  {paper.title}")
        lines.append(f"ID:     {paper.id}")
        lines.append(f"Source: {paper.source}")
        lines.append(f"Cats:   {' '.join(paper.categories)}")
        lines.append("")
        lines.append("Authors:")
        for a in paper.authors:
            affs = "; ".join(af.name for af in a.affiliations) or "—"
            sen = " [SENIOR]" if a.is_senior else ""
            hidx = f"h={a.h_index}" if a.h_index is not None else "h=?"
            cites = f"cites={a.cited_by_count}" if a.cited_by_count is not None else ""
            lines.append(f"  - {a.name}{sen}  ({hidx} {cites})  → {affs}")
        lines.append("")
        lines.append("Decision: " + ("ACCEPTED" if d.accepted else "REJECTED"))
        for r in d.reasons:
            lines.append(f"  · {r}")
        if d.tier1_matches:
            lines.append(f"  Tier-1 labs matched: {', '.join(sorted(set(d.tier1_matches)))}")
        if d.tier2_matches:
            lines.append(f"  Tier-2 labs matched: {', '.join(sorted(set(d.tier2_matches)))}")
        if d.senior_authors:
            lines.append(f"  Senior authors:      {', '.join(d.senior_authors)}")
        if d.accepted:
            lines.append(f"  Feeds:               {', '.join(d.feeds) or '—'}")
            for feed_id, kws in (d.matched_keywords or {}).items():
                if kws:
                    lines.append(f"    {feed_id} matched: {', '.join(kws)}")
            for feed_id, why in (d.rejected_by_feed or {}).items():
                lines.append(f"    {feed_id} skipped: {why}")
        return "\n".join(lines)

    # --- helpers -------------------------------------------------------------

    def _annotate_authors(self, paper: Paper, decision: Decision):
        """Set Author.is_senior and fill Decision tier matches in place."""
        n = len(paper.authors)
        senior_positions = set(self.cfg.filter.senior_positions or [])
        for i, author in enumerate(paper.authors):
            # Match this author's affiliations to allowlist.
            for inst in self.tier1:
                if any(inst.matches(a.name) or inst.matches(a.raw) for a in author.affiliations):
                    decision.tier1_matches.append(inst.name)
            for inst in self.tier2:
                if any(inst.matches(a.name) or inst.matches(a.raw) for a in author.affiliations):
                    decision.tier2_matches.append(inst.name)

            # Mark senior. Position-based ∧ stat-based.
            is_position_senior = False
            if "first" in senior_positions and i == 0:
                is_position_senior = True
            if "last" in senior_positions and i == n - 1:
                is_position_senior = True
            if "any" in senior_positions:
                is_position_senior = True

            is_stat_senior = (
                (author.h_index is not None and author.h_index >= self.cfg.filter.senior_h_index_threshold)
                or (author.cited_by_count is not None and author.cited_by_count >= self.cfg.filter.senior_cite_threshold)
            )
            author.is_senior = bool(is_position_senior and is_stat_senior)

        decision.tier1_matches = list(set(decision.tier1_matches))
        decision.tier2_matches = list(set(decision.tier2_matches))

    def _matched_tier(self, author: Author, tier: int) -> bool:
        insts = self.tier1 if tier == 1 else self.tier2
        for inst in insts:
            for a in author.affiliations:
                if inst.matches(a.name) or inst.matches(a.raw):
                    return True
        return False

    def _has_senior_at_tier(self, paper: Paper, tier: int) -> bool:
        for a in paper.authors:
            if a.is_senior and self._matched_tier(a, tier):
                return True
        return False

    def _has_senior_at_position(self, paper: Paper, tier: int, positions: Iterable[str]) -> bool:
        pos_set = set(positions)
        n = len(paper.authors)
        for i, a in enumerate(paper.authors):
            if not a.is_senior:
                continue
            if not self._matched_tier(a, tier):
                continue
            if ("first" in pos_set and i == 0) or ("last" in pos_set and i == n - 1):
                return True
        return False

    def _route_to_feed(self, paper: Paper, feed: FeedSpec) -> tuple[bool, str]:
        # everything feed: always include
        if feed.id == "everything":
            return True, ""

        if feed.arxiv_categories and not any(c in feed.arxiv_categories for c in paper.categories):
            # Exception: non-arXiv sources don't have arXiv cats — route by source instead.
            if paper.source == "arxiv":
                return False, "no arxiv category match"

        if feed.sources and paper.source not in feed.sources:
            return False, "source not in feed.sources"

        text = (paper.title + " " + paper.abstract).lower()
        if feed.exclude_if_keyword:
            for kw in feed.exclude_if_keyword:
                if kw.lower() in text:
                    return False, f"excluded keyword: {kw}"

        matched: list[str] = []
        if feed.keywords_any:
            for kw in feed.keywords_any:
                if kw.lower() in text:
                    matched.append(kw)
            if not matched:
                return False, "no keyword match"

        return True, ",".join(matched)
