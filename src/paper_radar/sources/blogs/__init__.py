"""Blog adapters for frontier-lab research pages.

Each adapter is a tiny function that returns an iterable of `Paper` records.
Adapters live in their own modules so each one can be debugged / rewritten /
disabled in isolation without touching the others.

To add a new lab:
  1. Create src/paper_radar/sources/blogs/<lab>.py with a `fetch()` function
     returning Iterable[Paper]. Use the helpers in `_common.py` for RSS/HTML.
  2. Register it in ADAPTERS below.
  3. Add it to `blogs.enabled_adapters` in config.yaml.

Adapters are responsible for setting the right `lab` on the Paper so the
filter knows it's already a tier-1 source without OpenAlex enrichment.
"""
from __future__ import annotations
import logging
from typing import Callable, Iterable

from paper_radar.types import Paper

from . import _common
from . import (
    anthropic, openai_blog, deepmind, transformer_circuits,
    physical_intelligence, thinking_machines, goodfire,
    meta_ai, nvidia_research, mistral, microsoft_research, arc_institute,
    huggingface_papers, ai2, apple_ml, boston_dynamics, figure_ai,
)

log = logging.getLogger(__name__)

# Adapter name -> fetch function. The fetch function takes no arguments and
# returns an iterable of Papers. One broken adapter doesn't kill the run —
# `run_enabled` catches exceptions per-adapter.
ADAPTERS: dict[str, Callable[[], Iterable[Paper]]] = {
    "anthropic":             anthropic.fetch,
    "openai":                openai_blog.fetch,
    "google_deepmind":       deepmind.fetch,
    "transformer_circuits":  transformer_circuits.fetch,
    "physical_intelligence": physical_intelligence.fetch,
    "thinking_machines":     thinking_machines.fetch,
    "goodfire":              goodfire.fetch,
    "meta_ai":               meta_ai.fetch,
    "nvidia_research":       nvidia_research.fetch,
    "mistral":               mistral.fetch,
    "microsoft_research":    microsoft_research.fetch,
    "arc_institute":         arc_institute.fetch,
    "huggingface_papers":    huggingface_papers.fetch,
    "ai2":                   ai2.fetch,
    "apple_ml":              apple_ml.fetch,
    "boston_dynamics":       boston_dynamics.fetch,
    "figure_ai":             figure_ai.fetch,
}


def run_enabled(enabled: list[str]) -> Iterable[Paper]:
    for name in enabled:
        fn = ADAPTERS.get(name)
        if fn is None:
            log.warning("unknown blog adapter: %s", name)
            continue
        try:
            yield from fn()
        except Exception as e:
            log.exception("blog adapter %s crashed: %s", name, e)
