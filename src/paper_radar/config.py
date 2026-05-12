"""Config loading.

We keep three YAML files for separation of concerns:
  config.yaml      — runtime knobs (sources, filter thresholds, output)
  allowlist.yaml   — tier 1 / tier 2 institutions
  feeds.yaml       — feed definitions (categories, keywords)

This module loads all three and gives the rest of the codebase typed access.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class Institution:
    name: str
    match: list[str]
    country: str = ""
    tier: int = 0   # 1 or 2

    def matches(self, candidate: str) -> bool:
        """True if `candidate` (an affiliation string) contains any match pattern."""
        if not candidate:
            return False
        c = candidate.lower()
        return any(p.lower() in c for p in self.match)


@dataclass
class FeedSpec:
    id: str
    title: str
    description: str
    arxiv_categories: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    keywords_any: list[str] = field(default_factory=list)
    exclude_if_keyword: list[str] = field(default_factory=list)


@dataclass
class FilterConfig:
    tier_1_mode: str = "any_author"
    tier_2_mode: str = "senior_only"
    senior_h_index_threshold: int = 30
    senior_cite_threshold: int = 5000
    senior_positions: list[str] = field(default_factory=lambda: ["first", "last"])


@dataclass
class ArxivConfig:
    enabled: bool = True
    sets: list[str] = field(default_factory=list)
    days_back: int = 1
    max_records: int = 5000


@dataclass
class BlogsConfig:
    enabled: bool = True
    enabled_adapters: list[str] = field(default_factory=list)


@dataclass
class EnrichConfig:
    resolve_affiliations: bool = True
    resolve_h_index: bool = True
    manual_must_include: list[str] = field(default_factory=list)


@dataclass
class OutputConfig:
    feeds_dir: str = "feeds_out"
    state_dir: str = "data"
    publish_landing_page: bool = True
    dedupe_across_runs: bool = True
    always_emit_everything: bool = True
    feed_max_items: int = 200


@dataclass
class LoggingConfig:
    level: str = "INFO"
    decisions_jsonl: str = "data/decisions.jsonl"


@dataclass
class Config:
    arxiv: ArxivConfig
    blogs: BlogsConfig
    filter: FilterConfig
    enrich: EnrichConfig
    output: OutputConfig
    logging: LoggingConfig

    tier_1: list[Institution] = field(default_factory=list)
    tier_2: list[Institution] = field(default_factory=list)
    feeds: list[FeedSpec] = field(default_factory=list)

    @property
    def all_institutions(self) -> list[Institution]:
        return self.tier_1 + self.tier_2

    def find_feed(self, feed_id: str) -> Optional[FeedSpec]:
        for f in self.feeds:
            if f.id == feed_id:
                return f
        return None


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_config(config_dir: Optional[Path] = None) -> Config:
    """Load configuration from YAML files.

    Pass an explicit `config_dir` to load from a non-standard location (handy in
    tests). Otherwise, looks at $PAPER_RADAR_CONFIG_DIR then `./config`.
    """
    if config_dir is None:
        env_dir = os.environ.get("PAPER_RADAR_CONFIG_DIR")
        config_dir = Path(env_dir) if env_dir else Path("config")
    config_dir = Path(config_dir)

    main = _load_yaml(config_dir / "config.yaml")
    allow = _load_yaml(config_dir / "allowlist.yaml")
    feeds = _load_yaml(config_dir / "feeds.yaml")

    tier1 = [Institution(**i, tier=1) for i in allow.get("tier_1_frontier_labs", [])]
    tier2 = [Institution(**i, tier=2) for i in allow.get("tier_2_academic_labs", [])]

    feed_specs = [FeedSpec(**f) for f in feeds.get("feeds", [])]

    return Config(
        arxiv=ArxivConfig(**main.get("arxiv", {})),
        blogs=BlogsConfig(**main.get("blogs", {})),
        filter=FilterConfig(**main.get("filter", {})),
        enrich=EnrichConfig(**main.get("enrich", {})),
        output=OutputConfig(**main.get("output", {})),
        logging=LoggingConfig(**main.get("logging", {})),
        tier_1=tier1,
        tier_2=tier2,
        feeds=feed_specs,
    )
