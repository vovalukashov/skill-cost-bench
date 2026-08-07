"""How much locating work does a task actually leave?

A commit message is written by someone who already knew the answer, and some of
them name the place: "use CAST(DATE({col}) AS DATETIME) in MySQL HOUR time
grain" is a patch, not a ticket. On such a task there is no navigation to do,
and navigation is the entire mechanism a code graph claims to accelerate. Tasks
like that quietly bias a graph benchmark *against* the graph, which matters most
when the result is "it does not help".

The test used here is the control arm's own strategy: take the distinctive words
out of the task text and grep the repository at the starting commit. If one of
them lands on the file that has to change, and lands on few enough files to read
them all, then the task handed over the location and the graph had nothing to
find.

The label is not a filter. Both kinds go into the run, and the analysis reports
them apart, because "does the graph help when there is searching to do" is a
sharper question than the average over both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Sequence

from .util import run

# Words that are distinctive in prose but useless as a search term in a codebase.
STOPWORDS = frozenset("""
about above after again against because before being below between both during
each few from further having into itself more most other over same some such
than that their them then there these they this those through under until very
were what when where which while with would
fix fixes fixed feat chore refactor test tests docs revert bump
add adds added allow allows avoid catch check correct dont doesnt drop enable
ensure error errors handle handles instead keep make makes prevent remove
report reports return returns show shows skip stop support supports throw update
updates use uses using wrap wraps
""".split())

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{4,}")


def terms(text: str, limit: int = 12) -> list[str]:
    """Distinctive words a person would grep for, longest first."""
    seen: dict[str, None] = {}
    for match in IDENTIFIER.finditer(text):
        word = match.group(0)
        if word.lower() in STOPWORDS:
            continue
        seen.setdefault(word, None)
    return sorted(seen, key=lambda w: -len(w))[:limit]


@dataclass
class Navigation:
    label: str                  # "given" or "needed"
    hit_term: str | None        # the word that gave it away
    hit_files: int              # how many files that word matches
    checked: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify(repo: str, commit: str, prompt: str, code_files: Sequence[str],
             max_files: int = 5, timeout: float = 60.0) -> Navigation:
    """Does grepping the task's own words land on the code that must change?

    ``max_files`` is the point at which a match stops being a shortcut: a term
    that hits fifty files tells the agent no more than the repository layout
    does. A term that hits three, one of them the file to edit, has done the
    search already.
    """
    targets = {f for f in code_files if f}
    checked = terms(prompt)
    for term in checked:
        proc = run(["git", "-C", repo, "grep", "-l", "-F", "--", term, commit],
                   timeout=timeout)
        if proc.returncode != 0:
            continue
        # `git grep <rev>` prefixes every line with "<rev>:".
        files = {line.split(":", 1)[1] for line in proc.stdout.splitlines() if ":" in line}
        if not files or len(files) > max_files:
            continue
        if files & targets:
            return Navigation("given", term, len(files), checked)
    return Navigation("needed", None, 0, checked)
