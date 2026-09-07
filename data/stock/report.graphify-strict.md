# graphify-superset-stock

Generated 2026-09-07T00:06:11Z. Control arm `control`, experimental arm `graphify-strict`. Advertised factor under test: 70.0x.

## 1. Did the skill run at all

- runs recorded: 320
- invalid: 1 (0.3%)

| reason | runs |
|---|---|
| control: agent exited with an error | 1 |

| arm | could reach the skill | evidence |
|---|---|---|
| graphify-stock | yes | tool_input: …{"command": "graphify query \"What are the god nodes in this codeba… |
| graphify-strict | yes | tool_input: …{"command": "graphify query \"What does this codebase do?\" 2>&1"}… |

- `graphify-strict`: skill offered in 160 valid runs, used in 119, left untouched in 41 (26%)
  - the skill's own tooling prompted the model in 160 of them; used without any prompt in 0, prompted and still unused in 41

| navigation | used the skill | left it untouched |
|---|---|---|
| given | 11 | 9 |
| needed | 108 | 32 |

Read this next to the split in 3a. A task that names the symbol to change leaves nothing to search for, and the model behaves as if it knows: those are the runs where it grepped the name, said it had found the place directly, and skipped the graph.

A valid run in which the model was handed the skill and did not touch it counts, and is reported above. Excluding it would average only over the runs where the skill happened to appeal. That reading holds because the positive control shows the arm could reach the skill; without it, the same transcript would mean nothing at all.

## 2. How noisy is one task

- repeat cells measured: 159
- median geometric SD of cost within a cell: 1.195
- median max/min spread within a cell: 1.287

This is the price of everything below: the same task, the same arm, nothing changed between repeats.

## 3. Effect

Ratios are control / experiment, so a number above 1.0 means the experimental arm is cheaper.

`both_solved` is the primary scope. `used_only` drops the experimental repeats that never touched the skill; the model chose those itself, and may have reached for the tool precisely where it was stuck, so read that row as description and not as an effect.

| metric | scope | n | geo mean | 95% CI | median | p (sign) | p (Wilcoxon) | verdict |
|---|---|---|---|---|---|---|---|---|
| cost, USD | both_solved | 28 | 0.802 | 0.693–0.911 | 0.832 | 0.004 | 0.002 | worse |
| cost, USD | all_valid | 80 | 0.882 | 0.813–0.957 | 0.883 | 0.000 | 0.000 | worse |
| cost, USD | used_only | 22 | 0.738 | 0.626–0.854 | 0.790 | 0.001 | 0.001 | worse |
| tokens, all kinds | both_solved | 28 | 0.853 | 0.731–0.985 | 0.861 | 0.036 | 0.023 | worse |
| tokens, all kinds | all_valid | 80 | 0.916 | 0.839–1.002 | 0.902 | 0.002 | 0.008 | null |
| tokens, all kinds | used_only | 22 | 0.784 | 0.656–0.924 | 0.850 | 0.001 | 0.008 | worse |
| output tokens | both_solved | 28 | 0.914 | 0.788–1.053 | 0.916 | 0.087 | 0.198 | null |
| output tokens | all_valid | 80 | 0.983 | 0.894–1.081 | 0.981 | 0.738 | 0.721 | null |
| output tokens | used_only | 22 | 0.859 | 0.721–1.016 | 0.872 | 0.052 | 0.091 | null |
| turns | both_solved | 28 | 0.934 | 0.816–1.059 | 0.952 | 0.442 | 0.331 | null |
| turns | all_valid | 80 | 0.979 | 0.909–1.055 | 1.000 | 0.640 | 0.424 | null |
| turns | used_only | 22 | 0.876 | 0.744–1.017 | 0.952 | 0.167 | 0.134 | null |
| wall clock, s | both_solved | 28 | 0.858 | 0.726–0.997 | 0.830 | 0.036 | 0.035 | worse |
| wall clock, s | all_valid | 80 | 0.900 | 0.821–0.989 | 0.922 | 0.033 | 0.008 | worse |
| wall clock, s | used_only | 22 | 0.808 | 0.669–0.961 | 0.830 | 0.052 | 0.027 | worse |

**Verdict on the primary metric:** `worse` — interval lies entirely below 1.0 — the skill costs more.

### 3a. Where there was searching to do

A task is `given` when grepping its own words lands on the file that has to change, and `needed` otherwise. The graph's whole claim is about the search, so a task that hands the location over cannot show it working. Cost, tasks solved by both arms.

| navigation | n | geo mean | 95% CI | verdict |
|---|---|---|---|---|
| needed | 23 | 0.796 | 0.670–0.924 | worse |
| given | 5 | 0.833 | 0.741–0.941 | worse |

## 4. Did it still work

- solved in both arms: 28
- only control: 8
- only experimental: 10
- neither: 34
- sign test on discordant tasks: p = 0.815

Cheaper with failing tests is not a saving.

## 5. What the index cost

- command: `/Users/luka/Projects/skill-cost-bench/.venv/bin/graphify extract . --code-only`
- indexes built: 80/80, one per task, each at that task's parent commit (80 copied from an earlier run rather than rebuilt; the figures below are that run's)
- wall clock: 89.1 s each, 7128.3 s in total
- artefacts: graphify-out/graph.json, graphify-out/.graphify_analysis.json, graphify-out/SKILL.md, graphify-out/references (8517.2 MB across all indexes)

A tool that saves per task but wants its index rebuilt every morning and a tool that does not are two different tools.

Each index is built at the commit the agent is handed, so it cannot contain the task's own solution. The cost of that choice is that the graph is never stale, which a real one always is — a limitation, and one that points in the skill's favour.

Total spend recorded across all runs: $97.83.
