"""Orchestration: shuffled, paired, resumable, budget-capped.

Both arms see the same tasks under the same model, effort, permission mode and
time limit. The only difference is the arm's own environment and flags.

Order is shuffled once with a fixed seed and the arms are interleaved, so a slow
hour on the API or a bad afternoon for the model cannot land on one arm. Rows are
appended to JSONL as they finish, so dying on run 180 of 240 costs nothing.
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
from pathlib import Path
from typing import Any, Iterable

from . import index as index_mod
from . import pricing as pricing_mod
from .activation import check_arm, check_availability
from .probe import probe_all
from .agent import invoke, render_prompt
from .config import Config
from .grade import grade
from .util import append_jsonl, read_jsonl, run, utc_iso, write_json
from .worktree import hide_paths, prune, worktree


def plan(tasks: Iterable[dict[str, Any]], arms: Iterable[str], repeats: int,
         seed: int) -> list[dict[str, Any]]:
    """Every (task, arm, repeat) cell, shuffled once with a fixed seed."""
    task_ids = [t["id"] for t in tasks]
    arm_names = list(arms)
    runs = [
        {"task": t, "arm": a, "rep": rep}
        for t in task_ids
        for a in arm_names
        for rep in range(1, repeats + 1)
    ]
    random.Random(seed).shuffle(runs)
    return runs


def run_key(spec: dict[str, Any]) -> str:
    return f"{spec['task']}|{spec['arm']}|{spec['rep']}"


def worktree_name(run_name: str, key: str) -> str:
    """A directory name that tells the agent nothing about the experiment.

    The first sweep named worktrees `graphify-superset-pilot-t018-control-3`, and
    every Read, Edit and Bash call echoed that path back into the transcript. The
    control arm was therefore told, dozens of times per run, that it was the
    control in a graphify benchmark. It also tripped the contamination guard on
    its own path. A digest carries the same uniqueness and none of the cues; the
    mapping back to the run lives in runs.jsonl.
    """
    return "wt-" + hashlib.sha1(f"{run_name}|{key}".encode()).hexdigest()[:12]


def completed_keys(runs_path: str | Path) -> set[str]:
    return {row["run_key"] for row in read_jsonl(runs_path) if row.get("run_key")}


def spent_usd(runs_path: str | Path) -> float:
    return sum(float(row.get("cost_usd") or 0.0) for row in read_jsonl(runs_path))


def _prepare_worktree(cfg: Config, wt: Path, task: dict[str, Any]) -> dict[str, Any]:
    """Hide the tests, strip configs, run the project's setup command."""
    hidden = hide_paths(wt, list(task.get("test_files", [])))
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
    return {"hidden": hidden, "stripped": stripped, "setup": setup}


