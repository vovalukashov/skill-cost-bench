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


def test_a_sweep_cannot_inherit_a_credential_from_the_shell():
    """This test used to assert the opposite, and the reversal is the point.

    The old rule was that a key must be set deliberately by an arm and never
    scrubbed, so that nobody could be confused about which credential a run
    used. The concern was right; the remedy was backwards. Refusing to scrub
    does not make the credential visible, it only makes it inherited — and a
    sweep is hundreds of sessions, so a key left in a shell moves the lot onto
    paid API billing with nothing in the output to show it.

    The credential is made visible instead: every run records `apiKeySource`
    from its own init event, which answers the original question with evidence
    rather than with an assumption about the environment.
    """
    assert "ANTHROPIC_API_KEY" in SCRUBBED_ENV, (
        "a sweep is hundreds of sessions; an inherited key would move all of them "
        "onto API billing for real money, and say nothing about it"
    )
    assert os.environ.get("ANTHROPIC_API_KEY") in (None, "")


def test_every_run_records_which_credential_paid_for_it():
    """The other half of scrubbing: say what was used, do not merely assume it."""
    from bench.transcript import summarize

    events = [
        {"type": "system", "subtype": "init", "tools": [], "mcp_servers": [],
         "slash_commands": [], "apiKeySource": "none"},
        {"type": "result", "subtype": "success", "is_error": False},
    ]
    assert summarize(events).api_key_source == "none"

    events[0]["apiKeySource"] = "ANTHROPIC_API_KEY"
    assert summarize(events).api_key_source == "ANTHROPIC_API_KEY", (
        "a run that did bill an API key has to say so in its own row"
    )
