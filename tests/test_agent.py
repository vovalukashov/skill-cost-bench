

def test_a_sweep_cannot_silently_bill_an_api_account():
    """Hundreds of sessions on a stray key is real money and a silent switch."""
    from bench.agent import SCRUBBED_ENV

    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
        assert name in SCRUBBED_ENV, f"{name} must not reach a run from the shell"


def test_an_arm_can_still_ask_for_key_based_auth(tmp_path: Path):
    """Scrubbing is a default, not a prohibition — but it has to be written down."""
    from bench.agent import invoke
    from bench.config import AgentConfig, ArmConfig

    script = tmp_path / "echo_env.sh"
    script.write_text(
        '#!/bin/sh\necho "{\\"type\\":\\"result\\",\\"subtype\\":\\"success\\",'
        '\\"is_error\\":false,\\"result\\":\\"$ANTHROPIC_API_KEY\\"}"\n',
        encoding="utf-8")
    script.chmod(0o755)

    arm = ArmConfig(name="keyed", label="K", env={"ANTHROPIC_API_KEY": "sk-declared"})
    run = invoke(AgentConfig(bin=str(script), timeout_s=30, permission_mode="",
                             model=None, effort=None),
                 arm, "hi", tmp_path, tmp_path / "t.jsonl")

    assert run.ok
    written = (tmp_path / "t.jsonl").read_text(encoding="utf-8")
    assert "sk-declared" in written, "an arm's own env still reaches the session"