def execute_one(cfg: Config, spec: dict[str, Any], task: dict[str, Any],
                out_dir: Path, index_source: Path | None,
                price_table: dict[str, pricing_mod.ModelPrice] | None = None) -> dict[str, Any]:
    arm = cfg.arm(spec["arm"])
    key = run_key(spec)
    wt_path = Path(cfg.target.worktree_root) / worktree_name(cfg.run.name, key)
    transcript = out_dir / "transcripts" / f"{key.replace('|', '__')}.jsonl"

    row: dict[str, Any] = {
        "run_key": key,
        "task": spec["task"],
        "arm": arm.name,
        "rep": spec["rep"],
        "commit": task.get("commit"),
        "parent": task.get("parent"),
        "started_at": utc_iso(),
        "valid": True,
        "invalid_reason": None,
        "solved": False,
        "cost_usd": None,
    }

    try:
        with worktree(cfg.target.repo, task["parent"], wt_path) as wt:
            row["prepare"] = _prepare_worktree(cfg, wt, task)

            if arm.use_index and index_source is not None:
                row["index_installed"] = index_mod.install(
                    index_source, wt, cfg.index.paths
                )
                row["index_refresh"] = index_mod.refresh(cfg.index, wt, arm.env)

            prompt = render_prompt(cfg.agent.prompt_template, task["prompt"])
            agent_run = invoke(cfg.agent, arm, prompt, wt, transcript)
            row["agent"] = agent_run.to_dict()

            summary = agent_run.summary
            # Reported by the CLI. Populated and accurate on a subscription, but
            # kept as a cross-check rather than the primary metric: a computed
            # figure can be re-priced later and does not depend on how a given
            # CLI version reports.
            row["cost_reported_usd"] = summary.get("cost_usd")
            row["cost_usd"] = pricing_mod.price_run(
                summary.get("usage"), summary.get("model"), price_table or {}
            )
            row["usage"] = summary.get("usage")
            row["total_tokens"] = summary.get("total_tokens")
            row["output_tokens"] = summary.get("output_tokens")
            row["num_turns"] = summary.get("num_turns")
            row["wall_s"] = agent_run.wall_s

            from .transcript import load as load_transcript

            events = load_transcript(transcript)
            checks = check_arm(events, arm.activation_patterns, arm.forbidden_patterns,
                               strip=str(wt))
            row.update({k: v for k, v in checks.items() if k not in ("valid", "invalid_reason")})
            if not checks["valid"]:
                row["valid"] = False
                row["invalid_reason"] = checks["invalid_reason"]

            row["availability"] = check_availability(
                summary.get("tools", []),
                summary.get("mcp_servers", []),
                summary.get("slash_commands", []),
                arm.expect_present,
                arm.expect_absent,
            )
            if not row["availability"]["ok"] and row["valid"]:
                row["valid"] = False
                row["invalid_reason"] = "arm was not configured as declared"

            if not agent_run.ok and row["valid"]:
                row["valid"] = False
                row["invalid_reason"] = (
                    "agent timed out" if agent_run.timed_out else "agent exited with an error"
                )

            grade_result = grade(
                cfg.target.repo,
                wt,
                task["commit"],
                task.get("test_files", []),
                cfg.target.test_cmd,
                timeout=cfg.target.test_timeout_s,
            )
            row["grade"] = grade_result.to_dict()
            row["solved"] = grade_result.passed
    except Exception as exc:  # noqa: BLE001 - a broken run must not stop the sweep
        row["valid"] = False
        row["invalid_reason"] = f"harness error: {type(exc).__name__}: {exc}"[:400]

    row["finished_at"] = utc_iso()
    return row


def execute(cfg: Config, tasks: list[dict[str, Any]], out_dir: str | Path,
            resume: bool = True, dry_run: bool = False) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    runs_path = out / "runs.jsonl"

    by_id = {t["id"]: t for t in tasks}
    price_table = pricing_mod.load_table(cfg.pricing)
    specs = plan(tasks, [a.name for a in cfg.arms], cfg.run.repeats, cfg.run.seed)
    done = completed_keys(runs_path) if resume else set()
    already = spent_usd(runs_path) if resume else 0.0

    state = {
        "planned": len(specs),
        "resumed_from": len(done),
        "executed": 0,
        "skipped_budget": 0,
        "spent_usd": already,
        "budget_usd": cfg.run.budget_usd,
        "stopped_on_budget": False,
    }

    if dry_run:
        write_json(out / "plan.json", {"state": state, "runs": specs})
        return state

    wants_index = any(a.use_index for a in cfg.arms) and bool(cfg.index.build_cmd)
    indexes = IndexCache(cfg, out) if wants_index else None

    if indexes is not None:
        # The probe needs a built index to be a fair test of reachability, and
        # the first task's is as good as any.
        first_parent = by_id[specs[0]["task"]]["parent"]
        probe_index = indexes.for_commit(first_parent)
        if probe_index is None:
            state["index_build_failed"] = True
            return state
    else:
        first_parent = by_id[specs[0]["task"]]["parent"]
        probe_index = None

    if any(a.activation_patterns for a in cfg.arms):
        probe_result = probe_all(cfg, first_parent, probe_index, out / "transcripts")
        write_json(out / "probe.json", probe_result)
        state["probe"] = {k: v["reachable"] for k, v in probe_result["arms"].items()}
        if not probe_result["ok"]:
            # Every run of an unreachable arm would be a silent no-op that looks
            # exactly like a cheap success. Refuse to spend the night on it.
            state["probe_failed"] = True
            return state

    prune(cfg.target.repo)
    for spec in specs:
        key = run_key(spec)
        if key in done:
            continue
        if state["spent_usd"] >= cfg.run.budget_usd:
            state["skipped_budget"] += 1
            state["stopped_on_budget"] = True
            continue
        task = by_id[spec["task"]]
        index_source = indexes.for_commit(task["parent"]) if indexes is not None else None
        row = execute_one(cfg, spec, task, out, index_source, price_table)
        append_jsonl(runs_path, row)
        state["executed"] += 1
        state["spent_usd"] += float(row.get("cost_usd") or 0.0)

    write_json(out / "run_state.json", state)
    return state


