"""Smoke tests for config loading."""
from paper_radar.config import load_config


def test_loads_three_files(config):
    assert config.arxiv.enabled
    assert config.arxiv.sets  # not empty
    assert config.feeds
    assert config.tier_1
    assert config.tier_2


def test_find_feed(config):
    assert config.find_feed("everything") is not None
    assert config.find_feed("does-not-exist") is None


def test_tier_1_present(config):
    names = {i.name for i in config.tier_1}
    # core frontier labs must be in tier 1
    for must_have in ["OpenAI", "Anthropic", "Google DeepMind", "Meta FAIR",
                      "Physical Intelligence", "Thinking Machines"]:
        assert must_have in names, f"{must_have} missing from tier_1"


def test_tier_2_present(config):
    names = {i.name for i in config.tier_2}
    for must_have in ["Stanford", "MIT", "UC Berkeley", "CMU"]:
        assert must_have in names


def test_institution_matching(config):
    google = next(i for i in config.tier_1 if i.name == "Google DeepMind")
    assert google.matches("Google DeepMind, London")
    assert google.matches("DeepMind")
    assert google.matches("Google Brain")
    assert not google.matches("Google Books")  # not a match — wrong substring

    anthropic = next(i for i in config.tier_1 if i.name == "Anthropic")
    assert anthropic.matches("Anthropic")
    assert not anthropic.matches("OpenAI")
