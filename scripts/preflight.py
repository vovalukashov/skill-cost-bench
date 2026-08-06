#!/usr/bin/env python3
"""Cheapest possible check that both arms are what the config says they are.

Runs one trivial prompt per arm and prints what each session was handed: tools,
MCP servers, slash commands, model, and what it cost. This is the step that
catches an arm which silently has no skill, an arm which silently has all of the
machine's skills, or an authentication problem — before a sweep spends real money
discovering the same thing.

    python3 scripts/preflight.py --config config.yaml
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench import config as config_mod  # noqa: E402
from bench.activation import check_availability  # noqa: E402
from bench.agent import invoke  # noqa: E402
from bench.transcript import load, result_event  # noqa: E402

PROMPT = "Reply with the single word: ready. Do not use any tools."


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--out", default=None, help="where to keep the two transcripts")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg_path = Path(args.config).resolve()
    cfg = config_mod.resolve_paths(config_mod.load(cfg_path), cfg_path.parent)

    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="preflight-"))
    out.mkdir(parents=True, exist_ok=True)

    total = 0.0
    failures = 0
    auth_broken = False
    for arm in cfg.arms:
        run = invoke(cfg.agent, arm, PROMPT, cfg_path.parent, out / f"{arm.name}.jsonl")
        s = run.summary
        avail = check_availability(
            s.get("tools", []), s.get("mcp_servers", []), s.get("slash_commands", []),
            arm.expect_present, arm.expect_absent,
        )
        total += float(s.get("cost_usd") or 0.0)

        print(f"\n=== arm {arm.name} ===")
        print(f"  exit: {run.returncode}  ok: {run.ok}  wall: {run.wall_s}s")
        print(f"  model: {s.get('model')}  cost: ${s.get('cost_usd')}")
        print(f"  tools: {len(s.get('tools', []))}")
        print(f"  mcp servers: {s.get('mcp_servers') or '—'}")
        commands = s.get("slash_commands") or []
        print(f"  slash commands ({len(commands)}): {', '.join(commands[:12])}"
              f"{' …' if len(commands) > 12 else ''}")
        print(f"  arm contract: {'OK' if avail['ok'] else 'FAILED'}")
        if not avail["ok"]:
            failures += 1
            if avail["missing"]:
                print(f"    missing (expected present): {avail['missing']}")
            if avail["leaked"]:
                print(f"    leaked (expected absent): {avail['leaked']}")
        if not run.ok:
            failures += 1
            events = load(out / f"{arm.name}.jsonl")
            text = str((result_event(events) or {}).get("result", ""))
            print(f"    result: {text[:200]}")
            print(f"    stderr: {run.stderr_tail[:300]}")
            if "not logged in" in text.lower() or "authenticate" in text.lower():
                auth_broken = True

    print(f"\ntranscripts: {out}")
    print(f"preflight spend: ${total:.4f}")
    if auth_broken:
        print("\nThe CLI is not authenticated. A sweep would produce nothing but "
              "zero-token errors, quickly and convincingly. Run `claude` "
              "interactively and /login first.")
    elif failures:
        print("\nDO NOT START THE SWEEP: the arms are not what the config claims.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
