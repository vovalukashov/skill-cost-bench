"""The whole pipeline on a toy repository with a fake agent.

Mine, approve, verify, run both arms, grade, analyse. Nothing here talks to an
API, which is the point: the harness has to be known-good before it is allowed
to spend anything.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from bench.analyze import analyze
from bench.config import AgentConfig, ArmConfig, Config, IndexConfig, RunConfig, TargetConfig
from bench.mine import MineConfig, mine
from bench.runner import execute, plan, run_key
from bench.util import read_jsonl
from scripts.verify_tasks import verify_one

TEST_CMD = "python3 {tests}"


def _fake_agent(path: Path) -> str:
    src = Path(__file__).resolve().parent / "fake_agent.py"
    dst = path / "fake_agent.py"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(dst)


def _solution(repo: Path, commit: str) -> str:
    return json.dumps(
        {
            "app/calc.py": subprocess.run(
                ["git", "-C", str(repo), "show", f"{commit}:app/calc.py"],
                capture_output=True, text=True, check=True,
            ).stdout
        }
    )


def _config(repo: Path, tmp_path: Path, tasks_file: Path, *, control_cost="0.20",
            experiment_cost="0.10", activate="1", repeats=2, budget=100.0,
            solve_experiment="1") -> Config:
    solution = _solution(repo, _mined(repo)[0]["commit"])
    agent_bin = _fake_agent(tmp_path)
    common = {"FAKE_AGENT_WRITE": solution, "FAKE_AGENT_JITTER": "0.05"}

    return Config(
        run=RunConfig(
            name="e2e",
            seed=1,
            repeats=repeats,
            budget_usd=budget,
            out_dir=str(tmp_path / "out"),
            tasks_file=str(tasks_file),
            bootstrap_resamples=500,
        ),
        target=TargetConfig(
            repo=str(repo),
            test_cmd=TEST_CMD,
            test_timeout_s=60,
            worktree_root=str(tmp_path / "wt"),
        ),
        agent=AgentConfig(bin=agent_bin, timeout_s=60, permission_mode="", model=None, effort=None),
        arms=[
            ArmConfig(
                name="control",
                label="A",
                env={**common, "FAKE_AGENT_COST": control_cost, "FAKE_AGENT_SEED": "a"},
                forbidden_patterns=["mcp__graphify__"],
                expect_absent=["graphify"],
            ),
            ArmConfig(
                name="graphify",
                label="B",
                env={
                    **common,
                    "FAKE_AGENT_COST": experiment_cost,
                    "FAKE_AGENT_SEED": "b",
                    "FAKE_AGENT_ACTIVATE": activate,
                    "FAKE_AGENT_SOLVE": solve_experiment,
                    "FAKE_AGENT_MCP": "graphify",
                    "FAKE_AGENT_COUNTER": str(tmp_path / "counter"),
                },
                activation_patterns=["mcp__graphify__"],
                expect_present=["graphify"],
            ),
        ],
        index=IndexConfig(),
        claim={"factor": 70.0, "source": "test"},
        pricing={"fake-model": {"input": 1.0, "output": 1.0,
                                "cache_write_5m": 1.0, "cache_write_1h": 1.0,
                                "cache_read": 1.0}},
    )


def _mined(repo: Path) -> list[dict]:
    tasks, _ = mine(MineConfig(repo=str(repo), test_globs=["tests/*"], max_tasks=50))
    return [t.to_dict() for t in tasks]


@pytest.fixture
def approved_manifest(demo_repo: Path, tmp_path: Path) -> Path:
    from bench import tasks as tasks_mod

    rows = _mined(demo_repo)
    for row in rows:
        row["review"] = "ok"
    path = tmp_path / "tasks.yaml"
    tasks_mod.save(path, {"repo": str(demo_repo), "test_cmd": TEST_CMD}, rows)
    return path


def test_mining_finds_every_task_and_no_noise(demo_repo: Path):
    tasks = _mined(demo_repo)
    assert len(tasks) == 3
    assert not any("left-pad" in t["subject"] for t in tasks)


def test_verification_accepts_every_real_task(demo_repo: Path, tmp_path: Path):
    for task in _mined(demo_repo):
        state = verify_one(str(demo_repo), task, TEST_CMD, tmp_path / "verify", None, 60, 60)
        assert state == "ok", f"{task['subject']}: tests must pass at the commit and fail at its parent"


def test_verification_rejects_a_task_whose_tests_already_pass(demo_repo: Path, tmp_path: Path):
    """A task whose grader is green at the starting state is a free win for both arms."""
    task = dict(_mined(demo_repo)[0])
    task["parent"] = task["commit"]  # start where the work is already done
    state = verify_one(str(demo_repo), task, TEST_CMD, tmp_path / "verify2", None, 60, 60)
    assert state == "passes_at_parent"


def test_plan_is_balanced_and_deterministic():
    tasks = [{"id": "t001"}, {"id": "t002"}]
    first = plan(tasks, ["control", "graphify"], 3, seed=42)
    second = plan(tasks, ["control", "graphify"], 3, seed=42)

    assert first == second, "the same seed must give the same order"
    assert len(first) == 12
    assert sum(1 for r in first if r["arm"] == "control") == 6
    assert sum(1 for r in first if r["arm"] == "graphify") == 6
    assert len({run_key(r) for r in first}) == 12
    assert [r["arm"] for r in first] != ["control"] * 6 + ["graphify"] * 6


def test_full_sweep_measures_the_planted_saving(demo_repo: Path, tmp_path: Path,
                                                approved_manifest: Path):
    cfg = _config(demo_repo, tmp_path, approved_manifest, repeats=2)
    tasks = [dict(t, review="ok", verified="ok") for t in _mined(demo_repo)]
    out = Path(cfg.run.out_dir) / "sweep"

    state = execute(cfg, tasks, out)
    assert state["executed"] == 12
    rows = list(read_jsonl(out / "runs.jsonl"))
    assert len(rows) == 12
    assert all(r["valid"] for r in rows), [r.get("invalid_reason") for r in rows]
    assert all(r["solved"] for r in rows), "the fake agent applies the real fix"

    summary = analyze(cfg, out)
    primary = summary["metrics"]["cost_usd"]["both_solved"]
    assert primary["n"] == 3
    # control 0.20 / experiment 0.10 -> a factor of about two, jitter aside
    assert 1.6 < primary["geometric_mean"] < 2.5
    assert summary["headline"]["verdict"] in {"null", "smaller_but_real"}
    assert (out / "report.md").exists()
    assert "Did the skill run at all" in (out / "report.md").read_text(encoding="utf-8")


def test_unused_skill_runs_are_counted_and_reported(demo_repo: Path, tmp_path: Path,
                                                    approved_manifest: Path):
    """The ponytail trap: every second experimental run never touches the skill.

    Those runs stay in. Dropping them would compute the arm's average over only
    the runs where the skill appealed, which is the flattering half of the data.
    They are labelled instead, and the label reaches the report.
    """
    cfg = _config(demo_repo, tmp_path, approved_manifest, activate="alternate", repeats=2)
    tasks = [dict(t, review="ok", verified="ok") for t in _mined(demo_repo)]
    out = Path(cfg.run.out_dir) / "dead"

    execute(cfg, tasks, out)
    rows = list(read_jsonl(out / "runs.jsonl"))
    experimental = [r for r in rows if r["arm"] == "graphify"]

    assert len(experimental) == 6
    assert all(r["valid"] for r in rows), "an unused skill is a result, not a broken run"

    unused = [r for r in experimental if r["activation_status"] == "available_unused"]
    assert len(unused) == 3, "every second experimental run never touched the skill"
    assert all(r["activation_status"] == "used"
               for r in experimental if r not in unused)

    summary = analyze(cfg, out)
    assert summary["validity"]["n_invalid"] == 0
    assert summary["validity"]["per_arm"]["graphify"]["available_unused"] == 3
    assert summary["validity"]["per_arm"]["graphify"]["used_skill"] == 3
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "left untouched in 3" in report


def test_a_cheaper_arm_that_stops_solving_is_visible(demo_repo: Path, tmp_path: Path,
                                                     approved_manifest: Path):
    cfg = _config(demo_repo, tmp_path, approved_manifest, solve_experiment="0", repeats=2)
    tasks = [dict(t, review="ok", verified="ok") for t in _mined(demo_repo)]
    out = Path(cfg.run.out_dir) / "unsolved"

    execute(cfg, tasks, out)
    summary = analyze(cfg, out)

    assert summary["solve"]["only_control"] == 3
    assert summary["metrics"]["cost_usd"]["both_solved"].get("insufficient")


def test_resume_skips_finished_runs(demo_repo: Path, tmp_path: Path, approved_manifest: Path):
    cfg = _config(demo_repo, tmp_path, approved_manifest, repeats=2)
    tasks = [dict(t, review="ok", verified="ok") for t in _mined(demo_repo)]
    out = Path(cfg.run.out_dir) / "resume"

    first = execute(cfg, tasks, out)
    assert first["executed"] == 12

    second = execute(cfg, tasks, out)
    assert second["executed"] == 0
    assert second["resumed_from"] == 12
    assert len(list(read_jsonl(out / "runs.jsonl"))) == 12


def test_budget_cap_stops_the_sweep_and_says_what_is_missing(demo_repo: Path, tmp_path: Path,
                                                             approved_manifest: Path):
    cfg = _config(demo_repo, tmp_path, approved_manifest, repeats=2, budget=0.5)
    tasks = [dict(t, review="ok", verified="ok") for t in _mined(demo_repo)]
    out = Path(cfg.run.out_dir) / "budget"

    state = execute(cfg, tasks, out)

    assert state["stopped_on_budget"] is True
    assert state["skipped_budget"] > 0
    assert state["executed"] + state["skipped_budget"] == 12
    assert state["spent_usd"] >= 0.5


def test_dry_run_writes_a_plan_and_spends_nothing(demo_repo: Path, tmp_path: Path,
                                                  approved_manifest: Path):
    cfg = _config(demo_repo, tmp_path, approved_manifest, repeats=2)
    tasks = [dict(t, review="ok", verified="ok") for t in _mined(demo_repo)]
    out = Path(cfg.run.out_dir) / "dry"

    state = execute(cfg, tasks, out, dry_run=True)

    assert state["executed"] == 0
    assert (out / "plan.json").exists()
    assert not (out / "runs.jsonl").exists()


def test_the_source_repository_is_never_written_to(demo_repo: Path, tmp_path: Path,
                                                   approved_manifest: Path):
    head_before = subprocess.run(["git", "-C", str(demo_repo), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout
    status_before = subprocess.run(["git", "-C", str(demo_repo), "status", "--porcelain"],
                                   capture_output=True, text=True).stdout

    cfg = _config(demo_repo, tmp_path, approved_manifest, repeats=1)
    tasks = [dict(t, review="ok", verified="ok") for t in _mined(demo_repo)]
    execute(cfg, tasks, Path(cfg.run.out_dir) / "readonly")

    head_after = subprocess.run(["git", "-C", str(demo_repo), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout
    status_after = subprocess.run(["git", "-C", str(demo_repo), "status", "--porcelain"],
                                  capture_output=True, text=True).stdout

    assert head_before == head_after
    assert status_before == status_after


def test_the_worktree_path_tells_the_agent_nothing(demo_repo: Path, tmp_path: Path,
                                                   approved_manifest: Path):
    """The agent reads its own path on every file call; it must learn nothing from it."""
    from bench.runner import worktree_name

    name = worktree_name("graphify-superset-pilot", "t018|control|3")
    for cue in ("graphify", "control", "pilot", "t018", "bench", "skill"):
        assert cue not in name, f"the sandbox path leaks {cue!r} to the agent"
    assert name != worktree_name("graphify-superset-pilot", "t018|graphify|3")


def test_an_unreachable_skill_stops_the_sweep_before_it_spends(
    demo_repo: Path, tmp_path: Path, approved_manifest: Path
):
    """The failure that cost the first sweep: an arm that cannot call its own tool.

    Every run would have looked like a cheap, silent success. The probe has to
    catch it before any task runs, not after the night is gone.
    """
    cfg = _config(demo_repo, tmp_path, approved_manifest, activate="0", repeats=2)
    tasks = [dict(t, review="ok", verified="ok") for t in _mined(demo_repo)]
    out = Path(cfg.run.out_dir) / "unreachable"

    state = execute(cfg, tasks, out)

    assert state.get("probe_failed") is True
    assert state["executed"] == 0, "not one task may run once the probe has failed"
    assert not (out / "runs.jsonl").exists()
    probe = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    assert probe["ok"] is False
    assert probe["arms"]["graphify"]["reachable"] is False


def test_a_reachable_skill_lets_the_sweep_run(demo_repo: Path, tmp_path: Path,
                                              approved_manifest: Path):
    cfg = _config(demo_repo, tmp_path, approved_manifest, activate="1", repeats=1)
    tasks = [dict(t, review="ok", verified="ok") for t in _mined(demo_repo)]
    out = Path(cfg.run.out_dir) / "reachable"

    state = execute(cfg, tasks, out)

    assert not state.get("probe_failed")
    assert state["executed"] == 6
    probe = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    assert probe["ok"] is True
    assert probe["arms"]["graphify"]["reachable"] is True


def test_the_used_only_scope_drops_repeats_that_ignored_the_skill(
    demo_repo: Path, tmp_path: Path, approved_manifest: Path
):
    """Descriptive, not randomised: the model picks when to reach for the tool."""
    cfg = _config(demo_repo, tmp_path, approved_manifest, activate="alternate", repeats=2)
    tasks = [dict(t, review="ok", verified="ok") for t in _mined(demo_repo)]
    out = Path(cfg.run.out_dir) / "used_only"

    execute(cfg, tasks, out)
    summary = analyze(cfg, out)

    rows = list(read_jsonl(out / "runs.jsonl"))
    unused = [r for r in rows if r.get("activation_status") == "available_unused"]
    assert unused, "the fixture must produce some runs that ignore the skill"

    scopes = summary["metrics"]["cost_usd"]
    assert "used_only" in scopes
    if not scopes["used_only"].get("insufficient"):
        assert scopes["used_only"]["n"] <= scopes["all_valid"]["n"]
    assert "read that row as description" in (out / "report.md").read_text(encoding="utf-8")
