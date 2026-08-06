#!/usr/bin/env python3
"""A stand-in for the agent binary.

Emits the same stream-json event shapes Claude Code emits, edits files in the
worktree, and reports a cost. That is enough to exercise the whole pipeline —
worktrees, hidden tests, activation scanning, grading, resume, budget cap — for
free, which is the only way to know the harness works before it starts spending.

Behaviour comes from the environment so the runner can stay unaware it is fake:

    FAKE_AGENT_WRITE      JSON {relative path: file content} to write
    FAKE_AGENT_SOLVE      "1" to write those files, "0" to leave the tree alone
    FAKE_AGENT_ACTIVATE   "1" to emit a tool call that looks like the skill running
    FAKE_AGENT_COST       base cost in USD
    FAKE_AGENT_JITTER     multiplicative noise, log-normal sigma
    FAKE_AGENT_TOOLS      comma-separated tool names for the init event
    FAKE_AGENT_MCP        comma-separated MCP server names
    FAKE_AGENT_COMMANDS   comma-separated slash commands
    FAKE_AGENT_ERROR      "1" to finish with an error result
    FAKE_AGENT_SEED       seed for the jitter
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import uuid
from pathlib import Path


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")


def env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def main() -> int:
    argv = sys.argv[1:]
    session_id = str(uuid.uuid4())
    prompt = ""
    for i, arg in enumerate(argv):
        if arg == "--session-id" and i + 1 < len(argv):
            session_id = argv[i + 1]
        if arg in ("-p", "--print") and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            prompt = argv[i + 1]

    tools = env_list("FAKE_AGENT_TOOLS") or ["Read", "Edit", "Bash"]
    mcp = env_list("FAKE_AGENT_MCP")
    commands = env_list("FAKE_AGENT_COMMANDS")

    emit({
        "type": "system",
        "subtype": "init",
        "session_id": session_id,
        "model": os.environ.get("FAKE_AGENT_MODEL", "fake-model"),
        "tools": tools,
        "mcp_servers": [{"name": name, "status": "connected"} for name in mcp],
        "slash_commands": commands,
        "cwd": os.getcwd(),
    })

    activate = os.environ.get("FAKE_AGENT_ACTIVATE", "0")
    if activate == "alternate":
        # Every second run is dead, which is what the activation check exists for.
        counter_path = Path(os.environ.get("FAKE_AGENT_COUNTER", ".fake-agent-counter"))
        seen = int(counter_path.read_text()) if counter_path.exists() else 0
        counter_path.write_text(str(seen + 1))
        activate = "1" if seen % 2 == 0 else "0"

    if activate == "1":
        emit({
            "type": "assistant",
            "session_id": session_id,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Querying the code graph before touching files."},
                    {
                        "type": "tool_use",
                        "id": "toolu_fake_1",
                        "name": "mcp__graphify__query_graph",
                        "input": {"query": "callers of the function in question",
                                  "index": "graphify-out/graph.json"},
                    },
                ],
            },
        })

    wrote: list[str] = []
    if os.environ.get("FAKE_AGENT_SOLVE", "1") == "1":
        payload = json.loads(os.environ.get("FAKE_AGENT_WRITE", "{}"))
        for rel, content in payload.items():
            target = Path(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            wrote.append(rel)

    emit({
        "type": "assistant",
        "session_id": session_id,
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": f"Prompt seen: {prompt[:60]}"},
                {
                    "type": "tool_use",
                    "id": "toolu_fake_2",
                    "name": "Edit",
                    "input": {"file_path": wrote[0] if wrote else "none", "new_string": "…"},
                },
            ],
        },
    })

    base = float(os.environ.get("FAKE_AGENT_COST", "0.10"))
    sigma = float(os.environ.get("FAKE_AGENT_JITTER", "0"))
    seed = os.environ.get("FAKE_AGENT_SEED")
    rng = random.Random(seed if seed is not None else session_id)
    cost = base * (math.exp(rng.gauss(0, sigma)) if sigma > 0 else 1.0)

    is_error = os.environ.get("FAKE_AGENT_ERROR") == "1"
    emit({
        "type": "result",
        "subtype": "error_during_execution" if is_error else "success",
        "is_error": is_error,
        "session_id": session_id,
        "num_turns": 3,
        "duration_ms": 1000,
        "duration_api_ms": 800,
        "total_cost_usd": round(cost, 6),
        "usage": {
            "input_tokens": int(2000 * cost / max(base, 1e-9)),
            "output_tokens": int(500 * cost / max(base, 1e-9)),
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": int(10000 * cost / max(base, 1e-9)),
        },
        "result": "done",
    })
    return 1 if is_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
