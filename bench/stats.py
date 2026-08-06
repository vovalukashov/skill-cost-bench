"""Multiplicative statistics, because the claim is multiplicative.

"70x cheaper" is a statement about a ratio, so the summary is the geometric mean
of per-task ratios control/experiment (a ratio above 1.0 means the experimental
arm is cheaper), with a paired bootstrap interval over tasks. The median, an
exact sign test and Wilcoxon on log ratios sit next to it so that one freakishly
cheap task cannot carry a headline.

Pure standard library on purpose: 10k bootstrap resamples over a few dozen tasks
costs less than importing numpy, and the harness stays installable with one
dependency.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, asdict
from typing import Any, Sequence

# The four pre-registered verdicts. Written down before any data exists, because
# after a run there is always a phrasing that makes the number look convincing.
VERDICTS = {
    "as_promised": "interval covers the advertised factor",
    "smaller_but_real": "interval excludes 1.0, lies entirely below the advertised factor",
    "null": "interval covers 1.0 — parity cannot be excluded",
    "worse": "interval lies entirely below 1.0 — the skill costs more",
    "above_claim": "interval lies entirely above the advertised factor",
}


@dataclass
class Estimate:
    n: int
    geometric_mean: float
    ci_low: float
    ci_high: float
    median: float
    p_sign: float
    p_wilcoxon: float
    geometric_sd: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def geometric_mean(values: Sequence[float]) -> float:
    clean = [v for v in values if v is not None and v > 0]
    if not clean:
        return float("nan")
    return math.exp(sum(math.log(v) for v in clean) / len(clean))


def geometric_sd(values: Sequence[float]) -> float:
    """exp(sd(log x)) — the natural spread measure for ratios."""
    logs = [math.log(v) for v in values if v is not None and v > 0]
    if len(logs) < 2:
        return float("nan")
    return math.exp(statistics.stdev(logs))


def bootstrap_ci(
    values: Sequence[float],
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int = 20260806,
) -> tuple[float, float]:
    """Percentile bootstrap interval for the geometric mean.

    Resampling is over tasks, not over runs: repeats of the same task are not
    independent observations, and treating them as such would shrink the
    interval by pretending the sample is bigger than it is.
    """
    clean = [v for v in values if v is not None and v > 0]
    if len(clean) < 2:
        return (float("nan"), float("nan"))
    logs = [math.log(v) for v in clean]
    rng = random.Random(seed)
    n = len(logs)
    means: list[float] = []
    for _ in range(n_resamples):
        total = 0.0
        for _ in range(n):
            total += logs[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    lo_idx = int(math.floor((alpha / 2) * n_resamples))
    hi_idx = min(n_resamples - 1, int(math.ceil((1 - alpha / 2) * n_resamples)) - 1)
    return (math.exp(means[lo_idx]), math.exp(means[hi_idx]))


def _binom_cdf(k: int, n: int, p: float = 0.5) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(0, k + 1))


def sign_test(values: Sequence[float], null: float = 1.0) -> float:
    """Exact two-sided sign test: how many tasks moved which way."""
    pos = sum(1 for v in values if v is not None and v > null)
    neg = sum(1 for v in values if v is not None and v < null)
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    return min(1.0, 2 * _binom_cdf(k, n))


def _wilcoxon_exact_p(w: float, n: int) -> float:
    """Exact two-sided p for the signed-rank statistic via the rank-sum DP."""
    total = 1 << n
    counts = [0] * (n * (n + 1) // 2 + 1)
    counts[0] = 1
    for rank in range(1, n + 1):
        for s in range(len(counts) - 1, rank - 1, -1):
            counts[s] += counts[s - rank]
    cumulative = 0
    target = min(w, n * (n + 1) / 2 - w)
    for s, c in enumerate(counts):
        if s <= target:
            cumulative += c
    return min(1.0, 2 * cumulative / total)


def wilcoxon_signed_rank(values: Sequence[float], null: float = 1.0) -> float:
    """Two-sided Wilcoxon signed-rank on log ratios (null: median ratio == 1)."""
    diffs = [math.log(v) - math.log(null) for v in values if v is not None and v > 0]
    diffs = [d for d in diffs if d != 0.0]
    n = len(diffs)
    if n == 0:
        return 1.0
    if n < 6:
        # Too few pairs for either approximation to mean anything.
        return 1.0

    order = sorted(range(n), key=lambda i: abs(diffs[i]))
    ranks = [0.0] * n
    i = 0
    tie_groups: list[int] = []
    while i < n:
        j = i
        while j + 1 < n and abs(diffs[order[j + 1]]) == abs(diffs[order[i]]):
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        tie_groups.append(j - i + 1)
        i = j + 1

    w_plus = sum(r for r, d in zip(ranks, diffs) if d > 0)

    if n <= 20 and all(g == 1 for g in tie_groups):
        return _wilcoxon_exact_p(w_plus, n)

    mean = n * (n + 1) / 4
    var = n * (n + 1) * (2 * n + 1) / 24
    var -= sum(g**3 - g for g in tie_groups) / 48
    if var <= 0:
        return 1.0
    z = (abs(w_plus - mean) - 0.5) / math.sqrt(var)
    return min(1.0, 2 * (1 - _std_normal_cdf(z)))


def _std_normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def estimate(
    ratios: Sequence[float],
    n_resamples: int = 10_000,
    seed: int = 20260806,
    alpha: float = 0.05,
) -> Estimate:
    clean = [r for r in ratios if r is not None and r > 0]
    lo, hi = bootstrap_ci(clean, n_resamples=n_resamples, alpha=alpha, seed=seed)
    return Estimate(
        n=len(clean),
        geometric_mean=geometric_mean(clean),
        ci_low=lo,
        ci_high=hi,
        median=statistics.median(clean) if clean else float("nan"),
        p_sign=sign_test(clean),
        p_wilcoxon=wilcoxon_signed_rank(clean),
        geometric_sd=geometric_sd(clean),
    )


def verdict(ci_low: float, ci_high: float, claim: float) -> str:
    """Map an interval onto the pre-registered buckets. Order is part of the rule.

    Parity is checked first: an interval wide enough to cover both 1.0 and the
    advertised factor is inconclusive, not a confirmation.
    """
    if any(math.isnan(x) for x in (ci_low, ci_high)):
        return "null"
    if ci_low <= 1.0 <= ci_high:
        return "null"
    if ci_high < 1.0:
        return "worse"
    if ci_low <= claim <= ci_high:
        return "as_promised"
    if ci_high < claim:
        return "smaller_but_real"
    return "above_claim"


def noise_floor(values_by_task_arm: dict[tuple[str, str], list[float]]) -> dict[str, Any]:
    """How much does the same task cost twice in a row, with nothing changed?

    The pilot exists to print this number. If the measured effect is smaller than
    the repeat-to-repeat spread, the report has to say so out loud, above any
    claim about money.
    """
    within: list[float] = []
    per_cell: list[dict[str, Any]] = []
    for (task, arm), values in sorted(values_by_task_arm.items()):
        clean = [v for v in values if v is not None and v > 0]
        if len(clean) < 2:
            continue
        gsd = geometric_sd(clean)
        within.append(gsd)
        per_cell.append(
            {
                "task": task,
                "arm": arm,
                "n": len(clean),
                "min": min(clean),
                "max": max(clean),
                "spread_ratio": max(clean) / min(clean),
                "geometric_sd": gsd,
            }
        )
    return {
        "cells": per_cell,
        "median_geometric_sd": statistics.median(within) if within else float("nan"),
        "median_spread_ratio": (
            statistics.median([c["spread_ratio"] for c in per_cell]) if per_cell else float("nan")
        ),
        "n_cells": len(per_cell),
    }
