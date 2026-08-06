# Experiment specification

This document is the protocol. It is committed before any data exists, and the
git timestamp is the evidence. Everything that could be chosen after seeing the
numbers — the primary metric, the exclusion rules, the verdict boundaries — is
fixed here.

## 1. Question

For a coding-agent skill that advertises a cost reduction of factor *F*: what is
the ratio of the cost of a completed task without the skill to the cost of the
same task with it, on one real repository, with tasks taken from that
repository's own history?

Cost is the price of a task carried to green tests, not the price of a query.

## 2. Hypotheses

- H0: the geometric mean of the per-task ratio control/experiment equals 1.0.
- H1 (advertised): it equals *F*.

Both are tested against the same interval; the buckets in §8 map the interval
onto a verdict.

## 3. Units

- **Task** — one mined commit. The unit of analysis.
- **Run** — one (task, arm, repeat). The unit of execution.
- **Cell** — one (task, arm). Repeats within a cell measure noise, not sample
  size, and are collapsed by median before any comparison.

## 4. Task construction

A commit qualifies when all of the following hold:

1. it is not a merge and not a revert;
2. it touches at least one test file and at least one non-test code file;
3. it touches between `min_files` and `max_files` files (default 2–25) — a
   larger commit is several tasks in one coat;
4. its subject is not a dependency bump, lockfile update, release or rename;
5. it touches no path matching the sensitive list (keys, `.env`, credentials,
   tfstate) or the infrastructure list (migrations, `*.sql`, lockfiles);
6. at least one of its test files is added or modified rather than deleted. A
   commit that only deletes tests leaves the task with no grader: restoring
   "the commit's tests" restores nothing and both arms fail for a reason that
   has nothing to do with the agent.

From a qualifying commit:

- **starting state** = the parent commit, checked out into a detached worktree;
- **task statement** = the commit subject and body, with `(#123)` references and
  `Co-authored-by` / `Signed-off-by` / `Closes` trailers removed, truncated to
  1200 characters;
- **grader** = the commit's own versions of the test files it touched;
- during the run those test files are **absent** from the worktree; at grading
  they are written back from the commit and executed.

### 4.1 Human review

Mining writes `review: pending` on every task. The runner executes only
`review: ok`. Nothing promotes a task automatically. Tasks whose message
contains a fenced code block or the name or path of a file the commit changed are
flagged `leak_risk: true` so they are read first, but the flag is an ordering
aid, not a decision.

### 4.2 Machine verification

Before any spend, each approved task must satisfy both:

- tests **pass** at the commit — otherwise the grader is broken in this
  environment and no agent could ever satisfy it (`fails_at_commit`);
- the same tests **fail** at the parent — otherwise the task is already done at
  the starting state (`passes_at_parent`).

Only `verified: ok` tasks enter the sweep.

## 5. Arms

Two arms, identical in model, reasoning effort, permission mode, per-session
budget, timeout, prompt, worktree, setup command and hidden tests.

- **A (control)** — no skills, no MCP servers. Repository-level agent
  instructions (`.claude/`, `CLAUDE.md`, `AGENTS.md`) are removed from the
  worktree in **both** arms so that neither inherits guidance the other lacks.
- **B (experimental)** — the same, plus the skill under test and its index.

Both arms also run with the host's own agent environment cleared (`CLAUDECODE`,
`CLAUDE_EFFORT`, `ANTHROPIC_BASE_URL` and friends). A sweep launched from inside
an agent session would otherwise inherit settings that silently change effort or
endpoint — identically in both arms, and differently from a sweep launched out of
a plain shell.

