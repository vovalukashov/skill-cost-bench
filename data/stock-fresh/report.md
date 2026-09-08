# graphify-superset-stock

Generated 2026-09-08T17:24:40Z. Control arm `control`, experimental arm `graphify-stock`. Advertised factor under test: 70.0x.

## 1. Did the skill run at all

- runs recorded: 320
- invalid: 3 (0.9%)

| reason | runs |
|---|---|
| graphify-stock: agent exited with an error | 3 |

| arm | could reach the skill | evidence |
|---|---|---|
| graphify-stock | yes | tool_input: …aphify-out/ 2>&1; echo \"---\"; test -f graphify-out/graph.json && echo \"graph.json exists\""}… |
| graphify-strict | yes | tool_input: …{"command": "graphify query \"what does this codebase do\" 2>&1"}… |

- `graphify-stock`: skill offered in 157 valid runs, used in 113, left untouched in 44 (28%)
  - the skill's own tooling prompted the model in 157 of them; used without any prompt in 0, prompted and still unused in 44
  - `MANDATORY: graphify-out`: 1450 hits, heard in 157 runs
  - `may be STALE`: 32 hits, heard in 20 runs

| navigation | used the skill | left it untouched |
|---|---|---|
| given | 11 | 9 |
| needed | 104 | 36 |

Read this next to the split in 3a. A task that names the symbol to change leaves nothing to search for, and the model behaves as if it knows: those are the runs where it grepped the name, said it had found the place directly, and skipped the graph.

A valid run in which the model was handed the skill and did not touch it counts, and is reported above. Excluding it would average only over the runs where the skill happened to appeal. That reading holds because the positive control shows the arm could reach the skill; without it, the same transcript would mean nothing at all.

## 2. How noisy is one task

- repeat cells measured: 157
- median geometric SD of cost within a cell: 1.166
- median max/min spread within a cell: 1.243

This is the price of everything below: the same task, the same arm, nothing changed between repeats.

## 3. Effect

Ratios are control / experiment, so a number above 1.0 means the experimental arm is cheaper.

`both_solved` is the primary scope. `used_only` drops the experimental repeats that never touched the skill; the model chose those itself, and may have reached for the tool precisely where it was stuck, so read that row as description and not as an effect.

| metric | scope | n | geo mean | 95% CI | median | p (sign) | p (Wilcoxon) | verdict |
|---|---|---|---|---|---|---|---|---|
| cost, USD | both_solved | 27 | 0.770 | 0.581–0.954 | 0.813 | 0.052 | 0.026 | worse |
| cost, USD | all_valid | 80 | 0.914 | 0.816–1.015 | 0.904 | 0.314 | 0.052 | null |
| cost, USD | used_only | 19 | 0.687 | 0.482–0.905 | 0.777 | 0.019 | 0.018 | worse |
| tokens, all kinds | both_solved | 27 | 0.804 | 0.603–1.018 | 0.857 | 0.248 | 0.160 | null |
| tokens, all kinds | all_valid | 80 | 0.972 | 0.858–1.096 | 0.940 | 0.576 | 0.609 | null |
| tokens, all kinds | used_only | 19 | 0.706 | 0.491–0.957 | 0.736 | 0.064 | 0.040 | worse |
| output tokens | both_solved | 27 | 0.822 | 0.570–1.072 | 0.977 | 0.701 | 0.449 | null |
| output tokens | all_valid | 80 | 0.996 | 0.860–1.132 | 1.032 | 0.434 | 0.650 | null |
| output tokens | used_only | 19 | 0.738 | 0.461–1.028 | 0.966 | 0.359 | 0.196 | null |
| turns | both_solved | 27 | 0.860 | 0.642–1.074 | 0.964 | 0.690 | 0.404 | null |
| turns | all_valid | 80 | 1.027 | 0.914–1.142 | 1.049 | 0.356 | 0.302 | null |
| turns | used_only | 19 | 0.767 | 0.530–1.013 | 0.903 | 0.332 | 0.170 | null |
| wall clock, s | both_solved | 27 | 0.548 | 0.310–0.819 | 0.768 | 0.006 | 0.003 | worse |
| wall clock, s | all_valid | 80 | 0.806 | 0.633–0.978 | 0.823 | 0.057 | 0.057 | worse |
| wall clock, s | used_only | 19 | 0.423 | 0.179–0.756 | 0.724 | 0.001 | 0.001 | worse |

**Verdict on the primary metric:** `worse` — interval lies entirely below 1.0 — the skill costs more.

### 3a. Where there was searching to do

A task is `given` when grepping its own words lands on the file that has to change, and `needed` otherwise. The graph's whole claim is about the search, so a task that hands the location over cannot show it working. Cost, tasks solved by both arms.

| navigation | n | geo mean | 95% CI | verdict |
|---|---|---|---|---|
| needed | 22 | 0.744 | 0.535–0.963 | worse |
| given | 5 | 0.893 | 0.697–1.172 | null |

## 4. Did it still work

- solved in both arms: 27
- only control: 10
- only experimental: 6
- neither: 37
- sign test on discordant tasks: p = 0.454

Cheaper with failing tests is not a saving.

## 5. What the index cost

- command: `/Users/luka/Projects/skill-cost-bench/.venv/bin/graphify extract . --code-only`
- indexes built: 80/80, one per task, each at that task's parent commit (80 copied from an earlier run rather than rebuilt; the figures below are that run's)
- wall clock: 89.1 s each, 7128.3 s in total
- artefacts: graphify-out/graph.json, graphify-out/.graphify_analysis.json, graphify-out/SKILL.md, graphify-out/references (8517.2 MB across all indexes)

A tool that saves per task but wants its index rebuilt every morning and a tool that does not are two different tools.

Each index is built at the commit the agent is handed, so it cannot contain the task's own solution. The cost of that choice is that the graph is never stale, which a real one always is — a limitation, and one that points in the skill's favour.

Total spend recorded across all runs: $93.85.
