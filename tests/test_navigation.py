"""A task that names its own location leaves the graph nothing to find."""

from __future__ import annotations

import subprocess
from pathlib import Path

from bench.navigation import classify, terms


def test_terms_keep_the_words_worth_grepping():
    got = terms("fix(mcp): reject unknown fields in nested chart-config models")
    assert "unknown" in got or "nested" in got
    assert "fix" not in got, "a conventional-commit prefix is not a search term"
    assert all(len(w) >= 5 for w in got)


def test_terms_are_deduplicated_and_longest_first():
    got = terms("SHOW_STACKTRACE gate SHOW_STACKTRACE behind exception_type")
    assert got == sorted(set(got), key=lambda w: -len(w))


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "r"
    (root / "app").mkdir(parents=True)
    (root / "app" / "billing.py").write_text(
        "def apply_prorated_discount(amount):\n    return amount\n", encoding="utf-8")
    (root / "app" / "views.py").write_text("def index():\n    return 1\n", encoding="utf-8")
    for i in range(6):
        (root / "app" / f"common{i}.py").write_text("SHARED = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@e.x",
                    "commit", "-q", "-m", "init"], check=True, capture_output=True)
    return root


def test_a_task_naming_the_symbol_has_its_navigation_given(tmp_path: Path):
    root = _repo(tmp_path)
    nav = classify(str(root), "HEAD",
                   "fix(billing): round apply_prorated_discount to two places",
                   ["app/billing.py"])

    assert nav.label == "given"
    assert nav.hit_term == "apply_prorated_discount"
    assert nav.hit_files == 1


def test_a_task_describing_only_the_symptom_leaves_the_search(tmp_path: Path):
    root = _repo(tmp_path)
    nav = classify(str(root), "HEAD",
                   "fix: customers on annual plans are charged twice in their first month",
                   ["app/billing.py"])

    assert nav.label == "needed"
    assert nav.hit_term is None
    assert nav.checked, "the terms it tried are on the record"


def test_a_term_matching_half_the_repository_is_no_shortcut(tmp_path: Path):
    root = _repo(tmp_path)
    nav = classify(str(root), "HEAD", "adjust SHARED constant handling", ["app/billing.py"],
                   max_files=5)

    assert nav.label == "needed", "a word in six files has not located anything"
