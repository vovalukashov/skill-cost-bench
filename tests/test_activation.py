from __future__ import annotations

from bench.activation import check_arm, check_availability, scan

PATTERNS = ["mcp__graphify__", r"graphify-out/graph\.json", r"(?m)^/graphify\b"]


def _assistant(content: list[dict]) -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "content": content}}


def test_a_session_that_used_the_skill_is_detected():
    events = [
        {"type": "system", "subtype": "init", "tools": ["Read"], "mcp_servers": [], "slash_commands": []},
        _assistant([{"type": "tool_use", "name": "mcp__graphify__query_graph", "input": {"q": "x"}}]),
        {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.2},
    ]
    result = scan(events, PATTERNS)
    assert result["activated"]
    assert result["total_hits"] >= 1
    assert result["evidence"]


def test_a_session_that_never_touched_the_skill_is_invalid_not_zero():
    events = [
        {"type": "system", "subtype": "init", "tools": ["Read"], "mcp_servers": [], "slash_commands": []},
        _assistant([{"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}]),
        {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.2},
    ]
    checks = check_arm(events, activation_patterns=PATTERNS)

    assert checks["valid"] is False
    assert checks["invalid_reason"] == "skill never activated"
    assert checks["activation"]["activated"] is False


def test_the_control_arm_is_rejected_when_the_skill_leaks_in():
    events = [_assistant([{"type": "tool_use", "name": "mcp__graphify__explain_node", "input": {}}])]
    checks = check_arm(events, forbidden_patterns=["graphify"])

    assert checks["valid"] is False
    assert "contaminated" in checks["invalid_reason"]


def test_a_clean_control_arm_passes():
    events = [_assistant([{"type": "tool_use", "name": "Grep", "input": {"pattern": "discount"}}])]
    assert check_arm(events, forbidden_patterns=["graphify"])["valid"] is True


def test_index_reads_count_as_activation_even_without_a_tool_call():
    events = [
        _assistant([{"type": "tool_use", "name": "Read",
                     "input": {"file_path": "graphify-out/graph.json"}}])
    ]
    assert scan(events, PATTERNS)["activated"]


def test_availability_is_separate_from_activation():
    ok = check_availability(["Read"], ["graphify"], ["/graphify"], expect_present=["graphify"])
    assert ok["ok"]

    missing = check_availability(["Read"], [], [], expect_present=["graphify"])
    assert not missing["ok"]
    assert missing["missing"] == ["graphify"]

    leaked = check_availability(["Read"], ["graphify"], [], expect_absent=["graphify"])
    assert not leaked["ok"]
    assert leaked["leaked"] == ["graphify"]
