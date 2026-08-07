"""Reading a Claude Code ``--output-format stream-json`` transcript.

Two things are pulled out of it: what the session was actually given (the
``system``/``init`` event lists tools, MCP servers and slash commands), and what
it cost (the final ``result`` event carries usage, cost and turns).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

Event = dict[str, Any]


def load(path: str | Path) -> list[Event]:
    events: list[Event] = []
    p = Path(path)
    if not p.exists():
        return events
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def init_event(events: Iterable[Event]) -> Event | None:
    for ev in events:
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            return ev
    return None


def result_event(events: Iterable[Event]) -> Event | None:
    found = None
    for ev in events:
        if ev.get("type") == "result":
            found = ev
    return found


def iter_tool_uses(events: Iterable[Event]) -> Iterable[tuple[str, Any]]:
    """Yield (tool_name, tool_input) for every tool call in the transcript."""
    for ev in events:
        message = ev.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield str(block.get("name", "")), block.get("input")


def iter_text(events: Iterable[Event]) -> Iterable[str]:
    for ev in events:
        message = ev.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            yield content
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in ("text", "thinking") and isinstance(
                block.get("text") or block.get("thinking"), str
            ):
                yield block.get("text") or block.get("thinking") or ""
            elif block.get("type") == "tool_result":
                inner = block.get("content")
                if isinstance(inner, str):
                    yield inner
                elif isinstance(inner, list):
                    for part in inner:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            yield part["text"]


@dataclass
class SessionSummary:
    session_id: str | None
    subtype: str | None
    is_error: bool
    num_turns: int | None
    duration_ms: int | None
    duration_api_ms: int | None
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    cache_creation_tokens: int | None
    cache_read_tokens: int | None
    total_tokens: int | None
    model: str | None
    tools: list[str]
    mcp_servers: list[str]
    slash_commands: list[str]
    # Which credential paid for the session. Runs scrub inherited keys so a sweep
    # cannot silently move onto API billing, and recording this is the other half
    # of that: the credential is on the record rather than assumed.
    api_key_source: str | None
    # The raw usage block is kept so cost can be recomputed at any price table,
    # including the per-TTL cache-write split the summary fields flatten away.
    usage: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def summarize(events: list[Event]) -> SessionSummary:
    init = init_event(events) or {}
    res = result_event(events) or {}
    usage = res.get("usage") if isinstance(res.get("usage"), dict) else {}

    inp = _int(usage.get("input_tokens"))
    out = _int(usage.get("output_tokens"))
    cc = _int(usage.get("cache_creation_input_tokens"))
    cr = _int(usage.get("cache_read_input_tokens"))
    total = sum(v for v in (inp, out, cc, cr) if v is not None) or None

    mcp = init.get("mcp_servers")
    if isinstance(mcp, list):
        mcp_names = [
            m.get("name", "") if isinstance(m, dict) else str(m) for m in mcp
        ]
    else:
        mcp_names = []

    return SessionSummary(
        session_id=res.get("session_id") or init.get("session_id"),
        subtype=res.get("subtype"),
        is_error=bool(res.get("is_error")),
        num_turns=_int(res.get("num_turns")),
        duration_ms=_int(res.get("duration_ms")),
        duration_api_ms=_int(res.get("duration_api_ms")),
        cost_usd=float(res["total_cost_usd"]) if isinstance(res.get("total_cost_usd"), (int, float)) else None,
        input_tokens=inp,
        output_tokens=out,
        cache_creation_tokens=cc,
        cache_read_tokens=cr,
        total_tokens=total,
        model=init.get("model") or res.get("model"),
        tools=[str(t) for t in init.get("tools", []) if isinstance(init.get("tools"), list)],
        mcp_servers=[n for n in mcp_names if n],
        slash_commands=[str(c) for c in init.get("slash_commands", [])
                        if isinstance(init.get("slash_commands"), list)],
        api_key_source=init.get("apiKeySource"),
        usage=dict(usage),
    )
