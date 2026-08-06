"""Did the skill actually run?

JetBrains found that ponytail self-activated zero times across ten sessions: it
only works when a SessionStart hook injects it. A skill that silently never runs
produces exactly the numbers of a skill that works perfectly and costs nothing,
so a benchmark that does not check activation cannot tell the two apart.

Every run in an arm that declares ``activation_patterns`` is scanned for traces
of the skill: tool calls, MCP tool names, index files it reads, markers it
prints. A run with no traces is not a zero result. It is an invalid run, and it
leaves the analysis with a recorded reason.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Sequence

from .transcript import Event, iter_text, iter_tool_uses


def _compile(patterns: Sequence[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def _haystacks(events: list[Event]) -> Iterable[tuple[str, str]]:
    """Yield (kind, text) pairs that a pattern may match against."""
    for name, payload in iter_tool_uses(events):
        yield "tool_name", name
        if payload is not None:
            try:
                yield "tool_input", json.dumps(payload, ensure_ascii=False)
            except (TypeError, ValueError):
                yield "tool_input", str(payload)
    for text in iter_text(events):
        yield "text", text


def scan(events: list[Event], patterns: Sequence[str]) -> dict[str, Any]:
    """Look for traces of the skill in a transcript.

    Returns ``activated``, per-pattern hit counts and a few short evidence
    strings, so a rejected run can be argued with rather than merely trusted.
    """
    compiled = _compile(patterns)
    hits: dict[str, int] = {p: 0 for p in patterns}
    evidence: list[str] = []
    kinds: dict[str, int] = {}

    for kind, text in _haystacks(events):
        if not text:
            continue
        for pattern, rx in zip(patterns, compiled):
            match = rx.search(text)
            if not match:
                continue
            hits[pattern] += 1
            kinds[kind] = kinds.get(kind, 0) + 1
            if len(evidence) < 5:
                start = max(0, match.start() - 40)
                evidence.append(f"{kind}: …{text[start:match.end() + 40]}…".replace("\n", " "))

    total = sum(hits.values())
    return {
        "activated": total > 0,
        "total_hits": total,
        "hits": hits,
        "hit_kinds": kinds,
        "evidence": evidence,
    }


def check_arm(
    events: list[Event],
    activation_patterns: Sequence[str] = (),
    forbidden_patterns: Sequence[str] = (),
) -> dict[str, Any]:
    """Validate one run against its arm's contract.

    ``activation_patterns`` — traces that MUST be present (experimental arm).
    ``forbidden_patterns`` — traces that must NOT be present (control arm: proof
    the skill did not leak in through a stray user- or project-level config).
    """
    out: dict[str, Any] = {"valid": True, "invalid_reason": None}

    if activation_patterns:
        res = scan(events, activation_patterns)
        out["activation"] = res
        if not res["activated"]:
            out["valid"] = False
            out["invalid_reason"] = "skill never activated"

    if forbidden_patterns:
        res = scan(events, forbidden_patterns)
        out["contamination"] = res
        if res["activated"] and out["valid"]:
            out["valid"] = False
            out["invalid_reason"] = "control arm contaminated by the skill"

    return out


def check_availability(
    summary_tools: Sequence[str],
    summary_mcp: Sequence[str],
    summary_commands: Sequence[str],
    expect_present: Sequence[str] = (),
    expect_absent: Sequence[str] = (),
) -> dict[str, Any]:
    """Check what the session was *offered*, from the stream-json init event.

    Availability is not activation: a session can be handed the skill and never
    use it. Both are recorded, and they answer different questions — whether the
    arm was configured correctly, and whether the model took the tool.
    """
    catalog = [*summary_tools, *summary_mcp, *summary_commands]
    blob = "\n".join(catalog)
    missing = [p for p in expect_present if not re.search(p, blob, re.IGNORECASE)]
    leaked = [p for p in expect_absent if re.search(p, blob, re.IGNORECASE)]
    return {
        "ok": not missing and not leaked,
        "missing": missing,
        "leaked": leaked,
        "catalog_size": len(catalog),
    }
