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


def test_a_session_that_never_touched_the_skill_counts_and_is_labelled():
    """Not a zero, and not a discard either: a result in its own right."""
    events = [
        {"type": "system", "subtype": "init", "tools": ["Read"], "mcp_servers": [], "slash_commands": []},
        _assistant([{"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}]),
        {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.2},
    ]
    checks = check_arm(events, activation_patterns=PATTERNS)

    assert checks["valid"] is True
    assert checks["invalid_reason"] is None
    assert checks["activation_status"] == "available_unused"
    assert checks["activation"]["activated"] is False


def test_a_session_that_used_the_skill_is_labelled_used():
    events = [_assistant([{"type": "tool_use", "name": "mcp__graphify__query_graph", "input": {}}])]
    assert check_arm(events, activation_patterns=PATTERNS)["activation_status"] == "used"


def test_the_harness_own_path_cannot_trip_the_control_guard():
    """The first sweep failed here: the worktree was named after the experiment."""
    path = "/tmp/repo-work/graphify-superset-pilot-t018-control-3/superset/utils/core.py"
    events = [_assistant([{"type": "tool_use", "name": "Read", "input": {"file_path": path}}])]

    assert check_arm(events, forbidden_patterns=["graphify"])["valid"] is False
    stripped = check_arm(events, forbidden_patterns=["graphify"],
                         strip="/tmp/repo-work/graphify-superset-pilot-t018-control-3")
    assert stripped["valid"] is True


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


def test_searching_for_the_skill_is_not_using_it():
    """ToolSearch takes the tool's own name as its argument.

    A session that looked the skill up and then went back to grep must not score
    as a session that used it.
    """
    looked_up_only = [_assistant([
        {"type": "tool_use", "name": "ToolSearch",
         "input": {"query": "select:mcp__graphify__graph_stats", "max_results": 5}},
        {"type": "tool_use", "name": "Bash", "input": {"command": "grep -rn foo ."}},
    ])]
    assert check_arm(looked_up_only, activation_patterns=PATTERNS)["activation_status"] \
        == "available_unused"

    then_called = [_assistant([
        {"type": "tool_use", "name": "ToolSearch",
         "input": {"query": "select:mcp__graphify__graph_stats", "max_results": 5}},
        {"type": "tool_use", "name": "mcp__graphify__graph_stats", "input": {}},
    ])]
    assert check_arm(then_called, activation_patterns=PATTERNS)["activation_status"] == "used"


def test_reading_the_index_still_counts_as_using_the_skill():
    """The index file appears in a Read argument, and that is a real use."""
    events = [_assistant([
        {"type": "tool_use", "name": "Read", "input": {"file_path": "graphify-out/graph.json"}},
    ])]
    assert check_arm(events, activation_patterns=PATTERNS)["activation_status"] == "used"


def test_mentioning_the_index_in_prose_is_not_using_it():
    """Once the index sits in the tree, its path shows up in any `ls` the model echoes."""
    events = [_assistant([
        {"type": "text",
         "text": "Files here: superset/config.py graphify-out/graph.json superset/api.py"},
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
    ])]
    res = check_arm(events, activation_patterns=PATTERNS)

    assert res["activation_status"] == "available_unused"
    assert res["activation"]["mentioned_only"] is True
    assert res["activation"]["total_hits"] >= 1, "the mention is still on the record"


def test_the_control_guard_still_fires_on_a_mere_mention():
    """Contamination is about exposure, so prose counts there."""
    events = [_assistant([{"type": "text", "text": "the graphify index would help here"}])]
    assert check_arm(events, forbidden_patterns=["graphify"])["valid"] is False


def test_compliance_is_reported_against_how_much_search_the_task_left():
    from bench.analyze import collect

    rows = [
        {"arm": "b", "valid": True, "navigation": "given",
         "activation_status": "available_unused"},
        {"arm": "b", "valid": True, "navigation": "needed", "activation_status": "used"},
        {"arm": "b", "valid": True, "navigation": "needed", "activation_status": "used"},
        {"arm": "a", "valid": True},
    ]
    by_nav = collect(rows)["activation_by_navigation"]

    assert by_nav["given"] == {"used": 0, "available_unused": 1}
    assert by_nav["needed"] == {"used": 2, "available_unused": 0}
    assert "unlabelled" not in by_nav, "a run with no skill offered is not a skipped skill"


def test_a_nudge_from_the_tools_own_hook_is_counted_but_is_not_activation():
    """The hook speaks, the model answers: two different facts, both recorded.

    The stock install fires a PreToolUse hook that pushes the same sentence into
    the session before every read. Counting that as the model reaching for the
    graph would score the tool's own reminder as a decision the model made.
    """
    events = [
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "content": "MANDATORY: graphify-out/graph.json exists. "
                                               "You MUST run graphify before reading source files."},
        ]}},
        _assistant([{"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}]),
    ]
    checks = check_arm(events, activation_patterns=PATTERNS,
                       nudge_patterns=["MANDATORY: graphify-out"])

    assert checks["activation_status"] == "available_unused"
    assert checks["nudges"]["total_hits"] == 1
    assert checks["nudged"] is True


def test_a_nudged_session_that_then_used_the_graph_is_both():
    events = [
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "content": "MANDATORY: graphify-out/graph.json exists."},
        ]}},
        _assistant([{"type": "tool_use", "name": "Bash",
                     "input": {"command": "graphify query \"where is the loader\""}}]),
    ]
    checks = check_arm(events, activation_patterns=[r"graphify query"],
                       nudge_patterns=["MANDATORY: graphify-out"])

    assert checks["activation_status"] == "used"
    assert checks["nudged"] is True


