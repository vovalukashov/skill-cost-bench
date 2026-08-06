#!/usr/bin/env python3
"""Check that each task is both solvable and not already solved.

Two questions per task, both answered without an agent and without spending
anything on the API:

1. At the commit itself, do the commit's own tests pass? If not, the grader is
   broken in this environment and no agent could ever satisfy it.
2. At the parent commit with those tests restored, do they fail? If they pass,
   the task is already done at the starting state and would score a free win for
   both arms.

Only tasks that answer yes and yes are worth paying for. The rest are marked and
left in the manifest with the reason, not silently dropped.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench import tasks as tasks_mod  # noqa: E402
from bench.grade import run_tests  # noqa: E402
from bench.util import utc_iso  # noqa: E402
from bench.worktree import prune, restore_paths, worktree  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tasks", required=True)
    p.add_argument("--worktree-root", default="/tmp/skill-cost-bench-verify")
    p.add_argument("--setup-cmd", default=None, help="run once per worktree before the tests")
    p.add_argument("--timeout", type=float, default=900.0)
    p.add_argument("--setup-timeout", type=float, default=1800.0)
    p.add_argument("--only-approved", action="store_true",
                   help="verify only tasks already marked review: ok")
    p.add_argument("--limit", type=int, default=None)
    return p.parse_args(argv)


def verify_one(repo: str, task: dict, test_cmd: str, root: Path, setup_cmd: str | None,
               timeout: float, setup_timeout: float) -> str:
    from bench.util import run as sh

    tests = list(task.get("test_files", []))
    if not tests:
        return "no_tests"

    # 1. tests pass at the commit
    with worktree(repo, task["commit"], root / f"{task['id']}-commit") as wt:
        if setup_cmd:
            sh(["/bin/sh", "-lc", setup_cmd], cwd=wt, timeout=setup_timeout)
        after = run_tests(wt, test_cmd, tests, timeout)
    if after.returncode != 0:
        return "fails_at_commit"

    # 2. the same tests fail at the parent
    with worktree(repo, task["parent"], root / f"{task['id']}-parent") as wt:
        if setup_cmd:
            sh(["/bin/sh", "-lc", setup_cmd], cwd=wt, timeout=setup_timeout)
        restored = restore_paths(repo, wt, task["commit"], tests)
        before = run_tests(wt, test_cmd, restored or tests, timeout)
    if before.returncode == 0:
        return "passes_at_parent"
    return "ok"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    meta, rows = tasks_mod.load(args.tasks)
    repo = meta["repo"]
    test_cmd = meta.get("test_cmd", "pytest -q {tests}")
    root = Path(args.worktree_root)

    selected = [t for t in rows if not args.only_approved or t.get("review") == "ok"]
    if args.limit:
        selected = selected[: args.limit]

    prune(repo)
    tally: dict[str, int] = {}
    for i, task in enumerate(selected, 1):
        try:
            state = verify_one(repo, task, test_cmd, root, args.setup_cmd,
                               args.timeout, args.setup_timeout)
        except Exception as exc:  # noqa: BLE001
            state = f"error: {type(exc).__name__}"
        task["verified"] = state
        tally[state] = tally.get(state, 0) + 1
        print(f"[{i}/{len(selected)}] {task['id']} {task['commit'][:8]} -> {state}", flush=True)

    meta["verified_at"] = utc_iso()
    meta["verify_tally"] = tally
    tasks_mod.save(args.tasks, meta, rows)
    print()
    for state, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {count:4d}  {state}")
    print(f"\nmanifest updated: {args.tasks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
