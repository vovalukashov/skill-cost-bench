"""The positive control: can this arm reach its skill at all?

Without this, "the model never used the skill" is unreadable. It is the same
transcript whether the model looked at the tool and declined it or the tool was
never truly there, and the first sweep produced exactly that ambiguity: the
graphify arm called nothing, and the reason turned out to be the harness.

So once per sweep, before any task runs, each arm that declares activation
patterns is given a worktree with the index in it and told, in as many words, to
call the tool and report what it returned. If the transcript then contains no
trace of the skill, the arm is broken and the sweep must not start. If it does,
every later run that shows no trace is the model's own choice, and that is a
finding worth publishing.

The probe is deliberately blunt where the task prompt is silent: it names the
tool and demands a result. It measures reachability, not appeal.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from . import index as index_mod
from .activation import scan
from .agent import invoke
from .config import ArmConfig, Config
from .transcript import load
from .util import utc_iso
from .worktree import worktree

PROMPT = """Use the skill described in your instructions, right now, on this checkout.

Call one of its tools and report, in one line, what it returned. If a tool's
schema is not loaded, load it first. If you cannot call any of them, say exactly
what stopped you.

Do not read source files and do not answer from memory. The only thing being
checked here is whether the tool works."""


@dataclass
class ProbeResult:
    arm: str
    reachable: bool
    detail: str
    wall_s: float
    cost_reported_usd: float | None
    transcript_path: str
    checked_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def probe_arm(cfg: Config, arm: ArmConfig, commit: str, index_source: Path | None,
              transcript_dir: Path) -> ProbeResult:
    tmp = Path(tempfile.mkdtemp(prefix="probe-"))
    transcript = Path(transcript_dir) / f"probe__{arm.name}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)

    with worktree(cfg.target.repo, commit, tmp / "wt") as wt:
        if arm.use_index and index_source is not None:
            index_mod.install(index_source, wt, cfg.index.paths)
        run_result = invoke(cfg.agent, arm, PROMPT, wt, transcript)

    events = load(transcript)
    found = scan(events, arm.activation_patterns, strip=str(wt))
    detail = found["evidence"][0] if found["evidence"] else (
        run_result.summary.get("result") or "no trace of the skill in the probe"
    )
    return ProbeResult(
        arm=arm.name,
        reachable=bool(found["activated"]),
        detail=str(detail)[:400],
        wall_s=run_result.wall_s,
        cost_reported_usd=run_result.summary.get("cost_usd"),
        transcript_path=str(transcript),
        checked_at=utc_iso(),
    )


def probe_all(cfg: Config, commit: str, index_source: Path | None,
              transcript_dir: Path) -> dict[str, Any]:
    """Probe every arm that claims a skill. Returns {arm: result, ...} plus `ok`."""
    results = {}
    for arm in cfg.arms:
        if not arm.activation_patterns:
            continue
        results[arm.name] = probe_arm(cfg, arm, commit, index_source, transcript_dir).to_dict()
    return {
        "ok": all(r["reachable"] for r in results.values()),
        "arms": results,
        "prompt": PROMPT,
    }
