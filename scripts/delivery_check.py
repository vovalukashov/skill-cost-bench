#!/usr/bin/env python3
"""Does the skill get used more when it is installed the way a user installs it?

The pilot handed the experimental arm its skill as text appended to the system
prompt, with the MCP server alongside. The model never once reached for it. That
is only a finding about the skill if the delivery was faithful, and it may not
have been: a real user's skill is *registered*, it appears in the session's own
list of skills, and Claude Code decides when to load its body.

So this runs the same real tasks under a registered skill — `.claude/skills/`
inside the working copy, `--setting-sources project` — and counts how often the
graph gets touched. If the count stays at zero, the pilot's headline stands. If
it jumps, the pilot measured my packaging rather than the tool.

    python3 scripts/delivery_check.py --config config-superset.yaml --tasks 3
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench import config as config_mod  # noqa: E402
from bench import index as index_mod  # noqa: E402
from bench import tasks as tasks_mod  # noqa: E402
from bench.activation import scan  # noqa: E402
from bench.agent import invoke, render_prompt  # noqa: E402
from bench.config import AgentConfig, ArmConfig  # noqa: E402
from bench.transcript import load  # noqa: E402
from bench.worktree import hide_paths, worktree  # noqa: E402

SKILL_SRC = Path.home() / ".claude" / "skills" / "graphify"


def registered_arm(base: ArmConfig) -> ArmConfig:
    """The same arm, minus the stub, plus whatever a real installation gives."""
    args = [a for a in base.args if a != "--disable-slash-commands"]
    return ArmConfig(
        name="graphify-registered",
        label="B2",
        use_index=True,
        args=args,
        env=dict(base.env),
        activation_patterns=list(base.activation_patterns),
        expect_present=[],
    )


def project_sources(agent: AgentConfig) -> AgentConfig:
    """Let the working copy's own `.claude/` be read.

    The sweep passes `--setting-sources ""`, which strips user and project
    settings alike and takes the registered skill with them. Swapping the value
    rather than dropping the flag keeps everything else about the session equal.
    """
    extra = list(agent.extra_args)
    if "--setting-sources" in extra:
        extra[extra.index("--setting-sources") + 1] = "project"
    else:
        extra += ["--setting-sources", "project"]
    return replace(agent, extra_args=extra)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--tasks", type=int, default=3)
    ap.add_argument("--index-from", required=True,
                    help="run directory whose indexes/ can be reused")
    ap.add_argument("--out", default="out/delivery-check",
                    help="where transcripts and results are kept for audit")
    args = ap.parse_args()

    cfg_path = Path(args.config).resolve()
    cfg = config_mod.resolve_paths(config_mod.load(cfg_path), cfg_path.parent)
    base = next(a for a in cfg.arms if a.use_index)
    arm = registered_arm(base)

    _, rows = tasks_mod.load(cfg.run.tasks_file)
    chosen = [t for t in rows if t.get("review") == "ok"][: args.tasks]
    indexes = Path(args.index_from) / "indexes"

    out_dir = Path(args.out)
    (out_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    results = []
    for task in chosen:
        index_dir = indexes / task["parent"][:12]
        if not index_dir.exists():
            print(f"{task['id']}: no prebuilt index, skipped")
            continue

        tmp = Path(tempfile.mkdtemp(prefix="delivery-"))
        with worktree(cfg.target.repo, task["parent"], tmp / "wt") as wt:
            hide_paths(wt, list(task.get("test_files", [])))
            # Everything the pilot stripped, still stripped — except the skill,
            # which is the whole point of this check.
            hide_paths(wt, [p for p in cfg.target.strip_paths if p != ".claude"])
            index_mod.install(index_dir, wt, cfg.index.paths)
            shutil.copytree(SKILL_SRC, wt / ".claude" / "skills" / "graphify",
                            dirs_exist_ok=True)

            transcript = out_dir / "transcripts" / f"{task['id']}__registered.jsonl"
            prompt = render_prompt(cfg.agent.prompt_template, task["prompt"])
            run = invoke(project_sources(cfg.agent), arm, prompt, wt, transcript)
            events = load(transcript)
            found = scan(events, arm.activation_patterns, strip=str(wt))
            init = next((e for e in events if e.get("type") == "system" and e.get("tools")), {})
            results.append({
                "task": task["id"],
                "used_skill": found["activated"],
                "hits": found["hits"],
                "evidence": found["evidence"][:1],
                "mentioned_only": found.get("mentioned_only", False),
                "skill_registered": "graphify" in (init.get("slash_commands") or []),
                "cost_usd": run.summary.get("cost_usd"),
                "wall_s": run.wall_s,
            })
            print(json.dumps(results[-1], ensure_ascii=False))

    used = sum(1 for r in results if r["used_skill"])
    payload = {
        "delivery": "registered skill in the working copy, --setting-sources project",
        "n_tasks": len(results),
        "n_used": used,
        "n_mentioned_only": sum(1 for r in results if r["mentioned_only"]),
        "results": results,
    }
    (out_dir / "delivery_check.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistered delivery: skill used in {used}/{len(results)} tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
