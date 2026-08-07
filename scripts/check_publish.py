#!/usr/bin/env python3
"""Refuse to publish anything derived from a private repository.

Measuring on a codebase you may not redistribute is fine. Publishing the task
manifest, the transcripts or the run directory from that codebase is not: the
manifest carries its commit messages and file paths, and the transcripts carry
its source.

Good intentions do not survive a late night and a `git push`, so this is a gate:

    python3 scripts/check_publish.py            # exits non-zero on any hit

It reads `.private-sources.yaml`, which is deliberately NOT in the repository —
the list of private sources would itself be a disclosure. If that file is
missing the check FAILS. Failing closed is the whole point: a guard that passes
when its configuration is absent is not a guard.

Install it as a pre-push hook so it runs whether or not anyone remembers:

    git config core.hooksPath .githooks
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

CONFIG_NAME = ".private-sources.yaml"
NEVER_TRACKED = ("tasks/", "out/", ".targets/", ".arms/", "drafts/")

# A task manifest carries commit messages and file paths out of whatever
# repository it was mined from, which is why `tasks/` is banned outright. But
# results from a public target are worth publishing, and copying a manifest to
# another directory walks straight around that ban — so a tracked manifest has
# to say, in itself, where it came from and that the source is public.
MANIFEST_SUFFIX = ".tasks.yaml"
PUBLIC_SOURCE_KEY = "public_source"


def repo_root() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print("not inside a git repository", file=sys.stderr)
        raise SystemExit(2)
    return Path(out.stdout.strip())


def load_config(root: Path) -> dict[str, Any]:
    path = root / CONFIG_NAME
    if not path.exists():
        print(f"FAIL: {CONFIG_NAME} is missing.", file=sys.stderr)
        print(f"      Copy {CONFIG_NAME.replace('.yaml', '.example.yaml')} to "
              f"{CONFIG_NAME} and list the private sources.", file=sys.stderr)
        print("      This check fails closed: no list, no publishing.", file=sys.stderr)
        raise SystemExit(2)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        print(f"FAIL: {CONFIG_NAME} must be a mapping", file=sys.stderr)
        raise SystemExit(2)
    return data


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "ls-files"],
                         capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line.strip()]


def scan(root: Path, cfg: dict[str, Any]) -> list[str]:
    literals = [str(s) for s in cfg.get("literals", []) if str(s).strip()]
    patterns = [re.compile(str(p), re.IGNORECASE) for p in cfg.get("patterns", [])]
    paths = [str(p) for p in cfg.get("paths", []) if str(p).strip()]

    problems: list[str] = []
    files = tracked_files(root)

    for rel in files:
        for prefix in NEVER_TRACKED:
            if rel.startswith(prefix):
                problems.append(
                    f"{rel}: lives under {prefix} and must never be tracked — "
                    "that is where measured source and commit messages land"
                )

    for rel in files:
        if not rel.endswith(MANIFEST_SUFFIX) or rel.startswith("tasks/"):
            continue
        try:
            doc = yaml.safe_load((root / rel).read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError, UnicodeDecodeError):
            problems.append(f"{rel}: is a task manifest and could not be read to "
                            "check where it came from")
            continue
        source = doc.get(PUBLIC_SOURCE_KEY) if isinstance(doc, dict) else None
        if not (isinstance(source, str) and source.startswith("https://")):
            problems.append(
                f"{rel}: a tracked task manifest must carry `{PUBLIC_SOURCE_KEY}:` "
                "with the https URL of the public repository it was mined from. "
                "Without it there is nothing stopping a private repository's "
                "commit messages from being published under a different path"
            )

    haystack_targets = [f for f in files if not f.startswith(".git")]
    for rel in haystack_targets:
        p = root / rel
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lowered = text.lower()
        for literal in literals:
            if literal.lower() in lowered:
                line = next(
                    (i + 1 for i, ln in enumerate(text.splitlines())
                     if literal.lower() in ln.lower()), 0
                )
                problems.append(f"{rel}:{line}: contains private marker {literal!r}")
        for rx in patterns:
            match = rx.search(text)
            if match:
                problems.append(f"{rel}: matches private pattern /{rx.pattern}/ "
                                f"at {match.group(0)[:60]!r}")
        for private_path in paths:
            if private_path in text:
                problems.append(f"{rel}: contains a path into a private source "
                                f"({private_path})")

    remotes = subprocess.run(["git", "-C", str(root), "remote", "-v"],
                             capture_output=True, text=True).stdout
    for literal in literals:
        if literal.lower() in remotes.lower():
            problems.append(f"git remote points at a private source ({literal})")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    root = repo_root()
    cfg = load_config(root)
    problems = scan(root, cfg)

    if problems:
        print(f"BLOCKED: {len(problems)} problem(s) — private material would be "
              f"published:\n", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print("\nNothing was pushed.", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"clean: {len(tracked_files(root))} tracked files carry no marker "
              f"from any private source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
