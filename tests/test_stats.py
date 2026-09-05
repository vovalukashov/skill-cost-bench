from __future__ import annotations

import math
import random

from bench.stats import (
    bootstrap_ci,
    effect_below_noise,
    estimate,
    geometric_mean,
    noise_floor,
    sign_test,
    verdict,
    wilcoxon_signed_rank,
)


def test_geometric_mean_is_multiplicative():
    assert geometric_mean([2.0, 8.0]) == 4.0
    assert math.isclose(geometric_mean([1.0, 1.0, 1.0]), 1.0)


def test_bootstrap_recovers_a_planted_effect():
    rng = random.Random(7)
    true_ratio = 1.35
    ratios = [true_ratio * math.exp(rng.gauss(0, 0.3)) for _ in range(40)]

    lo, hi = bootstrap_ci(ratios, n_resamples=4000, seed=11)
    assert lo < true_ratio < hi
    assert lo > 1.0, "a real 35% effect over 40 tasks should exclude parity"


def test_bootstrap_interval_covers_parity_when_there_is_no_effect():
    rng = random.Random(3)
    ratios = [math.exp(rng.gauss(0, 0.3)) for _ in range(40)]
    lo, hi = bootstrap_ci(ratios, n_resamples=4000, seed=11)
    assert lo <= 1.0 <= hi


def test_sign_test_matches_a_hand_computed_case():
    # 9 of 10 tasks move the same way: two-sided exact p = 2 * 11/1024
    ratios = [1.5] * 9 + [0.9]
    assert math.isclose(sign_test(ratios), 2 * (11 / 1024), rel_tol=1e-9)


def test_sign_test_is_one_when_the_split_is_even():
    assert sign_test([1.5, 1.5, 0.5, 0.5]) == 1.0


def test_wilcoxon_agrees_with_a_known_exact_value():
    # Classic worked example: all six differences positive, W+ = 21, p = 2/64.
    ratios = [math.exp(d) for d in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)]
    assert math.isclose(wilcoxon_signed_rank(ratios), 2 * (1 / 64), rel_tol=1e-9)


def test_verdict_buckets_are_mutually_exclusive():
    # An interval covering parity is inconclusive even if it also covers the claim.
    assert verdict(0.5, 90.0, 70.0) == "null"
    assert verdict(0.9, 1.1, 70.0) == "null"
    assert verdict(0.5, 0.9, 70.0) == "worse"
    assert verdict(1.2, 1.9, 70.0) == "smaller_but_real"
    assert verdict(60.0, 80.0, 70.0) == "as_promised"
    assert verdict(90.0, 120.0, 70.0) == "above_claim"


def test_verdict_is_null_when_the_interval_is_undefined():
    assert verdict(float("nan"), float("nan"), 70.0) == "null"


def test_estimate_reports_every_field():
    est = estimate([1.2, 1.4, 1.1, 1.35, 1.25, 0.95, 1.5, 1.3], n_resamples=2000)
    assert est.n == 8
    assert est.ci_low < est.geometric_mean < est.ci_high
    assert 0.0 <= est.p_sign <= 1.0
    assert 0.0 <= est.p_wilcoxon <= 1.0
    assert est.geometric_sd > 1.0


def test_noise_floor_measures_repeats_within_a_cell():
    cells = {
        ("t001", "control"): [0.10, 0.20],
        ("t001", "graphify"): [0.08, 0.09],
        ("t002", "control"): [0.30],  # single repeat carries no information
    }
    noise = noise_floor(cells)
    assert noise["n_cells"] == 2
    assert noise["median_spread_ratio"] > 1.0


def test_effect_below_noise_compares_on_the_log_scale():
    """A ratio and its reciprocal are the same distance from parity.

    Comparing `abs(gm - 1)` against `abs(gsd - 1)` mixes an additive distance
    with a multiplicative spread, and it reads 0.843 as smaller than a spread
    that it is in fact larger than. Both sides belong in logs.
    """
    # The measured run: geometric mean 0.843, within-cell geometric SD 1.164.
    # |ln 0.843| = 0.171 against ln 1.164 = 0.152 — the effect is larger.
    assert effect_below_noise(0.843, 1.164) is False
    # Same numbers on the linear scale would have said the opposite:
    assert abs(0.843 - 1.0) < abs(1.164 - 1.0)

    # A genuinely tiny effect still trips the guard.
    assert effect_below_noise(1.01, 1.30) is True

    # Direction cannot change the answer: a ratio and its reciprocal are equally
    # far from parity, which the linear form got wrong.
    assert effect_below_noise(1.2, 1.164) == effect_below_noise(1 / 1.2, 1.164)


def test_effect_below_noise_is_unknown_without_a_measured_spread():
    assert effect_below_noise(0.843, None) is None
    assert effect_below_noise(None, 1.164) is None
    assert effect_below_noise(0.843, float("nan")) is None
