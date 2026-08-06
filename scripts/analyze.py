#!/usr/bin/env python3
"""Recompute every number in the report from runs.jsonl.

    python3 scripts/analyze.py --config config.yaml --out out/20260806T120000Z-pilot

Writes summary.json and report.md next to the raw runs. Nothing is cached: the
report is a pure function of the raw data plus the config, so anyone can rerun it
on the published JSONL and get the same figures.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench import config as config_mod  # noqa: E402
from bench.analyze import analyze  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--out", required=True, help="run directory containing runs.jsonl")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg_path = Path(args.config).resolve()
    cfg = config_mod.resolve_paths(config_mod.load(cfg_path), cfg_path.parent)
    summary = analyze(cfg, args.out)

    head = summary["headline"]
    print(f"verdict: {head['verdict']} — {head['verdict_meaning']}")
    print(f"cost ratio control/experiment: {head['geometric_mean']:.3f} "
          f"(95% CI {head['ci'][0]:.3f}–{head['ci'][1]:.3f})")
    print(f"invalid runs: {summary['validity']['n_invalid']}/{summary['validity']['n_rows']}")
    print(f"report: {Path(args.out) / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