def _hook(name: str, output: str) -> dict:
    """A PreToolUse hook firing, as Claude Code records it under --include-hook-events."""
    return {"type": "system", "subtype": "hook_response", "hook_name": name,
            "hook_event": "PreToolUse", "output": output, "stdout": output,
            "exit_code": 0, "outcome": "success"}


NUDGE = ('{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":'
         '"MANDATORY: graphify-out/graph.json exists. You MUST run graphify before '
         'reading source files."}}')


def test_a_hook_firing_is_read_from_the_transcript():
    """Hook output is a system event, not a message, and was invisible.

    The scanner walked assistant and user messages only, so the tool could shout
    at the model on every file read and the report would say it never spoke.
    """
    events = [
        _hook("PreToolUse:Read", NUDGE),
        _hook("PreToolUse:Bash", NUDGE),
        _assistant([{"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}]),
    ]
    res = scan(events, ["MANDATORY: graphify-out"])
    assert res["total_hits"] == 2
    assert res["hit_kinds"].get("hook") == 2


def test_a_hook_shouting_about_the_skill_is_not_the_model_using_it():
    """The whole point of counting nudges separately.

    A hook that names the tool in every reminder would otherwise mark every run
    as an activation, and the sweep would report a model that reached for the
    graph on its own when it did nothing of the kind.
    """
    events = [
        _hook("PreToolUse:Read", NUDGE),
        _assistant([{"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}]),
    ]
    checks = check_arm(events,
                       activation_patterns=[r"graphify (query|explain)"],
                       nudge_patterns=["MANDATORY: graphify-out"])
    assert checks["activation_status"] == "available_unused"
    assert checks["nudged"] is True
    assert checks["nudges"]["total_hits"] == 1


def test_the_model_answering_the_hook_still_counts_as_use():
    events = [
        _hook("PreToolUse:Read", NUDGE),
        _assistant([{"type": "tool_use", "name": "Bash",
                     "input": {"command": 'graphify query "where is the loader"'}}]),
    ]
    checks = check_arm(events,
                       activation_patterns=[r"graphify (query|explain)"],
                       nudge_patterns=["MANDATORY: graphify-out"])
    assert checks["activation_status"] == "used"
    assert checks["nudged"] is True
