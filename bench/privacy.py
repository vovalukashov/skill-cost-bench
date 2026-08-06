"""Marking the output of a private source, at the moment it is produced.

The publish gate (``scripts/check_publish.py``) is the last line. This is the
first one: when tasks are mined from a repository on the private list, the
manifest says so, and every run directory built from that manifest gets a
``PRIVATE_DO_NOT_PUBLISH`` file. A directory that has to be checked against a
list before it can be shared is worse than a directory that says what it is.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

CONFIG_NAME = ".private-sources.yaml"
MARKER_NAME = "PRIVATE_DO_NOT_PUBLISH"

MARKER_TEXT = """This directory was produced from a repository on the private
sources list ({source}).

It contains commit messages, file paths and source code from that repository.
Do not publish it, do not commit it, and do not attach it to an article. Publish
the aggregate report only after checking, by reading it, that no identifying
string survived.
"""


def find_config(start: str | Path) -> Path | None:
    """Look for the private-sources list in this directory and its parents."""
    current = Path(start).resolve()
    for candidate in (current, *current.parents):
        path = candidate / CONFIG_NAME
        if path.exists():
            return path
    return None


def load_rules(start: str | Path) -> dict[str, Any]:
    path = find_config(start)
    if not path:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def match_source(repo: str | Path, rules: dict[str, Any]) -> str | None:
    """Return the marker that makes ``repo`` private, or None."""
    text = str(Path(repo).resolve())
    for literal in rules.get("literals", []) or []:
        if str(literal).lower() in text.lower():
            return str(literal)
    for pattern in rules.get("patterns", []) or []:
        if re.search(str(pattern), text, re.IGNORECASE):
            return str(pattern)
    for private_path in rules.get("paths", []) or []:
        if text.startswith(str(private_path)):
            return str(private_path)
    return None


def is_private(repo: str | Path, start: str | Path | None = None) -> str | None:
    return match_source(repo, load_rules(start or Path.cwd()))


def write_marker(directory: str | Path, source: str) -> Path:
    path = Path(directory) / MARKER_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(MARKER_TEXT.format(source=source), encoding="utf-8")
    return path
