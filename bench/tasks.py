"""Reading and writing the task manifest.

The manifest is the contract between mining and running. Mining only ever writes
``review: pending``; the runner only ever executes ``review: ok``. Nothing
promotes a task automatically, because the one failure mode that mining cannot
detect is a commit message that hands over the answer, and only a human reading
it can see that.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml

from .mine import Task


def save(path: str | Path, meta: dict[str, Any], tasks: Iterable[Task | dict[str, Any]]) -> None:
    rows = [t.to_dict() if isinstance(t, Task) else dict(t) for t in tasks]
    payload = {"meta": meta, "tasks": rows}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def load(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"task manifest not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    meta = data.get("meta") or {}
    tasks = data.get("tasks") or []
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")
    return meta, tasks


def approved(tasks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in tasks if t.get("review") == "ok"]


def counts(tasks: Iterable[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in tasks:
        key = str(t.get("review", "pending"))
        out[key] = out.get(key, 0) + 1
    return out
