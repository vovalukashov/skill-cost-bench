"""Building the worktree an arm actually works in.

The sweep and its positive control have to hand the arm the same tree. When they
do not, the control answers a question about an arm nobody measured — and it
answers it convincingly, because a session that was never given the skill really
cannot use the skill.

That is not hypothetical. The first stock-install sweep refused to start: both
experimental arms failed their probe with "no skill is described anywhere in my
instructions". They were right. The probe copied the index in and stopped there,
while the skill itself arrives from its own installer, which only the sweep ran.

Order is the other thing this file exists to keep. The repository's own agent
instructions come out first, then the index goes in, and the skill's installer
runs last — so what it writes is the only guidance in the tree, and its hooks
find a graph already there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from . import index as index_mod
from .util import run
from .worktree import hide_paths


def run_arm_setup(arm: Any, wt: Path) -> dict[str, Any]:
    """Run the skill's own installer inside this arm's worktree."""
    proc = run(["/bin/sh", "-lc", arm.setup_cmd], cwd=wt,
               env=arm.env or None, timeout=arm.setup_timeout_s)
    return {
        "cmd": arm.setup_cmd,
        "exit_code": proc.returncode,
        "wall_s": round(proc.duration_s, 2),
        "timed_out": proc.timed_out,
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def prepare_worktree(
    cfg: Any,
    arm: Any,
    wt: Path,
    *,
    test_files: Sequence[str] = (),
    index_source: Path | None = None,
) -> dict[str, Any]:
    """Hide the tests, strip the configs, set the project up, install the skill.

    Returns the fields to record on the run row. The probe passes no test files,
    because it grades nothing; everything else is identical, which is the point.
    """
    hidden = hide_paths(wt, list(test_files))
    stripped = hide_paths(wt, list(cfg.target.strip_paths))

    setup: dict[str, Any] = {"ran": False}
    if cfg.target.setup_cmd:
        proc = run(["/bin/sh", "-lc", cfg.target.setup_cmd], cwd=wt,
                   timeout=cfg.target.setup_timeout_s)
        setup = {
            "ran": True,
            "exit_code": proc.returncode,
            "wall_s": round(proc.duration_s, 2),
            "timed_out": proc.timed_out,
        }

    out: dict[str, Any] = {"prepare": {"hidden": hidden, "stripped": stripped,
                                       "setup": setup}}

    if arm.use_index and index_source is not None:
        out["index_installed"] = index_mod.install(index_source, wt, cfg.index.paths)
        out["index_refresh"] = index_mod.refresh(cfg.index, wt, arm.env)

    if arm.setup_cmd:
        out["arm_setup"] = run_arm_setup(arm, wt)

    return out
