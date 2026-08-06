from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from bench.grade import build_command, grade
from bench.mine import MineConfig, mine
from bench.worktree import hide_paths, worktree

TEST_CMD = "python3 {tests}"


def _task(repo: Path) -> dict:
    tasks, _ = mine(MineConfig(repo=str(repo), test_globs=["tests/*"], max_tasks=50))
    return next(t for t in tasks if "percentage discounts" in t.subject).to_dict()


def test_build_command_quotes_test_paths():
    argv = build_command("pytest -q {tests}", ["tests/a b.py", "tests/c.py"])
    assert argv[:2] == ["/bin/sh", "-lc"]
    assert "'tests/a b.py'" in argv[2]


def test_a_worktree_is_removed_and_the_repo_is_untouched(demo_repo: Path, tmp_path: Path):
    task = _task(demo_repo)
    before = subprocess.run(["git", "-C", str(demo_repo), "status", "--porcelain"],
                            capture_output=True, text=True).stdout

    path = tmp_path / "wt"
    with worktree(demo_repo, task["parent"], path) as wt:
        assert (wt / "app" / "calc.py").exists()
        (wt / "scratch.txt").write_text("noise", encoding="utf-8")
    assert not path.exists()

    after = subprocess.run(["git", "-C", str(demo_repo), "status", "--porcelain"],
                           capture_output=True, text=True).stdout
    assert before == after


def test_hidden_tests_are_gone_while_the_agent_works(demo_repo: Path, tmp_path: Path):
    task = _task(demo_repo)
    with worktree(demo_repo, task["parent"], tmp_path / "wt") as wt:
        hide_paths(wt, task["test_files"])
        assert not (wt / "tests" / "test_calc.py").exists()
        assert (wt / "app" / "calc.py").exists()


def test_an_untouched_tree_fails_grading(demo_repo: Path, tmp_path: Path):
    task = _task(demo_repo)
    with worktree(demo_repo, task["parent"], tmp_path / "wt") as wt:
        hide_paths(wt, task["test_files"])
        result = grade(demo_repo, wt, task["commit"], task["test_files"], TEST_CMD, timeout=60)

    assert result.passed is False
    assert result.restored == ["tests/test_calc.py"]


def test_the_real_fix_passes_grading(demo_repo: Path, tmp_path: Path):
    task = _task(demo_repo)
    solution = subprocess.run(
        ["git", "-C", str(demo_repo), "show", f"{task['commit']}:app/calc.py"],
        capture_output=True, text=True, check=True,
    ).stdout

    with worktree(demo_repo, task["parent"], tmp_path / "wt") as wt:
        hide_paths(wt, task["test_files"])
        (wt / "app" / "calc.py").write_text(solution, encoding="utf-8")
        result = grade(demo_repo, wt, task["commit"], task["test_files"], TEST_CMD, timeout=60)

    assert result.passed is True


def test_a_tree_that_only_deletes_the_tests_still_fails(demo_repo: Path, tmp_path: Path):
    """Grading restores the tests, so deleting them cannot buy a pass."""
    task = _task(demo_repo)
    with worktree(demo_repo, task["parent"], tmp_path / "wt") as wt:
        hide_paths(wt, task["test_files"])
        (wt / "tests").mkdir(exist_ok=True)
        (wt / "tests" / "test_calc.py").write_text("print('ok')\n", encoding="utf-8")
        result = grade(demo_repo, wt, task["commit"], task["test_files"], TEST_CMD, timeout=60)

    assert result.passed is False


def test_a_stale_worktree_registration_does_not_block_the_next_run(demo_repo: Path,
                                                                   tmp_path: Path):
    """A hard kill leaves the path registered; the next run must reclaim it."""
    task = _task(demo_repo)
    path = tmp_path / "wt"

    subprocess.run(["git", "-C", str(demo_repo), "worktree", "add", "--detach",
                    str(path), task["parent"]], check=True, capture_output=True)
    shutil.rmtree(path)  # the directory is gone, the registration is not

    with worktree(demo_repo, task["parent"], path) as wt:
        assert (wt / "app" / "calc.py").exists()
