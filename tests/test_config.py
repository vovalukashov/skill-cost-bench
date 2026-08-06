from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bench import config as config_mod

BASE = {
    "run": {"name": "x", "budget_usd": 1.0},
    "target": {"repo": "/tmp/repo"},
    "agent": {"bin": "claude"},
    "index": {},
    "claim": {"factor": 70.0},
    "arms": [
        {"name": "control", "forbidden_patterns": ["skill"]},
        {"name": "skill", "activation_patterns": ["mcp__skill__"]},
    ],
}


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_a_valid_config_loads(tmp_path: Path):
    cfg = config_mod.load(_write(tmp_path, BASE))
    assert [a.name for a in cfg.arms] == ["control", "skill"]
    assert cfg.claim_factor == 70.0


def test_an_experiment_without_activation_patterns_is_refused(tmp_path: Path):
    data = {**BASE, "arms": [{"name": "control"}, {"name": "skill"}]}
    with pytest.raises(config_mod.ConfigError, match="activation_patterns"):
        config_mod.load(_write(tmp_path, data))


def test_exactly_two_arms_are_required(tmp_path: Path):
    data = {**BASE, "arms": [BASE["arms"][0]]}
    with pytest.raises(config_mod.ConfigError, match="two arms"):
        config_mod.load(_write(tmp_path, data))


def test_use_index_without_a_build_command_is_refused(tmp_path: Path):
    arms = [BASE["arms"][0], {**BASE["arms"][1], "use_index": True}]
    with pytest.raises(config_mod.ConfigError, match="use_index"):
        config_mod.load(_write(tmp_path, {**BASE, "arms": arms}))


def test_a_missing_skill_file_is_a_config_error_not_a_traceback(tmp_path: Path):
    arms = [BASE["arms"][0], {**BASE["arms"][1], "append_system_prompt_file": "nope.md"}]
    with pytest.raises(config_mod.ConfigError, match="append_system_prompt_file"):
        config_mod.load(_write(tmp_path, {**BASE, "arms": arms}))


def test_the_skill_file_resolves_next_to_the_config(tmp_path: Path):
    (tmp_path / "SKILL.md").write_text("use the graph", encoding="utf-8")
    arms = [BASE["arms"][0], {**BASE["arms"][1], "append_system_prompt_file": "SKILL.md"}]
    cfg = config_mod.load(_write(tmp_path, {**BASE, "arms": arms}))
    assert Path(cfg.arm("skill").append_system_prompt_file).is_absolute()


def test_the_shipped_example_config_is_valid_except_for_its_placeholders(tmp_path: Path):
    """config.example.yaml must stay loadable, so it cannot silently rot."""
    raw = yaml.safe_load(Path("config.example.yaml").read_text(encoding="utf-8"))
    raw["arms"][1].pop("append_system_prompt_file", None)   # created by RUNBOOK step 1
    raw["run"]["out_dir"] = str(tmp_path / "out")
    raw["run"]["tasks_file"] = str(tmp_path / "tasks.yaml")
    cfg = config_mod.load(_write(tmp_path, raw))
    assert cfg.claim_factor == 70.0
    assert cfg.arm("graphify").use_index is True
    assert "--disable-slash-commands" in cfg.arm("control").args