Each arm declares what it expects to be handed (`expect_present`,
`expect_absent`, checked against the session's init event) and what proves it
ran (`activation_patterns`) or must never appear (`forbidden_patterns`).

## 6. Execution

- Every run: a fresh session id, a fresh detached worktree, destroyed afterwards.
  The source repository is read-only throughout.
- Order: all (task, arm, repeat) cells are generated, then shuffled once with a
  fixed seed. Arms are interleaved so time-of-day and API load cannot align with
  an arm.
- Results are appended to `runs.jsonl` as each run finishes; a rerun resumes from
  the recorded run keys.
- A sweep-level budget stops execution and records the number of runs left
  undone. A per-session budget caps any single runaway run.
- The index of the experimental arm is built once, in a reference checkout at
  repository HEAD, and its wall time, exit status and artefact size are recorded
  separately from the per-task numbers.

## 7. Validity rules

A run is **invalid**, and is excluded from every estimate with its reason
recorded, when any of these hold:

| condition | reason |
|---|---|
| no trace of the skill in an arm that declares `activation_patterns` | `skill never activated` |
| a trace of the skill in an arm that declares `forbidden_patterns` | `control arm contaminated by the skill` |
| the session was not handed what the arm declared | `arm was not configured as declared` |
| the agent exited non-zero, errored or hit the timeout | `agent exited with an error` / `agent timed out` |
| the harness itself failed | `harness error: …` |

Invalid runs are published with everything else. The share of invalid runs is
reported before any figure about money: if a meaningful fraction of the
experimental arm never activated, that is the headline, not the percentages.

## 8. Analysis

**Primary metric.** Cost in USD per task, on tasks solved by both arms,
**computed from the run's token counts** against a dated price table in the
config — not read from the session's own `total_cost_usd`.

That field is convenient and wrong to depend on: on a subscription it can be
zero or absent, because nothing was billed per token, while the work still
happened and still had a price. A benchmark that reads it measures the billing
arrangement of whoever ran it. Input, output, the two cache-write TTLs and cache
reads are priced separately, the reported figure is kept alongside as a
cross-check, and because the raw token counts are published a reader can
re-price the entire run at different rates without re-running it.

**Sensitivity.** The same computation over all valid pairs regardless of
outcome, reported next to it. Total tokens, output tokens, turns and wall clock
are secondary metrics computed identically.

**Per task:** median cost across valid repeats in each cell, then
`ratio = control / experiment`. Above 1.0 means the experimental arm is cheaper.

**Across tasks:**

- geometric mean of ratios;
- 95% percentile interval from a paired bootstrap resampling **tasks** (not
  runs), 10 000 resamples, seeded;
- median ratio;
- exact two-sided sign test;
- Wilcoxon signed-rank on log ratios (exact for n ≤ 20 without ties, normal
  approximation with tie correction otherwise).

**Defensive metric.** Solve counts per arm, the discordant pairs
(only-control / only-experimental) and an exact test on them. A cost reduction
accompanied by a fall in solved tasks is not a saving.

**Noise floor.** The geometric standard deviation of cost across repeats within
a cell, reported before the effect. If `|geometric mean − 1|` is smaller than
`|geometric SD − 1|`, the report states that the effect is below the
repeat-to-repeat spread.

## 9. Verdict buckets

Fixed before the run. Evaluated in this order, so an interval wide enough to
cover both parity and the claim is inconclusive rather than a confirmation.

| bucket | condition |
|---|---|
| `null` | interval covers 1.0 |
| `worse` | interval lies entirely below 1.0 |
| `as_promised` | interval covers *F* |
| `smaller_but_real` | interval lies entirely between 1.0 and *F* |
| `above_claim` | interval lies entirely above *F* |

## 10. Design of the run

1. **Pilot** — 12 tasks × 3 repeats × 2 arms = 72 runs. Its purpose is the noise
   floor of §8, not the effect. The number is published whatever it is.
2. **Main run** — 60–80 tasks × 2 repeats × 2 arms, conditional on the pilot
   showing the effect is separable from the noise. If it is not, that is the
   result and the main run is not paid for.

## 11. Deviations

Any departure from this document is recorded in `DEVIATIONS.md` with a date and
a reason, alongside the run it applies to.

## 12. Known limits

One repository, one language, one style of task, a few dozen pairs. Model
versions and prices move; every run directory is stamped and carries its resolved
config. Commit messages are a noisy proxy for a task statement: they were written
by someone who already knew the answer, which makes some tasks easier than a real
ticket and some harder, in both arms equally.

One bias runs in a known direction and cannot be removed, only declared. A commit
message often names the class or command it changed (`wrap Jinja rendering errors
in AlertCommand._execute_query`). That hands both arms part of the search, and
searching is exactly what a code graph is for, so tasks phrased this way
understate the graph's benefit. The `leak_risk` flag catches messages naming a
changed *file*, not a symbol, so some of these survive review. The direction of
the bias is against the skill under test, which is the safer way for it to be
wrong.
