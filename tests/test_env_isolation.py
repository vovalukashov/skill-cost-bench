"""A sweep launched from inside an agent session must not inherit its settings."""

from __future__ import annotations

import os

from bench.agent import SCRUBBED_ENV
from bench.util import run


def test_none_removes_an_inherited_variable(monkeypatch):
    monkeypatch.setenv("CLAUDE_EFFORT", "xhigh")

    inherited = run(["/bin/sh", "-c", "echo [$CLAUDE_EFFORT]"])
    assert inherited.stdout.strip() == "[xhigh]"

    scrubbed = run(["/bin/sh", "-c", "echo [$CLAUDE_EFFORT]"], env={"CLAUDE_EFFORT": None})
    assert scrubbed.stdout.strip() == "[]"


def test_an_arm_can_still_set_a_scrubbed_variable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://inherited.example")
    proc = run(["/bin/sh", "-c", "echo [$ANTHROPIC_BASE_URL]"],
               env={"ANTHROPIC_BASE_URL": "https://on-purpose.example"})
    assert proc.stdout.strip() == "[https://on-purpose.example]"


def test_the_scrub_list_covers_what_a_host_session_exports():
    """These are the variables observed in a live Claude Code session's env."""
    for name in ("CLAUDECODE", "CLAUDE_EFFORT", "CLAUDE_CODE_ENTRYPOINT",
                 "ANTHROPIC_BASE_URL"):
        assert name in SCRUBBED_ENV


def test_the_harness_own_process_does_not_leak_an_api_key():
    """Auth is the session's, not an inherited key — assert we never plant one."""
    assert "ANTHROPIC_API_KEY" not in SCRUBBED_ENV, (
        "an API key must be set deliberately by an arm, never scrubbed silently "
        "in a way that hides which credential a run used"
    )
    assert os.environ.get("ANTHROPIC_API_KEY") in (None, "")
