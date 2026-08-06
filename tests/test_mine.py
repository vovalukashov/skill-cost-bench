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
