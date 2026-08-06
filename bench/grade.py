"""Grading: restore the hidden tests, run them, report pass/fail.

Grading never looks at the diff the agent produced. The only question is whether
the commit's own tests pass on the agent's tree.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Sequence

from .util import Proc, run, tail
from .worktree import restore_paths


@dataclass
class GradeResult:
    passed: bool
    exit_code: int
    timed_out: bool
    duration_s: float
    restored: list[str]
    command: str
    output_tail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_command(template: str, test_files: Sequence[str]) -> list[str]:
    """Render a test command.

    ``{tests}`` is replaced by the shell-quoted test paths. A template without
    ``{tests}`` runs the whole suite, which is slower but sometimes the only
    thing a project supports.
    """
    quoted = " ".join(shlex.quote(t) for t in test_files)
    rendered = template.replace("{tests}", quoted) if "{tests}" in template else template
    return ["/bin/sh", "-lc", rendered]


def run_tests(
    worktree_path: str | Path,
    template: str,
    test_files: Sequence[str],
    timeout: float,
    env: dict[str, str] | None = None,
) -> Proc:
    return run(
        build_command(template, test_files),
        cwd=worktree_path,
        env=env,
        timeout=timeout,
    )


def grade(
    repo: str | Path,
    worktree_path: str | Path,
    commit: str,
    test_files: Sequence[str],
    template: str,
    timeout: float = 900.0,
    env: dict[str, str] | None = None,
) -> GradeResult:
    restored = restore_paths(repo, worktree_path, commit, list(test_files))
    proc = run_tests(worktree_path, template, restored or list(test_files), timeout, env)
    return GradeResult(
        passed=proc.returncode == 0 and not proc.timed_out,
        exit_code=proc.returncode,
        timed_out=proc.timed_out,
        duration_s=round(proc.duration_s, 2),
        restored=restored,
        command=template,
        output_tail=tail(proc.stdout + "\n" + proc.stderr, 4000),
    )
