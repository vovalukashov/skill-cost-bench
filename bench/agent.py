"""Running one agent session inside one worktree.

The agent is invoked head-less with ``--output-format stream-json``, so the whole
session is on disk afterwards: every tool call, the init event that says what the
session was offered, and the result event that says what it cost.

The binary is configuration, not code. Tests point it at a fake agent that emits
the same event shapes, which is how the pipeline can be exercised end to end
without spending anything.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .config import AgentConfig, ArmConfig
from .transcript import SessionSummary, load, summarize
from .util import Proc, run, tail


@dataclass
class AgentRun:
    ok: bool
    returncode: int
    timed_out: bool
    wall_s: float
    session_id: str
    transcript_path: str
    stderr_tail: str
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_argv(agent: AgentConfig, arm: ArmConfig, prompt: str, session_id: str) -> list[str]:
    argv = [agent.bin, "-p", prompt, "--output-format", "stream-json", "--verbose"]
    if agent.model:
        argv += ["--model", agent.model]
    if agent.effort:
        argv += ["--effort", agent.effort]
    if agent.permission_mode:
        argv += ["--permission-mode", agent.permission_mode]
    if agent.max_budget_usd:
        argv += ["--max-budget-usd", str(agent.max_budget_usd)]
    argv += ["--session-id", session_id]
    argv += list(agent.extra_args)
    argv += list(arm.args)
    if arm.append_system_prompt_file:
        text = Path(arm.append_system_prompt_file).read_text(encoding="utf-8")
        argv += ["--append-system-prompt", text]
    return argv


def invoke(
    agent: AgentConfig,
    arm: ArmConfig,
    prompt: str,
    cwd: str | Path,
    transcript_path: str | Path,
    env: dict[str, str] | None = None,
) -> AgentRun:
    session_id = str(uuid.uuid4())
    argv = build_argv(agent, arm, prompt, session_id)

    merged_env = dict(arm.env)
    if env:
        merged_env.update(env)
    # Keep the harness out of the agent's own telemetry-shaped decisions.
    merged_env.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")

    proc: Proc = run(argv, cwd=cwd, env=merged_env, timeout=agent.timeout_s)

    path = Path(transcript_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(proc.stdout, encoding="utf-8")

    events = load(path)
    summary: SessionSummary = summarize(events)
    return AgentRun(
        ok=proc.returncode == 0 and not proc.timed_out and not summary.is_error,
        returncode=proc.returncode,
        timed_out=proc.timed_out,
        wall_s=round(proc.duration_s, 2),
        session_id=summary.session_id or session_id,
        transcript_path=str(path),
        stderr_tail=tail(proc.stderr, 2000),
        summary=summary.to_dict(),
    )


TASK_PROMPT = """You are working in a checkout of this repository at an earlier commit.

Task:
{prompt}

Rules:
- Change the source code so the task is done.
- Do not write or modify any test files; the tests that judge this work are not
  in the tree and will be restored afterwards.
- Do not create git commits, branches or tags.
- When you are done, stop. Do not ask questions; there is nobody to answer them.
"""


def render_prompt(template: str, task_prompt: str) -> str:
    base = TASK_PROMPT.format(prompt=task_prompt)
    if template and template != "{prompt}":
        return template.format(prompt=task_prompt, task=base)
    return base
