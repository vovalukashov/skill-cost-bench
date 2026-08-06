"""Configuration: everything that differs between the two arms lives in data.

The harness knows nothing about Graphify. An arm is a name, a set of environment
variables, a set of extra CLI flags, and the patterns that prove the skill did or
did not run. Point the same code at a different skill by editing the config.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Sequence

import yaml


class ConfigError(ValueError):
    pass


@dataclass
class ArmConfig:
    name: str
    label: str = ""
    env: dict[str, str] = field(default_factory=dict)
    args: list[str] = field(default_factory=list)
    activation_patterns: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)
    expect_present: list[str] = field(default_factory=list)
    expect_absent: list[str] = field(default_factory=list)
    use_index: bool = False


@dataclass
class IndexConfig:
    """The cost of having an index at all, kept out of the per-task numbers.

    A tool that saves 30% per task but wants its index rebuilt every morning and
    a tool that does not are two different tools. The build is run once, timed
    and priced on its own, and reported next to the savings.
    """

    build_cmd: str | None = None
    build_timeout_s: float = 3600.0
    paths: list[str] = field(default_factory=list)
    refresh_cmd: str | None = None
    refresh_timeout_s: float = 900.0


@dataclass
class AgentConfig:
    bin: str = "claude"
    model: str | None = None
    effort: str | None = None
    permission_mode: str = "acceptEdits"
    max_budget_usd: float | None = None
    timeout_s: float = 1800.0
    extra_args: list[str] = field(default_factory=list)
    prompt_template: str = "{prompt}"


@dataclass
class TargetConfig:
    repo: str = ""
    test_cmd: str = "pytest -q {tests}"
    test_timeout_s: float = 900.0
    setup_cmd: str | None = None
    setup_timeout_s: float = 1800.0
    worktree_root: str = ""
    strip_paths: list[str] = field(default_factory=list)


@dataclass
class RunConfig:
    name: str = "run"
    seed: int = 20260806
    repeats: int = 2
    budget_usd: float = 10.0
    out_dir: str = "out"
    tasks_file: str = "tasks/tasks.yaml"
    max_tasks: int | None = None
    bootstrap_resamples: int = 10_000


@dataclass
class Config:
    run: RunConfig
    target: TargetConfig
    agent: AgentConfig
    arms: list[ArmConfig]
    index: IndexConfig
    claim: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def claim_factor(self) -> float:
        return float(self.claim.get("factor", 1.0))

    def arm(self, name: str) -> ArmConfig:
        for a in self.arms:
            if a.name == name:
                return a
        raise ConfigError(f"unknown arm: {name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run": asdict(self.run),
            "target": asdict(self.target),
            "agent": asdict(self.agent),
            "arms": [asdict(a) for a in self.arms],
            "index": asdict(self.index),
            "claim": self.claim,
        }


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise ConfigError(f"section '{key}' must be a mapping")
    return value


def load(path: str | Path) -> Config:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping")

    arms_raw = data.get("arms")
    if not isinstance(arms_raw, list) or len(arms_raw) != 2:
        raise ConfigError("exactly two arms are required (control and experiment)")
    arms = [ArmConfig(**a) for a in arms_raw]
    if arms[0].name == arms[1].name:
        raise ConfigError("arms must have distinct names")

    cfg = Config(
        run=RunConfig(**_section(data, "run")),
        target=TargetConfig(**_section(data, "target")),
        agent=AgentConfig(**_section(data, "agent")),
        arms=arms,
        index=IndexConfig(**_section(data, "index")),
        claim=_section(data, "claim"),
        raw=data,
    )
    validate(cfg)
    return cfg


def validate(cfg: Config) -> None:
    if not cfg.target.repo:
        raise ConfigError("target.repo is required")
    if cfg.run.repeats < 1:
        raise ConfigError("run.repeats must be >= 1")
    if cfg.run.budget_usd <= 0:
        raise ConfigError("run.budget_usd must be > 0")
    experimental = [a for a in cfg.arms if a.activation_patterns]
    if not experimental:
        raise ConfigError(
            "at least one arm must declare activation_patterns — without them a "
            "skill that never runs is scored as a skill that works for free"
        )
    if any(a.use_index for a in cfg.arms) and not cfg.index.build_cmd:
        raise ConfigError("an arm sets use_index but index.build_cmd is empty")


def resolve_paths(cfg: Config, base: str | Path) -> Config:
    """Make repo/tasks/out paths absolute relative to the config file location."""
    base = Path(base).resolve()
    cfg.target.repo = str((base / cfg.target.repo).resolve()) if not Path(cfg.target.repo).is_absolute() else cfg.target.repo
    if not Path(cfg.run.tasks_file).is_absolute():
        cfg.run.tasks_file = str((base / cfg.run.tasks_file).resolve())
    if not Path(cfg.run.out_dir).is_absolute():
        cfg.run.out_dir = str((base / cfg.run.out_dir).resolve())
    if not cfg.target.worktree_root:
        cfg.target.worktree_root = str(Path("/tmp") / "skill-cost-bench-worktrees")
    return cfg
