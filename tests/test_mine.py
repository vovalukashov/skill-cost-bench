from __future__ import annotations

from pathlib import Path

from bench.mine import MineConfig, clean_message, leak_check, mine


def _cfg(repo: Path, **kw) -> MineConfig:
    base = dict(repo=str(repo), test_globs=["tests/*", "tests/**"], max_tasks=50)
    base.update(kw)
    return MineConfig(**base)


def test_mines_the_real_task_and_skips_the_dependency_bump(demo_repo: Path):
    tasks, rejected = mine(_cfg(demo_repo))
    subjects = [t.subject for t in tasks]

    assert any("percentage discounts" in s for s in subjects)
    assert not any("left-pad" in s for s in subjects)
    assert any("dependency" in reason for reason in rejected)


def test_task_carries_parent_tests_and_code(demo_repo: Path):
    tasks, _ = mine(_cfg(demo_repo))
    task = next(t for t in tasks if "percentage discounts" in t.subject)

    assert task.parent, "a task without a parent commit has no starting state"
    assert task.test_files == ["tests/test_calc.py"]
    assert task.code_files == ["app/calc.py"]
    assert task.review == "pending", "mining must never approve its own tasks"
    assert task.verified == "unverified"


def test_pr_reference_is_stripped_from_the_prompt(demo_repo: Path):
    tasks, _ = mine(_cfg(demo_repo))
    task = next(t for t in tasks if "percentage discounts" in t.subject)
    assert "#42" not in task.prompt
    assert "percentage discounts" in task.prompt


def test_commits_touching_too_many_files_are_rejected(demo_repo: Path):
    tasks, rejected = mine(_cfg(demo_repo, max_files=1))
    assert tasks == []
    assert any("files" in reason for reason in rejected)


def _repo_with(tmp_path: Path, extra_file: str) -> Path:
    """A repo whose one real task also touches ``extra_file``."""
    import subprocess

    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True,
                   capture_output=True, text=True)

    def commit(message: str) -> None:
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                       capture_output=True, text=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=b", "-c", "user.email=b@e.x",
             "commit", "-q", "-m", message],
            check=True, capture_output=True, text=True,
        )

    (repo / "app" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "tests" / "test_calc.py").write_text("assert True\n")
    commit("Initial")

    (repo / "app" / "calc.py").write_text("def add(a, b):\n    return a + b + 0\n")
    (repo / "tests" / "test_calc.py").write_text("assert True  # more\n")
    target = repo / extra_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("changed\n")
    commit("Cache the computed order total")

    return repo


def test_a_lockfile_does_not_throw_the_task_away(tmp_path: Path):
    """A dependency lock in the commit is a reason to look, not to discard.

    Mining a JavaScript monorepo turned this up: a quarter of its commits that
    touched code and tests together also carried a lockfile, and rejecting the
    whole commit for it silently threw away the usable tasks. Whether the task
    actually needs an install is decided empirically by the verifier, which runs
    the tests at the commit and at its parent.
    """
    repo = _repo_with(tmp_path, "package-lock.json")
    tasks, _ = mine(_cfg(repo))

    assert [t.subject for t in tasks] == ["Cache the computed order total"]
    task = tasks[0]
    assert task.setup_risk, "the lockfile must be flagged for the human reviewer"
    assert any("package-lock.json" in h for h in task.setup_hits)
    assert "package-lock.json" not in task.code_files, (
        "a lockfile is not production code for the agent to edit"
    )


def test_a_migration_still_throws_the_task_away(tmp_path: Path):
    """Unlike a lockfile, a migration needs state no throwaway worktree has."""
    repo = _repo_with(tmp_path, "migrations/0001_add_column.py")
    tasks, rejected = mine(_cfg(repo))

    assert tasks == []
    assert any("migration" in reason for reason in rejected)


def test_clean_message_drops_trailers():
    text = clean_message(
        "Fix the thing (#7)",
        "Body line.\n\nCo-authored-by: Someone <x@y.z>\nSigned-off-by: Someone <x@y.z>",
        1200,
    )
    assert "Co-authored-by" not in text
    assert "Signed-off-by" not in text
    assert text.startswith("Fix the thing")


def test_leak_check_flags_a_message_that_hands_over_the_answer():
    hits = leak_check("Fix app/calc.py by clamping percent", ["app/calc.py"])
    assert hits
    assert any("app/calc.py" in h for h in hits)

    assert leak_check("Reject out-of-range discounts", ["app/calc.py"]) == []


def test_leak_check_flags_code_fences():
    hits = leak_check("Do this:\n```python\nreturn 1\n```", ["app/calc.py"])
    assert any("code fence" in h for h in hits)
