from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HEADER = '"""Order maths."""\n\n\ndef add(a, b):\n    return a + b\n'

CALC_V1 = HEADER

CALC_V2 = HEADER + '''

def discount(total, percent):
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    return total - total * percent / 100
'''

CALC_V3 = HEADER + '''

def discount(total, percent):
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    if total < 0:
        raise ValueError("total must not be negative")
    return total - total * percent / 100
'''

CALC_V4 = HEADER + '''

def discount(total, percent):
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    if total < 0:
        raise ValueError("total must not be negative")
    return round(total - total * percent / 100, 2)
'''

PREAMBLE = '''import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.calc import add, discount

assert add(2, 3) == 5
'''

RAISES = '''

def _raises(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False
'''

TEST_V1 = '''import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.calc import add

assert add(2, 3) == 5
print("ok")
'''

TEST_V2 = PREAMBLE + RAISES + '''
assert discount(200, 10) == 180
assert _raises(discount, 200, 101)
print("ok")
'''

TEST_V3 = PREAMBLE + RAISES + '''
assert discount(200, 10) == 180
assert _raises(discount, 200, 101)
assert _raises(discount, -1, 10)
print("ok")
'''

TEST_V4 = PREAMBLE + RAISES + '''
assert discount(200, 10) == 180
assert _raises(discount, 200, 101)
assert _raises(discount, -1, 10)
assert discount(19.99, 10) == 17.99
print("ok")
'''


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    ).stdout


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=bench", "-c", "user.email=bench@example.com",
         "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").strip()


def _write(repo: Path, calc: str, tests: str) -> None:
    (repo / "app" / "calc.py").write_text(calc, encoding="utf-8")
    (repo / "tests" / "test_calc.py").write_text(tests, encoding="utf-8")


@pytest.fixture
def demo_repo(tmp_path: Path) -> Path:
    """A small repository with three minable tasks and one commit that is not one.

    Each task is additive, so the newest version of ``app/calc.py`` satisfies the
    tests of every earlier task. That lets the fake agent apply one known-good
    solution and still be graded honestly on each task's own tests.
    """
    repo = tmp_path / "demo"
    (repo / "app").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True,
                   capture_output=True, text=True)

    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    _write(repo, CALC_V1, TEST_V1)
    _commit(repo, "Initial order maths")

    _write(repo, CALC_V2, TEST_V2)
    _commit(repo, "Support percentage discounts on the order total (#42)")

    _write(repo, CALC_V3, TEST_V3)
    _commit(repo, "Reject negative order totals")

    _write(repo, CALC_V4, TEST_V4)
    _commit(repo, "Round the discounted total to cents")

    (repo / "package.json").write_text('{"name": "demo"}\n', encoding="utf-8")
    (repo / "tests" / "test_calc.py").write_text(TEST_V4 + "\n", encoding="utf-8")
    _commit(repo, "chore(deps): bump left-pad from 1.0.0 to 1.1.0")

    return repo


@pytest.fixture
def fake_agent_path() -> str:
    return str(Path(__file__).resolve().parent / "fake_agent.py")
