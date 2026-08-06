"""Throwaway git worktrees.

Every run gets its own checkout of the parent commit. The source repository is
only ever read: worktrees are detached, created under a scratch root outside the
repo, and removed afterwards. Nothing is committed, nothing is pushed.
"""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .util import run


class WorktreeError(RuntimeError):
    pass


def _git(repo: str | Path, *args: str, timeout: float = 300.0):
    proc = run(["git", "-C", str(repo), *args], timeout=timeout)
    if proc.returncode != 0:
        raise WorktreeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:400]}")
    return proc


def prune(repo: str | Path) -> None:
    run(["git", "-C", str(repo), "worktree", "prune"], timeout=120.0)


@contextmanager
def worktree(repo: str | Path, commit: str, path: str | Path) -> Iterator[Path]:
    """Check ``commit`` out at ``path`` and remove the worktree on the way out."""
    path = Path(path)
    # A hard kill leaves the path registered in the repo's worktree list even
    # after the directory is gone, and `worktree add` then refuses the same path
    # forever. Clear both the registration and the directory before adding.
    run(["git", "-C", str(repo), "worktree", "remove", "--force", str(path)], timeout=120.0)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    prune(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "--detach", "--force", str(path), commit)
    try:
        yield path
    finally:
        run(["git", "-C", str(repo), "worktree", "remove", "--force", str(path)], timeout=300.0)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        prune(repo)


def restore_paths(repo: str | Path, worktree_path: str | Path, commit: str,
                  paths: list[str]) -> list[str]:
    """Copy files as of ``commit`` into the worktree, overwriting what is there.

    Used at grading time to bring back the hidden tests. Files that did not exist
    at ``commit`` (deleted tests) are removed from the worktree instead.
    """
    restored: list[str] = []
    wt = Path(worktree_path)
    for rel in paths:
        proc = run(["git", "-C", str(repo), "show", f"{commit}:{rel}"], timeout=120.0)
        target = wt / rel
        if proc.returncode != 0:
            if target.exists():
                target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(proc.stdout, encoding="utf-8")
        restored.append(rel)
    return restored


def hide_paths(worktree_path: str | Path, paths: list[str]) -> list[str]:
    """Delete files from the worktree (both arms, identically)."""
    removed: list[str] = []
    wt = Path(worktree_path)
    for rel in paths:
        target = wt / rel
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed.append(rel)
        elif target.exists():
            target.unlink()
            removed.append(rel)
    return removed
