"""Top-level orchestration: pull → enrich → filter → write feeds.

A run is a single function call. Tests bypass this and call individual
modules directly; the CLI calls `run_once()`.
"""
from __future__ import annotations
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from paper_radar.config import Config
from paper_radar.filter import Filter
from paper_radar.feed import write_feed, write_landing_page
from paper_radar.resolver import Resolver
from paper_radar.sources import arxiv as arxiv_source
from paper_radar.sources.blogs import run_enabled as run_blog_adapters
from paper_radar.state import State
from paper_radar.stats import build_stats, write_stats
from paper_radar.types import Decision, Paper

log = logging.getLogger(__name__)


def run_once(cfg: Config, *, dry_run: bool = False) -> dict:
    """One full daily run. Returns the stats dict for convenience.

    `dry_run=True` performs everything except writing output files.
    """
    started_at = int(time.time())
    state_dir = Path(cfg.output.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    feeds_dir = Path(cfg.output.feeds_dir)
    feeds_dir.mkdir(parents=True, exist_ok=True)

    state = State(state_dir)

    # 1. Pull
    log.info("=== pulling papers ===")
    papers: list[Paper] = []
    if cfg.arxiv.enabled:
        for p in arxiv_source.fetch_recent(cfg.arxiv):
            papers.append(p)
    if cfg.blogs.enabled:
        for p in run_blog_adapters(cfg.blogs.enabled_adapters):
            papers.append(p)
    log.info("pulled %d total papers (arxiv + blogs)", len(papers))

    # Drop already-seen papers (cross-run dedupe)
    if cfg.output.dedupe_across_runs:
        before = len(papers)
        papers = [p for p in papers if not state.has_seen(p.id)]
        log.info("dedupe: %d -> %d (skipped %d already-emitted)", before, len(papers), before - len(papers))

    # 2. Enrich (parallelized — most time is OpenAlex network I/O)
    resolver_stats = {}
    if cfg.enrich.resolve_affiliations:
        log.info("=== enriching authors via OpenAlex ===")
        with Resolver(state_dir, cfg.enrich) as resolver:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            n_workers = 4    # OpenAlex polite-pool allows ~10 req/s with mailto
            done = 0
            with ThreadPoolExecutor(max_workers=n_workers) as pool:
                futures = {pool.submit(resolver.enrich, p): p for p in papers}
                for fut in as_completed(futures):
                    done += 1
                    if done % 50 == 0:
                        log.info("enriched %d/%d (cache_hits=%d openalex_hits=%d unresolved=%d)",
                                 done, len(papers),
                                 resolver.stats["cache_hits"], resolver.stats["openalex_hits"],
                                 resolver.stats["unresolved"])
            resolver_stats = dict(resolver.stats)

    # 3. Filter
    log.info("=== filtering ===")
    filt = Filter(cfg)
    decisions: list[Decision] = []
    for p in papers:
        decisions.append(filt.evaluate(p))
    accepted = sum(1 for d in decisions if d.accepted)
    log.info("filter: %d accepted of %d", accepted, len(papers))

    # 4. Write decisions log (always — useful for `paper-radar explain` later)
    if not dry_run:
        decisions_path = Path(cfg.logging.decisions_jsonl)
        decisions_path.parent.mkdir(parents=True, exist_ok=True)
        # Append, but truncate to last 30 days worth by simple line count if too big.
        with decisions_path.open("a") as f:
            for d in decisions:
                f.write(json.dumps({"run_started_at": started_at, **d.to_dict()}) + "\n")

    # 5. Route + write feeds
    items_by_feed: dict[str, list[tuple[Paper, Decision]]] = {f.id: [] for f in cfg.feeds}
    for p, d in zip(papers, decisions):
        if not d.accepted:
            continue
        for feed_id in d.feeds:
            items_by_feed.setdefault(feed_id, []).append((p, d))
        state.mark_seen(p, d.feeds)

    feed_item_counts: dict[str, int] = {}
    if not dry_run:
        for feed in cfg.feeds:
            items = items_by_feed.get(feed.id, [])
            write_feed(feed, items, feeds_dir, max_items=cfg.output.feed_max_items)
            feed_item_counts[feed.id] = len(items)
        if cfg.output.publish_landing_page:
            write_landing_page(cfg.feeds, feeds_dir, feed_item_counts)

    # 6. Stats
    stats = build_stats(
        seen=papers,
        decisions=decisions,
        resolver_stats=resolver_stats,
        config_snapshot={
            "tier_1_count": len(cfg.tier_1),
            "tier_2_count": len(cfg.tier_2),
            "tier_2_mode": cfg.filter.tier_2_mode,
            "senior_h_index_threshold": cfg.filter.senior_h_index_threshold,
            "senior_cite_threshold": cfg.filter.senior_cite_threshold,
        },
    )
    stats["per_feed_counts"] = feed_item_counts or stats["per_feed_counts"]
    if not dry_run:
        write_stats(stats, feeds_dir)
        state.record_run(started_at, len(papers), accepted, stats)
    state.close()
    return stats
