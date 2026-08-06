"""Small shared helpers: time stamps, JSONL IO, subprocess wrapper."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


def utc_stamp() -> str:
    """Compact UTC stamp used for run directories: 20260806T173012Z."""
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A truncated last line is expected when a run was killed mid-write.
                continue


def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def write_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass
class Proc:
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False


def run(
    args: Sequence[str],
    cwd: str | Path | None = None,
    env: dict[str, str | None] | None = None,
    timeout: float | None = None,
    stdin: str | None = None,
) -> Proc:
    """Run a command, capture output, never raise on a non-zero exit.

    A ``None`` value in ``env`` removes that variable from the child's
    environment rather than setting it — the only way to keep an inherited
    variable out of a subprocess.
    """
    full_env = dict(os.environ)
    for key, value in (env or {}).items():
        if value is None:
            full_env.pop(key, None)
        else:
            full_env[key] = value
    started = time.time()
    try:
        cp = subprocess.run(
            list(args),
            cwd=str(cwd) if cwd else None,
            env=full_env,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return Proc(cp.returncode, cp.stdout, cp.stderr, time.time() - started)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        return Proc(124, out, err, time.time() - started, timed_out=True)


def tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return "…(truncated)…\n" + text[-limit:]


def chunked(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
