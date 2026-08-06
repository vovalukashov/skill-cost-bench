#!/usr/bin/env python3
"""Run the sweep. Resumable, budget-capped, safe to interrupt.

    python3 scripts/run_bench.py --config config.yaml
    python3 scripts/run_bench.py --config config.yaml --dry-run
    python3 scripts/run_bench.py --config config.yaml --out out/20260806T120000Z
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench import config as config_mod  # noqa: E402
from bench import tasks as tasks_mod  # noqa: E402
from bench.runner import execute  # noqa: E402
from bench.util import utc_stamp, write_json  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--out", default=None, help="run directory (default: out/<UTC stamp>-<name>)")
    p.add_argument("--dry-run", action="store_true", help="write the plan, spend nothing")
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--max-tasks", type=int, default=None, help="override run.max_tasks")
    p.add_argument("--require-verified", action="store_true", default=True)
    p.add_argument("--allow-unverified", dest="require_verified", action="store_false")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg_path = Path(args.config).resolve()
    cfg = config_mod.resolve_paths(config_mod.load(cfg_path), cfg_path.parent)

    meta, rows = tasks_mod.load(cfg.run.tasks_file)
    approved = tasks_mod.approved(rows)
    if args.require_verified:
        approved = [t for t in approved if t.get("verified") == "ok"]

    limit = args.max_tasks or cfg.run.max_tasks
    if limit:
        approved = approved[:limit]

    if not approved:
        review_counts = tasks_mod.counts(rows)
        print("no runnable tasks.", file=sys.stderr)
        print(f"  manifest: {cfg.run.tasks_file}", file=sys.stderr)
        print(f"  review states: {review_counts}", file=sys.stderr)
        print("  mark good tasks review: ok, then run scripts/verify_tasks.py", file=sys.stderr)
        return 2

    out = Path(args.out) if args.out else Path(cfg.run.out_dir) / f"{utc_stamp()}-{cfg.run.name}"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "config_resolved.json", cfg.to_dict())
    write_json(out / "tasks_used.json", [t["id"] for t in approved])

    planned = len(approved) * len(cfg.arms) * cfg.run.repeats
    print(f"tasks: {len(approved)}  arms: {len(cfg.arms)}  repeats: {cfg.run.repeats}")
    print(f"planned runs: {planned}   budget: ${cfg.run.budget_usd:.2f}")
    print(f"out: {out}")

    state = execute(cfg, approved, out, resume=not args.no_resume, dry_run=args.dry_run)
    print()
    for key, value in state.items():
        print(f"  {key}: {value}")
    if state.get("stopped_on_budget"):
        print(f"\nBUDGET REACHED. {state['skipped_budget']} runs were left undone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
