"""Mining has to know what a commit did to a file, not only that it touched it."""

from __future__ import annotations

import subprocess
from pathlib import Path

from bench.mine import MineConfig, classify, iter_commits, mine


def _cfg(repo: Path, **kw) -> MineConfig:
    base = dict(repo=str(repo), test_globs=["tests/*"], max_tasks=50)
    base.update(kw)
    return MineConfig(**base)


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=b", "-c", "user.email=b@e.x",
                    "commit", "-q", "-m", message], check=True, capture_output=True)


def test_status_letters_are_parsed(demo_repo: Path):
    records = list(iter_commits(_cfg(demo_repo)))
    latest = records[0]
    assert latest["status"], "every record carries a status per path"
    assert set(latest["status"].values()) <= set("AMDRCTU")


def test_a_commit_that_only_deletes_tests_is_not_a_task(demo_repo: Path):
    """Restoring "the commit's tests" would restore nothing and fail both arms."""
    (demo_repo / "app" / "extra.py").write_text("VALUE = 1\n", encoding="utf-8")
    (demo_repo / "tests" / "test_extra.py").write_text("print('ok')\n", encoding="utf-8")
    _commit(demo_repo, "Add an extra module with its test")

    (demo_repo / "tests" / "test_extra.py").unlink()
    (demo_repo / "app" / "extra.py").write_text("VALUE = 2\n", encoding="utf-8")
    _commit(demo_repo, "Drop the extra test and bump the value")

    tasks, rejected = mine(_cfg(demo_repo))
    subjects = [t.subject for t in tasks]

    assert "Drop the extra test and bump the value" not in subjects
    assert any("only deletes tests" in reason for reason in rejected)


def test_a_commit_that_adds_and_deletes_tests_keeps_only_the_live_ones(demo_repo: Path):
    (demo_repo / "app" / "extra.py").write_text("VALUE = 1\n", encoding="utf-8")
    (demo_repo / "tests" / "test_old.py").write_text("print('ok')\n", encoding="utf-8")
    _commit(demo_repo, "Add a module with an old test")

    (demo_repo / "tests" / "test_old.py").unlink()
    (demo_repo / "tests" / "test_new.py").write_text("print('ok')\n", encoding="utf-8")
    (demo_repo / "app" / "extra.py").write_text("VALUE = 2\n", encoding="utf-8")
    _commit(demo_repo, "Replace the old test with a better one")

    tasks, _ = mine(_cfg(demo_repo))
    task = next(t for t in tasks if t.subject.startswith("Replace the old test"))

    assert task.test_files == ["tests/test_new.py"]
    assert "tests/test_old.py" not in task.test_files


def test_classify_rejects_a_delete_only_record_directly():
    record = {
        "commit": "a" * 40,
        "parent": "b" * 40,
        "date": "2026-01-01",
        "subject": "Remove the feature and its tests",
        "body": "",
        "files": ["app/x.py", "tests/test_x.py"],
        "status": {"app/x.py": "M", "tests/test_x.py": "D"},
    }
    task, reason = classify(record, MineConfig(repo=".", test_globs=["tests/*"]))
    assert task is None
    assert "only deletes tests" in reason
