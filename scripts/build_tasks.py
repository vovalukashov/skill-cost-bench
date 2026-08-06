#!/usr/bin/env python3
"""Mine agent tasks out of a repository's own git history.

    python3 scripts/build_tasks.py \\
        --repo ~/code/myproject \\
        --test-glob 'tests/**' --test-cmd 'pytest -q' \\
        --since 2025-01-01 --max-tasks 80 \\
        --out tasks/tasks.yaml

Writes a manifest in which every task is ``review: pending``. Read it before
running anything: some commit messages contain the answer, and no filter can see
that for you.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench import tasks as tasks_mod  # noqa: E402
from bench.mine import MineConfig, mine  # noqa: E402
from bench.util import run, utc_iso  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", required=True, help="path to the repository to mine")
    p.add_argument("--test-glob", action="append", default=[], required=True,
                   help="glob matching test files (repeatable)")
    p.add_argument("--code-glob", action="append", default=[],
                   help="glob matching production code (repeatable, default: everything else)")
    p.add_argument("--test-cmd", default="pytest -q {tests}",
                   help="command that runs the restored tests; {tests} is substituted")
    p.add_argument("--since", default=None, help="git --since date")
    p.add_argument("--until", default=None, help="git --until date")
    p.add_argument("--max-tasks", type=int, default=80)
    p.add_argument("--max-files", type=int, default=25,
                   help="commits touching more files are several tasks in one coat")
    p.add_argument("--min-files", type=int, default=2)
    p.add_argument("--path", action="append", default=[], help="limit mining to these paths")
    p.add_argument("--out", required=True, help="where to write the manifest")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo = str(Path(args.repo).expanduser().resolve())

    cfg = MineConfig(
        repo=repo,
        test_globs=args.test_glob,
        code_globs=args.code_glob or ["*"],
        since=args.since,
        until=args.until,
        max_tasks=args.max_tasks,
        max_files=args.max_files,
        min_files=args.min_files,
        paths=args.path,
    )
    found, rejected = mine(cfg)

    head = run(["git", "-C", repo, "rev-parse", "HEAD"], timeout=60).stdout.strip()
    meta = {
        "repo": repo,
        "repo_head": head,
        "generated_at": utc_iso(),
        "test_cmd": args.test_cmd,
        "filters": {
            "test_globs": list(args.test_glob),
            "code_globs": args.code_glob or ["*"],
            "since": args.since,
            "until": args.until,
            "max_files": args.max_files,
            "min_files": args.min_files,
            "paths": list(args.path),
        },
        "rejected": rejected,
    }
    tasks_mod.save(args.out, meta, found)

    flagged = sum(1 for t in found if t.leak_risk)
    print(f"mined {len(found)} candidate tasks -> {args.out}")
    print(f"  {flagged} flagged leak_risk (commit message may contain the answer)")
    print("  rejected commits by reason:")
    for reason, count in sorted(rejected.items(), key=lambda kv: -kv[1]):
        print(f"    {count:5d}  {reason}")
    print()
    print("Every task is review: pending. Read them, set review: ok on the good ones,")
    print("then run scripts/verify_tasks.py before spending anything on an agent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
