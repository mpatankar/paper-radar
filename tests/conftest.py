"""Shared pytest fixtures."""
from __future__ import annotations
import sys
from pathlib import Path

# Make `paper_radar` importable when running pytest from the repo root.
SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
from paper_radar.config import load_config


@pytest.fixture
def config():
    """Loaded config from the real config/ directory."""
    config_dir = Path(__file__).parent.parent / "config"
    return load_config(config_dir)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
