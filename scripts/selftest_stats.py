#!/usr/bin/env python3
"""Plant an effect in fake data and check the analysis finds it.

Statistics code that has never been pointed at a known answer is a guess with
decimal places. This script generates paired runs with a chosen true ratio and
a chosen amount of noise, feeds them through the real analysis, and prints what
came back.

    python3 scripts/selftest_stats.py --true-ratio 1.35 --tasks 40 --repeats 3
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.stats import estimate, verdict  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--true-ratio", type=float, default=1.35)
    p.add_argument("--tasks", type=int, default=40)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--task-sigma", type=float, default=0.55,
                   help="log-scale spread between tasks (tasks differ a lot)")
    p.add_argument("--rep-sigma", type=float, default=0.25,
                   help="log-scale spread between repeats of the same cell")
    p.add_argument("--claim", type=float, default=70.0)
    p.add_argument("--seed", type=int, default=20260806)
    p.add_argument("--trials", type=int, default=1)
    return p.parse_args(argv)


def one_trial(args: argparse.Namespace, seed: int) -> dict[str, float]:
    rng = random.Random(seed)
    ratios: list[float] = []
    for _ in range(args.tasks):
        base = math.exp(rng.gauss(0, args.task_sigma))  # this task's difficulty
        control = [base * math.exp(rng.gauss(0, args.rep_sigma)) for _ in range(args.repeats)]
        experiment = [
            (base / args.true_ratio) * math.exp(rng.gauss(0, args.rep_sigma))
            for _ in range(args.repeats)
        ]
        control.sort()
        experiment.sort()
        mid = args.repeats // 2
        ratios.append(control[mid] / experiment[mid])
    est = estimate(ratios, seed=seed)
    return {
        "gm": est.geometric_mean,
        "lo": est.ci_low,
        "hi": est.ci_high,
        "covered": float(est.ci_low <= args.true_ratio <= est.ci_high),
        "verdict": verdict(est.ci_low, est.ci_high, args.claim),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    covered = 0
    for i in range(args.trials):
        res = one_trial(args, args.seed + i)
        covered += int(res["covered"])
        if args.trials <= 5 or i < 3:
            print(
                f"trial {i + 1}: recovered {res['gm']:.3f} "
                f"(95% CI {res['lo']:.3f}–{res['hi']:.3f}), true {args.true_ratio:.3f}, "
                f"verdict {res['verdict']}"
            )
    if args.trials > 1:
        print(f"\ncoverage of the true ratio by the 95% CI: "
              f"{covered}/{args.trials} = {covered / args.trials:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
