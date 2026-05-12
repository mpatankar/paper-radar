"""Smoke test: every blog adapter listed in config.yaml is importable and
exposes a fetch() callable. We don't hit the network here.
"""
from __future__ import annotations
import yaml
from pathlib import Path

from paper_radar.sources.blogs import ADAPTERS


def test_every_configured_adapter_is_registered():
    config = yaml.safe_load((Path(__file__).parent.parent.parent / "config" / "config.yaml").read_text())
    enabled = config["blogs"]["enabled_adapters"]
    missing = [name for name in enabled if name not in ADAPTERS]
    assert not missing, f"adapters listed in config but not registered: {missing}"


def test_every_adapter_is_callable():
    for name, fn in ADAPTERS.items():
        assert callable(fn), f"adapter {name} is not callable"
