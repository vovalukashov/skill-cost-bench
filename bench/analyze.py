"""Turning runs.jsonl into a report.

Order of the report is deliberate. The share of invalid runs comes first,
because a skill that never activated is a bigger finding than any percentage.
The repeat-to-repeat noise comes second, because it prices everything below it.
The effect comes third, and it carries a defensive metric — the share of solved
tasks — so that "cheaper" cannot quietly mean "gave up sooner".
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any, Iterable

from .config import Config
from .stats import VERDICTS, estimate, noise_floor, sign_test, verdict
from .util import read_jsonl, utc_iso, write_json

# (name, solved-by-both-arms only, experimental repeats that used the skill only)
# The primary scope is the first one; the third is descriptive, not randomised.
SCOPES = [
    ("both_solved", True, False),
    ("all_valid", False, False),
    ("used_only", True, True),
]

METRICS = [
    ("cost_usd", "cost, USD"),
    ("total_tokens", "tokens, all kinds"),
    ("output_tokens", "output tokens"),
    ("num_turns", "turns"),
    ("wall_s", "wall clock, s"),
]


def _median(values: Iterable[float]) -> float | None:
    clean = [v for v in values if isinstance(v, (int, float)) and v is not None]
    return statistics.median(clean) if clean else None


def collect(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in rows if r.get("valid")]
    invalid = [r for r in rows if not r.get("valid")]

    reasons: dict[str, int] = {}
    for r in invalid:
        key = f"{r.get('arm')}: {r.get('invalid_reason') or 'unknown'}"
        reasons[key] = reasons.get(key, 0) + 1

    per_arm_totals: dict[str, dict[str, int]] = {}
    for r in rows:
        arm = str(r.get("arm"))
        bucket = per_arm_totals.setdefault(
            arm, {"runs": 0, "valid": 0, "solved": 0, "used_skill": 0, "available_unused": 0}
        )
        bucket["runs"] += 1
        if r.get("valid"):
            bucket["valid"] += 1
            if r.get("solved"):
                bucket["solved"] += 1
            status = r.get("activation_status")
            if status == "used":
                bucket["used_skill"] += 1
            elif status == "available_unused":
                bucket["available_unused"] += 1

    return {
        "n_rows": len(rows),
        "n_valid": len(valid),
        "n_invalid": len(invalid),
        "invalid_share": (len(invalid) / len(rows)) if rows else 0.0,
        "invalid_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "per_arm": per_arm_totals,
    }


def cells(rows: list[dict[str, Any]], metric: str) -> dict[tuple[str, str], list[float]]:
    out: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        if not r.get("valid"):
            continue
        value = r.get(metric)
        if not isinstance(value, (int, float)):
            continue
        out.setdefault((str(r["task"]), str(r["arm"])), []).append(float(value))
    return out


def pair_ratios(
    rows: list[dict[str, Any]],
    metric: str,
    control: str,
    experiment: str,
    solved_only: bool,
    used_only: bool = False,
) -> tuple[list[float], list[str]]:
    """One ratio per task: median over repeats, control divided by experiment.

    ``used_only`` keeps the experimental repeats in which the skill was actually
    touched. It answers the question a reader will ask anyway — when the model
    does reach for the tool, does it pay? — and it is not a randomised
    comparison: the model chooses when to reach, and it may reach precisely on
    the tasks that were confusing it. Read as description, never as effect.
    """
    usable = [r for r in rows if r.get("valid") and (r.get("solved") or not solved_only)]
    if used_only:
        usable = [
            r for r in usable
            if r.get("arm") != experiment or r.get("activation_status") != "available_unused"
        ]
    by_cell = cells(usable, metric)
    tasks = sorted({task for task, _ in by_cell})
    ratios: list[float] = []
    used: list[str] = []
    for task in tasks:
        a = by_cell.get((task, control))
        b = by_cell.get((task, experiment))
        if not a or not b:
            continue
        ma, mb = _median(a), _median(b)
        if not ma or not mb or ma <= 0 or mb <= 0:
            continue
        ratios.append(ma / mb)
        used.append(task)
    return ratios, used


def solve_rates(rows: list[dict[str, Any]], control: str, experiment: str) -> dict[str, Any]:
    by_task: dict[str, dict[str, list[bool]]] = {}
    for r in rows:
        if not r.get("valid"):
            continue
        by_task.setdefault(str(r["task"]), {}).setdefault(str(r["arm"]), []).append(
            bool(r.get("solved"))
        )
    only_control = only_experiment = both = neither = 0
    for task, arms in by_task.items():
        a = arms.get(control)
        b = arms.get(experiment)
        if not a or not b:
            continue
        sa = sum(a) / len(a) >= 0.5
        sb = sum(b) / len(b) >= 0.5
        if sa and sb:
            both += 1
        elif sa:
            only_control += 1
        elif sb:
            only_experiment += 1
        else:
            neither += 1
    discordant = only_control + only_experiment
    p = sign_test([2.0] * only_experiment + [0.5] * only_control) if discordant else 1.0
    return {
        "both_solved": both,
        "only_control": only_control,
        "only_experiment": only_experiment,
        "neither": neither,
        "p_discordant": p,
    }


def analyze(cfg: Config, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    rows = list(read_jsonl(out / "runs.jsonl"))
    if not rows:
        raise SystemExit(f"no runs found in {out / 'runs.jsonl'}")

    control = next((a.name for a in cfg.arms if not a.activation_patterns), cfg.arms[0].name)
    experiment = next((a.name for a in cfg.arms if a.activation_patterns), cfg.arms[-1].name)

    summary: dict[str, Any] = {
        "generated_at": utc_iso(),
        "run_name": cfg.run.name,
        "control_arm": control,
        "experiment_arm": experiment,
        "claim_factor": cfg.claim_factor,
        "claim_source": cfg.claim.get("source"),
        "repeats": cfg.run.repeats,
        "seed": cfg.run.seed,
        "validity": collect(rows),
        "noise": noise_floor(cells(rows, "cost_usd")),
        "solve": solve_rates(rows, control, experiment),
        "metrics": {},
        "spent_usd": round(sum(float(r.get("cost_usd") or 0.0) for r in rows), 4),
    }

    for metric, _label in METRICS:
        entry: dict[str, Any] = {}
        for scope, solved_only, used_only in SCOPES:
            ratios, tasks = pair_ratios(rows, metric, control, experiment, solved_only,
                                        used_only)
            if len(ratios) < 2:
                entry[scope] = {"n": len(ratios), "insufficient": True}
                continue
            est = estimate(ratios, n_resamples=cfg.run.bootstrap_resamples, seed=cfg.run.seed)
            entry[scope] = {
                **est.to_dict(),
                "tasks": tasks,
                "verdict": verdict(est.ci_low, est.ci_high, cfg.claim_factor),
            }
        summary["metrics"][metric] = entry

    import json

    builds = out / "indexes" / "builds.json"
    if builds.exists():
        per_commit = json.loads(builds.read_text(encoding="utf-8"))
        done = [b for b in per_commit.values() if b.get("built")]
        summary["index_build"] = {
            "n_indexes": len(per_commit),
            "n_built": len(done),
            "n_reused": sum(1 for b in per_commit.values() if b.get("reused_from")),
            "command": next((b.get("command") for b in per_commit.values()), None),
            "wall_s_total": round(sum(float(b.get("wall_s") or 0) for b in done), 1),
            "wall_s_each": round(
                sum(float(b.get("wall_s") or 0) for b in done) / len(done), 1
            ) if done else None,
            "bytes_total": sum(int(b.get("bytes_total") or 0) for b in done),
            "paths": next((b.get("paths") for b in done), []),
        }

    probe_path = out / "probe.json"
    if probe_path.exists():
        summary["probe"] = json.loads(probe_path.read_text(encoding="utf-8"))

    primary = summary["metrics"]["cost_usd"].get("both_solved", {})
    summary["headline"] = {
        "metric": "cost_usd",
        "scope": "both_solved",
        "geometric_mean": primary.get("geometric_mean"),
        "ci": [primary.get("ci_low"), primary.get("ci_high")],
        "verdict": primary.get("verdict"),
        "verdict_meaning": VERDICTS.get(primary.get("verdict", ""), ""),
        "effect_below_noise": _effect_below_noise(primary, summary["noise"]),
    }

    write_json(out / "summary.json", summary)
    (out / "report.md").write_text(render(summary), encoding="utf-8")
    return summary


def _effect_below_noise(primary: dict[str, Any], noise: dict[str, Any]) -> bool | None:
    gm = primary.get("geometric_mean")
    gsd = noise.get("median_geometric_sd")
    if not isinstance(gm, (int, float)) or not isinstance(gsd, (int, float)):
        return None
    if gsd != gsd:  # NaN
        return None
    return abs(gm - 1.0) < abs(gsd - 1.0)


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        if value != value:
            return "—"
        return f"{value:.{digits}f}"
    return str(value)


def render(summary: dict[str, Any]) -> str:
    v = summary["validity"]
    lines: list[str] = []
    add = lines.append

    add(f"# {summary['run_name']}")
    add("")
    add(f"Generated {summary['generated_at']}. "
        f"Control arm `{summary['control_arm']}`, experimental arm `{summary['experiment_arm']}`. "
        f"Advertised factor under test: {summary['claim_factor']}x.")
    add("")

    add("## 1. Did the skill run at all")
    add("")
    add(f"- runs recorded: {v['n_rows']}")
    add(f"- invalid: {v['n_invalid']} ({v['invalid_share'] * 100:.1f}%)")
    if v["invalid_reasons"]:
        add("")
        add("| reason | runs |")
        add("|---|---|")
        for reason, count in v["invalid_reasons"].items():
            add(f"| {reason} | {count} |")
    add("")

    probe = summary.get("probe")
    if probe:
        add("| arm | could reach the skill | evidence |")
        add("|---|---|---|")
        for name, res in probe.get("arms", {}).items():
            mark = "yes" if res.get("reachable") else "NO"
            add(f"| {name} | {mark} | {str(res.get('detail', ''))[:110]} |")
        add("")

    offered_any = False
    for arm, bucket in v["per_arm"].items():
        offered = bucket["used_skill"] + bucket["available_unused"]
        if not offered:
            continue
        offered_any = True
        share = bucket["available_unused"] / offered * 100
        add(f"- `{arm}`: skill offered in {offered} valid runs, used in "
            f"{bucket['used_skill']}, left untouched in "
            f"{bucket['available_unused']} ({share:.0f}%)")
    if offered_any:
        add("")

    add("A valid run in which the model was handed the skill and did not touch it "
        "counts, and is reported above. Excluding it would average only over the "
        "runs where the skill happened to appeal. That reading holds because the "
        "positive control shows the arm could reach the skill; without it, the "
        "same transcript would mean nothing at all.")
    add("")

    add("## 2. How noisy is one task")
    add("")
    noise = summary["noise"]
    add(f"- repeat cells measured: {noise['n_cells']}")
    add(f"- median geometric SD of cost within a cell: {_fmt(noise.get('median_geometric_sd'))}")
    add(f"- median max/min spread within a cell: {_fmt(noise.get('median_spread_ratio'))}")
    add("")
    add("This is the price of everything below: the same task, the same arm, "
        "nothing changed between repeats.")
    add("")

    add("## 3. Effect")
    add("")
    add("Ratios are control / experiment, so a number above 1.0 means the "
        "experimental arm is cheaper.")
    add("")
    add("`both_solved` is the primary scope. `used_only` drops the experimental "
        "repeats that never touched the skill; the model chose those itself, and "
        "may have reached for the tool precisely where it was stuck, so read that "
        "row as description and not as an effect.")
    add("")
    add("| metric | scope | n | geo mean | 95% CI | median | p (sign) | p (Wilcoxon) | verdict |")
    add("|---|---|---|---|---|---|---|---|---|")
    for metric, label in METRICS:
        for scope, _, _ in SCOPES:
            entry = summary["metrics"].get(metric, {}).get(scope, {})
            if entry.get("insufficient"):
                add(f"| {label} | {scope} | {entry.get('n', 0)} | — | — | — | — | — | not enough pairs |")
                continue
            add(
                f"| {label} | {scope} | {entry.get('n')} | {_fmt(entry.get('geometric_mean'))} "
                f"| {_fmt(entry.get('ci_low'))}–{_fmt(entry.get('ci_high'))} "
                f"| {_fmt(entry.get('median'))} | {_fmt(entry.get('p_sign'))} "
                f"| {_fmt(entry.get('p_wilcoxon'))} | {entry.get('verdict')} |"
            )
    add("")

    head = summary["headline"]
    add(f"**Verdict on the primary metric:** `{head['verdict']}` — {head['verdict_meaning']}.")
    if head.get("effect_below_noise"):
        add("")
        add("> The measured effect is smaller than the spread between repeats of a "
            "single task. Everything above rests on averaging across tasks, not on "
            "any individual comparison.")
    add("")

    add("## 4. Did it still work")
    add("")
    s = summary["solve"]
    add(f"- solved in both arms: {s['both_solved']}")
    add(f"- only control: {s['only_control']}")
    add(f"- only experimental: {s['only_experiment']}")
    add(f"- neither: {s['neither']}")
    add(f"- sign test on discordant tasks: p = {_fmt(s['p_discordant'])}")
    add("")
    add("Cheaper with failing tests is not a saving.")
    add("")

    if summary.get("index_build"):
        ib = summary["index_build"]
        add("## 5. What the index cost")
        add("")
        add(f"- command: `{ib.get('command')}`")
        reused = ib.get("n_reused") or 0
        add(f"- indexes built: {ib.get('n_built')}/{ib.get('n_indexes')}, one per task, "
            f"each at that task's parent commit"
            + (f" ({reused} copied from an earlier run rather than rebuilt; the "
               f"figures below are that run's)" if reused else ""))
        add(f"- wall clock: {_fmt(ib.get('wall_s_each'), 1)} s each, "
            f"{_fmt(ib.get('wall_s_total'), 1)} s in total")
        add(f"- artefacts: {', '.join(ib.get('paths') or []) or '—'} "
            f"({ib.get('bytes_total', 0) / 1_000_000:.1f} MB across all indexes)")
        add("")
        add("A tool that saves per task but wants its index rebuilt every morning "
            "and a tool that does not are two different tools.")
        add("")
        add("Each index is built at the commit the agent is handed, so it cannot "
            "contain the task's own solution. The cost of that choice is that the "
            "graph is never stale, which a real one always is — a limitation, and "
            "one that points in the skill's favour.")
        add("")

    add(f"Total spend recorded across all runs: ${summary['spent_usd']:.2f}.")
    add("")
    return "\n".join(lines)
