# skill-cost-bench

A paired A/B harness that answers one question about a coding-agent skill:
**what does a finished task cost with it, and without it?**

Not how well the skill retrieves code. Not how many tokens one query saves. The
cost of a task carried until the project's own tests go green — including the
edit-test-edit loops, the dead ends and the backtracking, which is where an
agent's bill actually comes from.

The harness knows nothing about any particular skill. An arm is a name, an
environment, a few CLI flags and the patterns that prove the skill ran. Swap the
arm block in the config and it measures something else.

## Why this exists

Skills are advertised with impressive multipliers. When those numbers get
measured on real agent work they tend to shrink, and sometimes reverse:

| skill | advertised | measured by JetBrains on SkillsBench |
|---|---|---|
| caveman | 65% fewer tokens | 8.5% fewer output tokens over 86 tasks (a 10-task pilot had said 29.5%) |
| rtk | 60–90% fewer tokens | +7.6% **more** expensive at low effort (p=0.004), ±0% at high |
| ponytail | −54% code, −22% tokens, −20% cost | −15% code, −10.3% cost over 80 paired tasks — and zero self-activations in ten sessions without a SessionStart hook |

That last row is the one this harness is built around. A skill that silently
never runs produces exactly the numbers of a skill that works perfectly and costs
nothing. Any benchmark that does not check activation cannot tell those two
apart, and neither can anyone writing a review based on their own impressions.

So every run in an arm that declares a skill is scanned for traces of it. A run
with no traces is not a zero. It is invalid, excluded, and counted with a reason.

## How a task is made

Tasks are not written by hand — hand-written tasks are tasks written for the
tool. They are reconstructed from commits the repository already contains:

- a commit that touched production code **and** tests is a candidate;
- its parent is the starting state;
- its message, stripped of PR references and trailers, is the task;
- its tests are the grader;
- those tests are deleted from the worktree while the agent works and restored
  only at grading time.

Two checks run before anything is paid for. The tests must pass at the commit
(otherwise the grader is broken in this environment) and fail at the parent
(otherwise the task is already done and both arms get a free win).

Merges, reverts, dependency bumps, renames, commits over 25 files, and anything
touching secrets, migrations or lockfiles are filtered out. Every mined task
lands as `review: pending` and the runner ignores anything but `review: ok`,
because the one thing no filter can see is a commit message that hands over the
answer.

## How a run is made

Two arms, identical in everything the harness controls — model, reasoning
effort, permission mode, time limit, prompt, worktree, hidden tests:

- **A, control** — a bare agent: no skills, no MCP servers, no repository
  instructions;
- **B, experimental** — the same, plus the skill under test and its index.

Every run gets a fresh session and its own detached git worktree, destroyed
afterwards. The source repository is only ever read. The order of all runs is
shuffled once with a fixed seed and the arms are interleaved, so a slow hour on
the API cannot land on one arm.

Rows are appended to JSONL as they finish. Dying on run 180 of 240 costs
nothing: the next invocation resumes. A hard budget stops the sweep and records
how many runs were left undone rather than quietly shortening the experiment.

The index is built once, in a reference checkout, and timed and priced on its own
line. A tool that saves per task but wants its index rebuilt every morning and a
tool that does not are two different tools.

## How the numbers are made

The advertised claim is a ratio, so the statistics are multiplicative. Per task,
the ratio of control cost to experimental cost (above 1.0 means the skill is
cheaper), with repeats collapsed by median. Then:

- geometric mean of the per-task ratios;
- 95% interval from a paired bootstrap over **tasks**, 10 000 resamples;
- median, exact sign test, Wilcoxon on log ratios, so one freakishly cheap task
  cannot carry a headline;
- share of solved tasks alongside every money figure, because cheaper with
  failing tests is not a saving.

The verdict falls into one of five buckets fixed before the run — after a run
there is always a phrasing that makes the number look convincing:

| bucket | condition |
|---|---|
| `as_promised` | the interval covers the advertised factor |
| `smaller_but_real` | the interval excludes 1.0 and lies entirely below the claim |
| `null` | the interval covers 1.0 — parity cannot be excluded |
| `worse` | the interval lies entirely below 1.0 |
| `above_claim` | the interval lies entirely above the claim |

The report prints the share of invalid runs first, the repeat-to-repeat noise
second, and the effect only third. If the effect is smaller than the noise, the
report says so above every number about money.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install pyyaml pytest
.venv/bin/python -m pytest tests/ -q          # 40 tests, no API calls, free
.venv/bin/python scripts/selftest_stats.py --trials 200

cp config.example.yaml config.yaml            # then edit target.repo and the arms

.venv/bin/python scripts/build_tasks.py \
    --repo ~/code/myproject \
    --test-glob 'tests/**' --test-cmd 'pytest -q {tests}' \
    --since 2025-01-01 --max-tasks 80 \
    --out tasks/tasks.yaml

# read tasks/tasks.yaml, set review: ok on the good ones
.venv/bin/python scripts/verify_tasks.py --tasks tasks/tasks.yaml --only-approved
.venv/bin/python scripts/preflight.py --config config.yaml     # ~$0.02
.venv/bin/python scripts/run_bench.py --config config.yaml --dry-run
.venv/bin/python scripts/run_bench.py --config config.yaml
.venv/bin/python scripts/analyze.py --config config.yaml --out out/<STAMP>-<name>
```

`RUNBOOK.md` has the long version, `EXPERIMENT_SPEC.md` the protocol this
implements.

## Before you publish a run

The manifest contains commit messages and file paths from the repository you
mined, and the transcripts contain its source code. If that repository is not
yours to publish, neither are they. Publish the harness and the aggregate report;
keep `tasks/` and `out/` private.

## What this is not

One repository, one language, one style of task, a few dozen pairs. It is not a
benchmark of a skill in general; it is a measurement on one codebase, dated, with
the prices of the day. That is exactly why the raw JSONL — including the invalid
runs — ships next to the report: the analysis is a pure function of the raw data
and the config, and anyone can rerun it and disagree.

MIT.
