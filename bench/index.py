"""Building the skill's index once, and pricing it on its own line.

A user does not rebuild a code graph before every task; they build it and keep
working while it slowly goes stale. The harness models exactly that: one build
in a reference checkout, its wall time and its cost recorded separately, then the
resulting files copied into each experimental worktree.

Skills without an index leave ``index.build_cmd`` empty and none of this runs.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .config import IndexConfig
from .util import run, tail, utc_iso


@dataclass
class IndexBuild:
    built: bool
    command: str | None
    exit_code: int | None
    wall_s: float
    timed_out: bool
    paths: list[str]
    bytes_total: int
    built_at: str
    output_tail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def build(cfg: IndexConfig, checkout: str | Path, env: dict[str, str] | None = None) -> IndexBuild:
    checkout = Path(checkout)
    if not cfg.build_cmd:
        return IndexBuild(False, None, None, 0.0, False, [], 0, utc_iso(), "")

    proc = run(["/bin/sh", "-lc", cfg.build_cmd], cwd=checkout, env=env,
               timeout=cfg.build_timeout_s)
    present = [p for p in cfg.paths if (checkout / p).exists()]
    total = sum(_size(checkout / p) for p in present)
    return IndexBuild(
        built=proc.returncode == 0 and not proc.timed_out,
        command=cfg.build_cmd,
        exit_code=proc.returncode,
        wall_s=round(proc.duration_s, 2),
        timed_out=proc.timed_out,
        paths=present,
        bytes_total=total,
        built_at=utc_iso(),
        output_tail=tail(proc.stdout + "\n" + proc.stderr, 4000),
    )


def install(source: str | Path, worktree: str | Path, paths: list[str]) -> list[str]:
    """Copy the built index into a worktree. Returns what was actually copied."""
    src = Path(source)
    dst = Path(worktree)
    copied: list[str] = []
    for rel in paths:
        s = src / rel
        d = dst / rel
        if not s.exists():
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
        copied.append(rel)
    return copied


def refresh(cfg: IndexConfig, worktree: str | Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Optional per-worktree incremental refresh, timed so it can be charged."""
    if not cfg.refresh_cmd:
        return {"ran": False}
    proc = run(["/bin/sh", "-lc", cfg.refresh_cmd], cwd=worktree, env=env,
               timeout=cfg.refresh_timeout_s)
    return {
        "ran": True,
        "exit_code": proc.returncode,
        "wall_s": round(proc.duration_s, 2),
        "timed_out": proc.timed_out,
    }
