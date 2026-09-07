# Raw results

Everything the reports were computed from. Nothing here is summarised or
filtered: invalid runs, unsolved tasks and runs where the skill went untouched
are all present, because the point of publishing is that the analysis can be
argued with without re-running the experiment.

Target: [apache/superset](https://github.com/apache/superset), ~400k lines.
Skill under test: [graphify](https://github.com/Graphify-Labs/graphify) 0.9.34,
which advertised 71.5x fewer tokens per query. Agent: Claude Code headless
(2.1.220 for the August sweeps, 2.1.236 for `stock/`), `claude-sonnet-5`, low
reasoning effort, on a subscription.

## The four sweeps

| directory | tasks | reps | runs | the experimental arm | headline |
|---|---|---|---|---|---|
| `pilot/` | 12 | 3 | 72 | skill available, model free to use it | used it **0 times in 36 runs** |
| `forced/` | 12 | 3 | 72 | ordered to locate the work with the graph first | 0.683 — costs more |
| `main/` | 80 | 2 | 320 | same, at scale | **0.843** (95% CI 0.726–0.989) — costs more |
| `stock/` | 80 | 2 | 480 | the vendor's own `graphify install --project`, with and without `--strict`, three arms | ⚠️ **artifact, see below** — 0.807 stock, 0.802 strict; the read hook took its softened branch in 610 of 613 firings, so this measured a weaker tool than named and the strict block was unreachable |

Ratios are control ÷ experiment, so below 1.0 means the experimental arm cost
more. `main/` supersedes `forced/`: the twelve-task estimate was overstating the
effect, which is the reason the larger sweep exists.

`stock/` was meant to answer the objection to all three of the above: that the
harness handed the skill over its own way rather than the way the product
installs itself. In `stock/` the installer runs in every experimental worktree
after the repository's own agent instructions are stripped, so its CLAUDE.md
section and its PreToolUse hooks are the only guidance in the tree.

**It is kept as an artifact, not a result.** The skill's read hook decides
freshness by mtime and, when the file being read is newer than `graph.json`,
downgrades itself from "you MUST query the graph" to "reading the file directly
is fine" before the strict block is ever considered. The harness copied each
index with its August build timestamp preserved into worktrees checked out in
September, so every source file looked newer than the graph: across the strict
arm the read hook took the softened branch in 610 of 613 firings, and the block
fired 0 times in 160 for that reason, not because of anything the model did.
Both experimental arms therefore received a weaker tool than the one named. The
pre-sweep check missed it because it copied the graph with a plain `cp`, which
stamps the copy with the current time. The transcripts carry every hook firing
and its exact wording, which is how the artifact was found. The corrected sweep,
with the index re-stamped on install and the hook's three voices counted apart,
is the directory listed next. Two files per pair: `summary.json`/`report.md` for
control vs `graphify-stock`, `summary.graphify-strict.json`/`report.graphify-strict.md`
for control vs `graphify-strict`. The exact arm prompts the August sweeps used are
in `arms/`.

`delivery_check.json` answers the obvious objection to the pilot — that the
skill went unused because of how the harness handed it over. It re-runs six of
the same tasks with the skill installed the way a user installs it, registered in
the working copy's own `.claude/skills` with `--setting-sources project`. Still
0 of 6.

## Files in each sweep

- `runs.jsonl` — one row per run: cost, tokens, turns, wall time, whether the
  tests passed, whether the skill was touched, and the run's own validity
  verdict with its reason. Costs are computed from token counts against the
  dated price table in the config, not read from the agent's own report; the
  reported figure is kept alongside as a cross-check.
- `summary.json`, `report.md` — the analysis. Reproduce with
  `python3 scripts/analyze.py --config <config> --out <sweep>`; it is a pure
  function of `runs.jsonl` plus the config.
- `probe.json` — the positive control, run before any task. It shows the
  experimental arm calling one of its own tools and reporting the result, which
  is what makes "the model did not use the skill" readable as a choice rather
  than as a broken arm.
- `config_resolved.json` — every setting as the run actually saw it.
- `index_builds.json` — what building the code graph cost, per task.
- `tasks_used.json`, `run_state.json` — which tasks ran, and how the sweep ended.

## Transcripts

`transcripts/*.tar.gz`, one archive per sweep, 955 sessions in all. Each is the
full `stream-json` event log: the init event listing what the session was
offered, every tool call and result, and the final usage block. `stock/` was run
with `--include-hook-events`, so its transcripts also carry every firing of the
skill's own hooks and what each one said. This is where the activation claims
can be checked directly rather than taken on trust.

## Tasks

`tasks/superset.tasks.yaml` — the manifest. Each task is a real commit that
touched code and tests: the parent commit is the starting state, the commit
message is the task, and the commit's own tests are the grader, removed from the
working copy while the agent works and restored to judge it.

Fields worth knowing:

- `verified` — `ok` means the tests were confirmed to pass at the commit and
  fail at its parent. Tasks that failed either check are kept with their reason
  rather than deleted: 9 were already green at the starting state and 7 had a
  grader that could not pass in this environment.
- `navigation` — `given` when grepping the task's own words lands on the file
  that has to change, `needed` otherwise. A code graph shortens the search, so a
  task that hands the location over cannot show it working, and the report keeps
  the two apart.
- `leak_risk` — the commit message may contain the answer. Those 42 were never
  run.
