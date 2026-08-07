"""Did the skill actually run?

A skill that silently never runs produces exactly the numbers of a skill that
works perfectly and costs nothing, so a benchmark that does not check activation
cannot tell the two apart. This is not a hypothetical: the first skill measured
here was reached for zero times in 36 runs, with the tools demonstrably within
reach, and only produced a number at all once the session was ordered to use it.

Every run in an arm that declares ``activation_patterns`` is scanned for traces
of the skill: tool calls, MCP tool names, index files it reads, markers it
prints. A run with no traces is recorded as ``available_unused``.

It is deliberately *not* thrown away. The first sweep threw such runs out, and
that was wrong twice over. A model that is handed a skill and declines to use it
is the single most interesting thing this harness can observe — discarding it
would delete the finding and leave an average computed only over the runs where
the skill happened to appeal. And "no trace" cannot be read at all until we know
the arm could reach the skill in the first place: an arm that was never able to
call the tool produces an identical transcript. That question is settled once per
sweep by a positive control (``probe``), not per run. Without a passing probe,
``available_unused`` means nothing and the sweep must not proceed.

What still invalidates a run is a harness fault: the control arm reaching the
skill, a misconfigured arm, a crash, a timeout.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Sequence

from .transcript import Event, iter_text, iter_tool_uses


# Tools whose arguments are tool names. Their input names a skill without using
# it, so it is read as a lookup rather than as evidence.
LOOKUP_TOOLS = frozenset({"ToolSearch"})


def _compile(patterns: Sequence[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def _haystacks(events: list[Event], strip: str | None = None) -> Iterable[tuple[str, str]]:
    """Yield (kind, text) pairs that a pattern may match against.

    ``strip`` removes a string — in practice the worktree path — before matching.
    The harness owns that path and puts it in front of the agent on every file
    operation; letting it match would make the guard fire on the harness's own
    noise rather than on anything the model did.
    """
    def clean(text: str) -> str:
        return text.replace(strip, "") if strip and text else text

    for name, payload in iter_tool_uses(events):
        yield "tool_name", clean(name)
        if payload is None:
            continue
        if name in LOOKUP_TOOLS:
            # Searching for a tool is not using it. `ToolSearch` takes the tool's
            # own name as its argument — `select:mcp__graphify__graph_stats` —
            # so counting its input would score a session that looked the skill
            # up and then thought better of it as a session that used it. The
            # call it makes afterwards, if any, is what counts.
            continue
        try:
            yield "tool_input", clean(json.dumps(payload, ensure_ascii=False))
        except (TypeError, ValueError):
            yield "tool_input", clean(str(payload))
    for text in iter_text(events):
        yield "text", clean(text)


def scan(events: list[Event], patterns: Sequence[str], strip: str | None = None) -> dict[str, Any]:
    """Look for traces of the skill in a transcript.

    Returns ``activated``, per-pattern hit counts and a few short evidence
    strings, so a rejected run can be argued with rather than merely trusted.
    """
    compiled = _compile(patterns)
    hits: dict[str, int] = {p: 0 for p in patterns}
    evidence: list[str] = []
    kinds: dict[str, int] = {}

    for kind, text in _haystacks(events, strip):
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
    # Talking about the skill is not using it. Once the index sits in the working
    # copy, its path turns up in any directory listing the model echoes back, and
    # a run that only ever ran `ls` was scoring as a run that queried the graph.
    # Use is a tool call: the name of a tool, or the arguments it was called with.
    by_call = sum(count for kind, count in kinds.items() if kind != "text")
    return {
        "activated": by_call > 0,
        "total_hits": total,
        "hits": hits,
        "hit_kinds": kinds,
        "mentioned_only": total > 0 and by_call == 0,
        "evidence": evidence,
    }


def check_arm(
    events: list[Event],
    activation_patterns: Sequence[str] = (),
    forbidden_patterns: Sequence[str] = (),
    strip: str | None = None,
) -> dict[str, Any]:
    """Validate one run against its arm's contract.

    ``activation_patterns`` — traces of the skill (experimental arm). Their
    absence is reported as ``available_unused``, not as an invalid run; see the
    module docstring for why, and for the positive control that has to pass
    before the label can be believed.
    ``forbidden_patterns`` — traces that must NOT be present (control arm: proof
    the skill did not leak in through a stray user- or project-level config).
    """
    out: dict[str, Any] = {"valid": True, "invalid_reason": None}

    if activation_patterns:
        res = scan(events, activation_patterns, strip)
        out["activation"] = res
        out["activation_status"] = "used" if res["activated"] else "available_unused"

    if forbidden_patterns:
        res = scan(events, forbidden_patterns, strip)
        out["contamination"] = res
        # Asymmetric on purpose. Activation asks whether the model *used* the
        # skill, so only a tool call counts. Contamination asks whether the
        # control arm was exposed to it at all, and a mention in prose already
        # answers that: it cannot write about a graph it was never shown.
        if res["total_hits"] > 0 and out["valid"]:
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

    Read this one narrowly. The init event is emitted before MCP servers finish
    connecting, so an MCP-backed skill is listed there with status `pending` and
    contributes no tools to the catalog — measured on a 104MB graph and on a
    one-node graph alike, so it is a property of the headless session, not of the
    index. Passing this check means the arm was *configured* as declared. Whether
    the model could reach the tool is a separate question, and only the positive
    control answers it.
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
