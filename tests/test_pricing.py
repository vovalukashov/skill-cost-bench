from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from bench.pricing import ModelPrice, load_table, price_run, price_usage, split_cache_writes

SONNET = ModelPrice(input=3.0, output=15.0, cache_write_5m=3.75,
                    cache_write_1h=6.0, cache_read=0.30)


def test_a_plain_request_is_priced_by_hand_arithmetic():
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    # 1M in at $3 + 0.1M out at $15 = 3.00 + 1.50
    assert math.isclose(price_usage(usage, SONNET), 4.5, rel_tol=1e-9)


def test_cache_reads_are_a_tenth_of_input():
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 1_000_000}
    assert math.isclose(price_usage(usage, SONNET), 0.30, rel_tol=1e-9)


def test_the_two_cache_ttls_are_priced_apart():
    usage = {"cache_creation": {"ephemeral_5m_input_tokens": 1_000_000,
                                "ephemeral_1h_input_tokens": 1_000_000}}
    assert split_cache_writes(usage) == (1_000_000, 1_000_000)
    assert math.isclose(price_usage(usage, SONNET), 3.75 + 6.0, rel_tol=1e-9)


def test_a_total_without_a_breakdown_falls_back_to_the_cheaper_ttl():
    """Undercounting is the safer way to be wrong about the cache-heavy arm."""
    usage = {"cache_creation_input_tokens": 1_000_000}
    assert split_cache_writes(usage) == (1_000_000, 0)
    assert math.isclose(price_usage(usage, SONNET), 3.75, rel_tol=1e-9)


def test_an_empty_breakdown_does_not_hide_the_total():
    usage = {"cache_creation": {"ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 0},
             "cache_creation_input_tokens": 400_000}
    assert split_cache_writes(usage) == (400_000, 0)


def test_multipliers_fill_in_rates_that_are_not_spelled_out():
    price = ModelPrice.from_dict({"input": 3.0, "output": 15.0})
    assert price.cache_write_5m == 3.75
    assert price.cache_write_1h == 6.0
    assert math.isclose(price.cache_read, 0.30, rel_tol=1e-9)


def test_an_unpriced_model_returns_none_rather_than_a_free_run():
    table = {"claude-sonnet-5": SONNET}
    assert price_run({"input_tokens": 1000}, "some-other-model", table) is None
    assert price_run({"input_tokens": 1000}, None, table) is None
    assert price_run({"input_tokens": 1_000_000}, "claude-sonnet-5", table) == 3.0


def test_table_loading_ignores_the_metadata_keys():
    table = load_table({"source": "https://…", "dated": "2026-08-06", "note": "…",
                        "claude-sonnet-5": {"input": 3.0, "output": 15.0}})
    assert list(table) == ["claude-sonnet-5"]


def test_missing_usage_is_zero_not_a_crash():
    assert price_usage(None, SONNET) == 0.0
    assert price_usage({}, SONNET) == 0.0


def test_the_shipped_configs_price_the_model_they_run():
    """A config whose model has no price would report no cost at all."""
    for name in ("config.example.yaml", "config-superset.yaml", "config-night.yaml"):
        raw = yaml.safe_load(Path(name).read_text(encoding="utf-8"))
        model = raw["agent"]["model"]
        assert model in load_table(raw["pricing"]), f"{name}: {model} is unpriced"


def test_an_unpriced_model_is_refused_at_config_load(tmp_path: Path):
    from bench import config as config_mod

    data = {
        "run": {"name": "x", "budget_usd": 1.0},
        "target": {"repo": "/tmp/repo"},
        "agent": {"bin": "claude", "model": "claude-not-a-real-model"},
        "index": {},
        "pricing": {"claude-sonnet-5": {"input": 3.0, "output": 15.0}},
        "arms": [{"name": "control"}, {"name": "s", "activation_patterns": ["x"]}],
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(config_mod.ConfigError, match="pricing table"):
        config_mod.load(path)
