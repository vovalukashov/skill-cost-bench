"""Turn real commits into agent tasks.

A task is mined from a commit that touched production code *and* tests in the
same change. The parent commit is the starting state, the commit message is the
task statement, and the commit's own tests are the grader. The tests are not
present while the agent works: the worktree sits at the parent commit, and the
post-commit version of the test files is restored only at grading time.

Nothing here is trusted blindly. Every mined task lands in the manifest with
``review: pending``; the runner only executes tasks a human has marked
``review: ok``.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from .util import run

# Commits that are not tasks, however many files they touch.
SUBJECT_SKIP = re.compile(
    r"""(?ix)
    ^\s*(revert|merge)\b
    | \bbump\b .* \bto\b
    | ^\s*chore\(deps(-dev)?\)
    | \bdependabot\b | \brenovate\b
    | ^\s*(release|v?\d+\.\d+\.\d+)\s*$
    | \bupdate\s+(the\s+)?(lock ?file|dependencies|snapshots?)\b
    | ^\s*(rename|move)\b
    """
)

# Paths that must never end up in a published manifest or in an agent prompt.
SENSITIVE_GLOBS = (
    "*.pem",
    "*.key",
    "*.p12",
    "*.keystore",
    "*.env",
    ".env*",
    "*secret*",
    "*credential*",
    "*.tfstate",
)

# Paths that make a task unreproducible in a throwaway worktree: they need state
# the worktree does not have, and no amount of agent work can conjure a database.
INFRA_GLOBS = (
    "*/migrations/*",
    "migrations/*",
    "*/alembic/*",
    "*.sql",
)

# Dependency locks. These used to sit in INFRA_GLOBS and reject the commit
# outright, which was wrong: a lockfile does not stop a task from running, it
# only means the task *may* need an install step first. On a JavaScript monorepo
# that guess threw away 9 of the 37 commits that touched code and tests together
# — a quarter of the usable history, discarded on a hunch. Whether the install is
# really needed is decided by evidence: the verifier runs the tests at the commit
# and at its parent, and a task that cannot pass in this environment is dropped
# with a reason. So the lockfile is recorded for the human reviewer and left
# alone.
LOCKFILE_GLOBS = (
    "*lock.json",
    "*.lock",
    "*lock.yaml",
    "go.sum",
    "Cargo.lock",
    "poetry.lock",
)

TRAILER = re.compile(
    r"(?im)^\s*(co-authored-by|signed-off-by|reviewed-by|refs|closes|fixes|"
    r"cherry picked from commit)\b.*$"
)
PR_REF = re.compile(r"\s*\(#\d+\)\s*$")


@dataclass
class Task:
    id: str
    commit: str
    parent: str
    date: str
    subject: str
    prompt: str
    code_files: list[str]
    test_files: list[str]
    n_files: int
    review: str = "pending"
    reject_reason: str | None = None
    leak_risk: bool = False
    leak_hits: list[str] = field(default_factory=list)
    setup_risk: bool = False
    setup_hits: list[str] = field(default_factory=list)
    verified: str = "unverified"  # unverified | ok | fails_at_commit | passes_at_parent

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MineConfig:
    repo: str
    test_globs: Sequence[str]
    code_globs: Sequence[str] = ("*",)
    since: str | None = None
    until: str | None = None
    max_tasks: int = 80
    max_files: int = 25
    min_files: int = 2
    paths: Sequence[str] = ()
    max_prompt_chars: int = 1200


def _matches(path: str, globs: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch("/" + path, g) for g in globs)


def is_test_path(path: str, test_globs: Iterable[str]) -> bool:
    return _matches(path, test_globs)


def is_sensitive(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return _matches(path, SENSITIVE_GLOBS) or _matches(name, SENSITIVE_GLOBS)


def is_infra(path: str) -> bool:
    return _matches(path, INFRA_GLOBS)


def is_lockfile(path: str) -> bool:
    return _matches(path, LOCKFILE_GLOBS)


def clean_message(subject: str, body: str, max_chars: int) -> str:
    """Strip PR refs and trailers; keep the human intent, drop the bookkeeping."""
    subject = PR_REF.sub("", subject).strip()
    body = TRAILER.sub("", body or "")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    text = subject if not body else f"{subject}\n\n{body}"
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0].rstrip() + "\n…"
    return text


def leak_check(message: str, changed_files: Sequence[str]) -> list[str]:
    """Flag messages that hand the answer to the agent.

    Two cheap signals: a fenced code block, and a literal path of a file the
    commit changed. Both are reasons for a human to read the task before
    approving it, not automatic rejections.
    """
    hits: list[str] = []
    if "```" in message:
        hits.append("code fence in message")
    for path in changed_files:
        if path and path in message:
            hits.append(f"path in message: {path}")
    stems = {Path(p).stem for p in changed_files if Path(p).stem}
    for stem in sorted(stems):
        if len(stem) > 6 and re.search(rf"\b{re.escape(stem)}\b", message):
            hits.append(f"changed-file name in message: {stem}")
    return hits[:8]


def _git(repo: str, *args: str, timeout: float = 120.0) -> str:
    proc = run(["git", "-C", repo, *args], timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:400]}")
    return proc.stdout


def iter_commits(cfg: MineConfig) -> Iterable[dict[str, Any]]:
    """Yield raw commit records (hash, date, subject, body, files) newest first.

    A commit body may contain newlines, so the file list cannot be told from the
    body by looking at the lines. The format below closes the body with an
    explicit ``\\x1e``, which makes ``raw.split("\\x1e")`` alternate
    metadata-block, file-block, metadata-block, … with no guessing.
    """
    args = [
        "log",
        "--no-merges",
        "--pretty=format:%x1e%H%x1f%P%x1f%ad%x1f%s%x1f%b%x1e",
        "--date=short",
        "--name-status",
    ]
    if cfg.since:
        args.append(f"--since={cfg.since}")
    if cfg.until:
        args.append(f"--until={cfg.until}")
    if cfg.paths:
        args.append("--")
        args.extend(cfg.paths)

    raw = _git(cfg.repo, *args, timeout=900.0)
    blocks = raw.split("\x1e")
    # blocks[0] is whatever precedes the first record separator (normally empty).
    for i in range(1, len(blocks), 2):
        meta = blocks[i]
        files_block = blocks[i + 1] if i + 1 < len(blocks) else ""
        parts = meta.split("\x1f")
        if len(parts) < 5:
            continue
        commit, parents, date, subject = parts[0], parts[1], parts[2], parts[3]
        body = "\x1f".join(parts[4:])

        # --name-status lines are "<status>\t<path>" (renames carry two paths).
        files: list[str] = []
        status: dict[str, str] = {}
        for line in files_block.splitlines():
            if not line.strip():
                continue
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            code = fields[0].strip()
            path = fields[-1].strip()
            files.append(path)
            status[path] = code[0] if code else "M"

        yield {
            "commit": commit,
            "parent": parents.split()[0] if parents.split() else "",
            "date": date,
            "subject": subject,
            "body": body.strip(),
            "files": files,
            "status": status,
        }


def classify(rec: dict[str, Any], cfg: MineConfig) -> tuple[Task | None, str | None]:
    """Return (task, None) when the commit is usable, else (None, reason)."""
    files = rec["files"]
    if not rec["parent"]:
        return None, "root commit"
    if not files:
        return None, "no files"
    if len(files) > cfg.max_files:
        return None, f"touches {len(files)} files (> {cfg.max_files})"
    if len(files) < cfg.min_files:
        return None, f"touches {len(files)} files (< {cfg.min_files})"
    if SUBJECT_SKIP.search(rec["subject"]):
        return None, "merge/revert/dependency/rename commit"

    sensitive = [f for f in files if is_sensitive(f)]
    if sensitive:
        return None, f"touches sensitive path: {sensitive[0]}"
    infra = [f for f in files if is_infra(f)]
    if infra:
        return None, f"touches migration/lockfile: {infra[0]}"

    status = rec.get("status") or {}
    locks = [f for f in files if is_lockfile(f)]
    test_files = [f for f in files if is_test_path(f, cfg.test_globs)]
    code_files = [
        f
        for f in files
        if not is_test_path(f, cfg.test_globs)
        and not is_lockfile(f)
        and _matches(f, cfg.code_globs)
    ]
    if not test_files:
        return None, "no test files"
    if not code_files:
        return None, "no production code files"

    # A commit that only deletes tests leaves the task with no grader at all:
    # restoring "the commit's tests" restores nothing, the runner finds no test
    # files, and both arms fail for a reason that has nothing to do with the
    # agent. Keep only commits that add or change at least one test.
    live_tests = [f for f in test_files if status.get(f, "M") != "D"]
    if not live_tests:
        return None, "commit only deletes tests, leaving no grader"
    test_files = live_tests

    message = clean_message(rec["subject"], rec["body"], cfg.max_prompt_chars)
    hits = leak_check(message, files)
    task = Task(
        id="",  # assigned by mine()
        commit=rec["commit"],
        parent=rec["parent"],
        date=rec["date"],
        subject=PR_REF.sub("", rec["subject"]).strip(),
        prompt=message,
        code_files=sorted(code_files),
        test_files=sorted(test_files),
        n_files=len(files),
        leak_risk=bool(hits),
        leak_hits=hits,
        setup_risk=bool(locks),
        setup_hits=[f"dependency lock changed: {f}" for f in sorted(locks)[:8]],
    )
    return task, None


def mine(cfg: MineConfig) -> tuple[list[Task], dict[str, int]]:
    """Mine tasks newest-first, returning the tasks and a histogram of rejections."""
    tasks: list[Task] = []
    rejected: dict[str, int] = {}
    for rec in iter_commits(cfg):
        task, reason = classify(rec, cfg)
        if task is None:
            key = re.sub(r"\d+", "N", reason or "unknown")
            rejected[key] = rejected.get(key, 0) + 1
            continue
        task.id = f"t{len(tasks) + 1:03d}"
        tasks.append(task)
        if len(tasks) >= cfg.max_tasks:
            break
    return tasks, rejected
