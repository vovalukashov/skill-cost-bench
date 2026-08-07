"""Reusing an index is only safe because it is keyed by the commit it was built at."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from bench.config import ArmConfig, Config, IndexConfig, RunConfig, TargetConfig, AgentConfig
from bench.runner import IndexCache

BUILD = "mkdir -p graphify-out && git rev-parse HEAD > graphify-out/graph.json"


def _cfg(repo: Path, tmp_path: Path, reuse_from=None) -> Config:
    return Config(
        run=RunConfig(name="idx", seed=1, repeats=1, budget_usd=1.0,
                      out_dir=str(tmp_path / "out"), tasks_file="unused"),
        target=TargetConfig(repo=str(repo), test_cmd="true", worktree_root=str(tmp_path / "wt")),
        agent=AgentConfig(bin="true"),
        arms=[ArmConfig(name="b", label="B", use_index=True,
                        activation_patterns=["x"])],
        index=IndexConfig(build_cmd=BUILD, paths=["graphify-out/graph.json"],
                          reuse_from=str(reuse_from) if reuse_from else None),
        claim={"factor": 1.0},
    )


def _commits(repo: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "rev-list", "-n", "2", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.split()


def test_an_index_is_built_once_and_kept(demo_repo: Path, tmp_path: Path):
    cache = IndexCache(_cfg(demo_repo, tmp_path), tmp_path / "run1")
    head = _commits(demo_repo)[0]

    first = cache.for_commit(head)
    assert first is not None and (first / "graphify-out" / "graph.json").exists()
    assert (first / "graphify-out" / "graph.json").read_text().strip() == head


def test_a_second_process_does_not_rebuild_what_is_on_disk(demo_repo: Path, tmp_path: Path):
    """A sweep that dies halfway used to burn a quarter-hour of CPU on restart."""
    head = _commits(demo_repo)[0]
    IndexCache(_cfg(demo_repo, tmp_path), tmp_path / "run1").for_commit(head)

    fresh = IndexCache(_cfg(demo_repo, tmp_path), tmp_path / "run1")
    assert head in fresh.builds, "the ledger on disk has to be read back"
    marker = tmp_path / "run1" / "indexes" / head[:12] / "graphify-out" / "untouched"
    marker.write_text("still here", encoding="utf-8")

    again = IndexCache(_cfg(demo_repo, tmp_path), tmp_path / "run1")
    again.for_commit(head)
    assert marker.exists(), "a rebuild would have wiped the directory"


def test_a_later_run_adopts_an_index_for_the_same_commit(demo_repo: Path, tmp_path: Path):
    head = _commits(demo_repo)[0]
    IndexCache(_cfg(demo_repo, tmp_path), tmp_path / "run1").for_commit(head)

    second = IndexCache(_cfg(demo_repo, tmp_path, reuse_from=tmp_path / "run1"),
                        tmp_path / "run2")
    dest = second.for_commit(head)

    assert dest is not None and dest.parent.parent.name == "run2"
    assert (dest / "graphify-out" / "graph.json").read_text().strip() == head
    ledger = json.loads((tmp_path / "run2" / "indexes" / "builds.json").read_text())
    assert "reused_from" in ledger[head], "an adopted index must say where it came from"


def test_a_different_commit_is_never_adopted(demo_repo: Path, tmp_path: Path):
    """The whole safety of reuse rests on this."""
    head, parent = _commits(demo_repo)
    IndexCache(_cfg(demo_repo, tmp_path), tmp_path / "run1").for_commit(head)

    second = IndexCache(_cfg(demo_repo, tmp_path, reuse_from=tmp_path / "run1"),
                        tmp_path / "run2")
    dest = second.for_commit(parent)

    assert (dest / "graphify-out" / "graph.json").read_text().strip() == parent
    ledger = json.loads((tmp_path / "run2" / "indexes" / "builds.json").read_text())
    assert "reused_from" not in ledger[parent], "a different commit must be built fresh"


def test_a_ledger_entry_whose_files_are_gone_is_rebuilt(demo_repo: Path, tmp_path: Path):
    head = _commits(demo_repo)[0]
    cache = IndexCache(_cfg(demo_repo, tmp_path), tmp_path / "run1")
    dest = cache.for_commit(head)
    (dest / "graphify-out" / "graph.json").unlink()

    fresh = IndexCache(_cfg(demo_repo, tmp_path), tmp_path / "run1")
    rebuilt = fresh.for_commit(head)
    assert (rebuilt / "graphify-out" / "graph.json").exists()
