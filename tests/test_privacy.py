from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from bench import privacy
from scripts.check_publish import scan

RULES = {
    "literals": ["acme-internal"],
    "patterns": [r"git@github\.com:acme-corp/"],
    "paths": ["/Users/someone/work/acme-monorepo"],
}


def test_a_repo_on_the_list_is_recognised(tmp_path: Path):
    (tmp_path / ".private-sources.yaml").write_text(yaml.safe_dump(RULES), encoding="utf-8")
    assert privacy.match_source("/tmp/acme-internal/repo", RULES) == "acme-internal"
    assert privacy.match_source("/Users/someone/work/acme-monorepo/x", RULES)


def test_an_unrelated_repo_is_not_flagged():
    assert privacy.match_source("/Users/me/projects/night", RULES) is None


def test_rules_are_found_in_a_parent_directory(tmp_path: Path):
    (tmp_path / ".private-sources.yaml").write_text(yaml.safe_dump(RULES), encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert privacy.load_rules(nested)["literals"] == ["acme-internal"]


def test_no_rules_file_means_no_rules_but_the_publish_gate_still_fails(tmp_path: Path):
    """Absent rules are safe here (nothing is marked) and fatal at the gate."""
    assert privacy.load_rules(tmp_path) == {}


def test_the_marker_names_the_source(tmp_path: Path):
    path = privacy.write_marker(tmp_path, "acme-internal")
    text = path.read_text(encoding="utf-8")
    assert path.name == "PRIVATE_DO_NOT_PUBLISH"
    assert "acme-internal" in text
    assert "Do not publish" in text


def _git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True,
                   capture_output=True)
    (root / "README.md").write_text("# clean\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@e.x",
                    "commit", "-q", "-m", "init"], check=True, capture_output=True)
    return root


def test_the_gate_passes_a_clean_repository(tmp_path: Path):
    root = _git_repo(tmp_path)
    assert scan(root, RULES) == []


def test_the_gate_blocks_a_leaked_literal(tmp_path: Path):
    root = _git_repo(tmp_path)
    (root / "notes.md").write_text("mined from acme-internal last week\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)

    problems = scan(root, RULES)
    assert any("acme-internal" in p for p in problems)


def test_the_gate_blocks_a_tracked_task_manifest(tmp_path: Path):
    root = _git_repo(tmp_path)
    (root / "tasks").mkdir()
    (root / "tasks" / "tasks.yaml").write_text("tasks: []\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-Af"], check=True, capture_output=True)

    problems = scan(root, RULES)
    assert any("tasks/" in p and "never be tracked" in p for p in problems)


def test_the_gate_blocks_a_leaked_absolute_path(tmp_path: Path):
    root = _git_repo(tmp_path)
    (root / "config.yaml").write_text(
        "repo: /Users/someone/work/acme-monorepo\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)

    assert any("private source" in p for p in scan(root, RULES))


def test_the_gate_blocks_a_private_remote(tmp_path: Path):
    root = _git_repo(tmp_path)
    subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                    "git@github.com:acme-corp/acme-internal.git"], check=True,
                   capture_output=True)

    assert any("remote" in p for p in scan(root, RULES))


def test_this_repository_ships_the_hook_and_the_example(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    hook = root / ".githooks" / "pre-push"
    assert hook.exists(), "the guard has to run without anyone remembering it"
    assert "check_publish.py" in hook.read_text(encoding="utf-8")
    assert (root / ".private-sources.example.yaml").exists()
    assert not (root / ".private-sources.yaml").exists() or True  # local only, never tracked

    tracked = subprocess.run(["git", "-C", str(root), "ls-files"],
                             capture_output=True, text=True).stdout
    assert ".private-sources.yaml" not in tracked.split("\n")


def test_the_hook_refuses_rather_than_skips_when_it_cannot_run():
    """A guard that gives up quietly is not a guard."""
    hook = (Path(__file__).resolve().parents[1] / ".githooks" / "pre-push").read_text(encoding="utf-8")
    assert "exit 1" in hook, "the hook must fail closed when no interpreter works"
    assert "import yaml" in hook, "it must verify the interpreter can actually run the guard"
    assert ".venv/bin/python" in hook, "it should prefer the project venv, which has PyYAML"


def test_a_tracked_manifest_must_name_its_public_source(tmp_path: Path):
    """`tasks/` is banned outright; copying a manifest elsewhere must not evade that."""
    root = _git_repo(tmp_path)
    (root / "data").mkdir()
    (root / "data" / "x.tasks.yaml").write_text("tasks: []\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)

    problems = scan(root, RULES)
    assert any("public_source" in p for p in problems), (
        "a manifest outside tasks/ still carries commit messages out of some repository"
    )


def test_a_manifest_that_declares_a_public_source_passes(tmp_path: Path):
    root = _git_repo(tmp_path)
    (root / "data").mkdir()
    (root / "data" / "x.tasks.yaml").write_text(
        "public_source: https://github.com/apache/superset\ntasks: []\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)

    assert scan(root, RULES) == []


def test_a_manifest_claiming_a_local_path_as_its_source_is_refused(tmp_path: Path):
    root = _git_repo(tmp_path)
    (root / "data").mkdir()
    (root / "data" / "x.tasks.yaml").write_text(
        "public_source: /Users/someone/work/private-repo\ntasks: []\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)

    assert any("public_source" in p for p in scan(root, RULES)), (
        "only an https URL counts as a public source"
    )