class IndexCache:
    """One index per task, built at the commit the agent will actually see.

    The first design built a single index at repo HEAD and copied it into every
    worktree. That is wrong in a way that flatters the skill: the task commits
    are ancestors of HEAD, so the graph indexes a codebase in which the fix under
    test has already landed. Grepping the HEAD graph for one pilot task turned up
    both identifiers from its solution. The task's own answer must not be sitting
    in the experimental arm's index.

    So the index is built at each task's parent commit — exactly the tree the
    agent is handed, no future in it — and cached by commit, because repeats and
    both arms of the same task share one.

    The cost of the fix is honesty about a second thing: a real user's graph is
    always a little stale, and this one never is. That is a limitation of the
    measurement, recorded rather than hidden, and it points the same way as the
    leak did — in the skill's favour.
    """

    def __init__(self, cfg: Config, out: Path, reuse_from: str | Path | None = None) -> None:
        self.cfg = cfg
        self.root = Path(out) / "indexes"
        self.builds: dict[str, dict[str, Any]] = {}
        self.arm = next(a for a in cfg.arms if a.use_index)
        # Defaulting to the config keeps a caller from silently getting no reuse
        # by forgetting an argument, which is how this was first written.
        source = reuse_from if reuse_from is not None else cfg.index.reuse_from
        self.reuse_from = Path(source) / "indexes" if source else None
        ledger = self.root / "builds.json"
        if ledger.exists():
            # A sweep that died halfway rebuilt every index on restart, which is
            # a quarter-hour of CPU for files already on disk.
            self.builds = json.loads(ledger.read_text(encoding="utf-8"))

    def _adopt(self, commit: str, dest: Path) -> bool:
        """Take an index built by an earlier run, if one is offered and complete."""
        if self.reuse_from is None:
            return False
        src = self.reuse_from / commit[:12]
        if not all((src / p).exists() for p in self.cfg.index.paths):
            return False
        shutil.copytree(src, dest, dirs_exist_ok=True)

        # Carry the original's figures across. Recording a reused index as
        # costing nothing would let a run that skipped the build report the
        # index as free, which is the one thing this section exists to prevent.
        ledger = self.reuse_from / "builds.json"
        origin: dict[str, Any] = {}
        if ledger.exists():
            origin = json.loads(ledger.read_text(encoding="utf-8")).get(commit, {})
        self.builds[commit] = {
            **origin,
            "built": True,
            "commit": commit,
            "reused_from": str(src),
            "command": self.cfg.index.build_cmd,
        }
        write_json(self.root / "builds.json", self.builds)
        return True

    def for_commit(self, commit: str) -> Path | None:
        dest = self.root / commit[:12]
        if commit in self.builds:
            built = self.builds[commit].get("built")
            if built and all((dest / p).exists() for p in self.cfg.index.paths):
                return dest
            if built:
                self.builds.pop(commit)  # recorded but gone from disk

        if self._adopt(commit, dest):
            return dest

        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        with worktree(self.cfg.target.repo, commit, dest.with_suffix(".wt")) as wt:
            result = index_mod.build(self.cfg.index, wt, self.arm.env)
            if result.built:
                dest.mkdir(parents=True, exist_ok=True)
                index_mod.install(wt, dest, self.cfg.index.paths)

        payload = result.to_dict()
        payload["commit"] = commit
        self.builds[commit] = payload
        write_json(self.root / "builds.json", self.builds)
        return dest if result.built else None
