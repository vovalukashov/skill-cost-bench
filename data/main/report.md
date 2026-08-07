# graphify-superset-main

Generated 2026-08-07T18:46:12Z. Control arm `control`, experimental arm `graphify`. Advertised factor under test: 70.0x.

## 1. Did the skill run at all

- runs recorded: 320
- invalid: 0 (0.0%)

| arm | could reach the skill | evidence |
|---|---|---|
| graphify | yes | tool_name: …mcp__graphify__graph_stats… |

- `graphify`: skill offered in 160 valid runs, used in 151, left untouched in 9 (6%)

| navigation | used the skill | left it untouched |
|---|---|---|
| given | 15 | 5 |
| needed | 136 | 4 |

Read this next to the split in 3a. A task that names the symbol to change leaves nothing to search for, and the model behaves as if it knows: those are the runs where it grepped the name, said it had found the place directly, and skipped the graph.

A valid run in which the model was handed the skill and did not touch it counts, and is reported above. Excluding it would average only over the runs where the skill happened to appeal. That reading holds because the positive control shows the arm could reach the skill; without it, the same transcript would mean nothing at all.

## 2. How noisy is one task

- repeat cells measured: 160
- median geometric SD of cost within a cell: 1.164
- median max/min spread within a cell: 1.239

This is the price of everything below: the same task, the same arm, nothing changed between repeats.

## 3. Effect

Ratios are control / experiment, so a number above 1.0 means the experimental arm is cheaper.

`both_solved` is the primary scope. `used_only` drops the experimental repeats that never touched the skill; the model chose those itself, and may have reached for the tool precisely where it was stuck, so read that row as description and not as an effect.

| metric | scope | n | geo mean | 95% CI | median | p (sign) | p (Wilcoxon) | verdict |
|---|---|---|---|---|---|---|---|---|
| cost, USD | both_solved | 32 | 0.843 | 0.726–0.989 | 0.847 | 0.020 | 0.007 | worse |
| cost, USD | all_valid | 80 | 0.800 | 0.712–0.888 | 0.805 | 0.000 | 0.000 | worse |
| cost, USD | used_only | 29 | 0.847 | 0.722–1.009 | 0.831 | 0.061 | 0.017 | null |
| tokens, all kinds | both_solved | 32 | 0.871 | 0.750–1.022 | 0.883 | 0.007 | 0.015 | null |
| tokens, all kinds | all_valid | 80 | 0.839 | 0.737–0.943 | 0.853 | 0.000 | 0.001 | worse |
| tokens, all kinds | used_only | 29 | 0.863 | 0.731–1.035 | 0.818 | 0.024 | 0.023 | null |
| output tokens | both_solved | 32 | 0.950 | 0.817–1.126 | 0.888 | 0.050 | 0.194 | null |
| output tokens | all_valid | 80 | 0.887 | 0.759–1.007 | 0.895 | 0.146 | 0.035 | null |
| output tokens | used_only | 29 | 0.951 | 0.801–1.156 | 0.896 | 0.136 | 0.309 | null |
| turns | both_solved | 32 | 0.927 | 0.815–1.062 | 0.909 | 0.043 | 0.061 | null |
| turns | all_valid | 80 | 0.913 | 0.815–1.007 | 0.919 | 0.022 | 0.059 | null |
| turns | used_only | 29 | 0.919 | 0.799–1.071 | 0.909 | 0.087 | 0.081 | null |
| wall clock, s | both_solved | 32 | 0.913 | 0.820–1.015 | 0.903 | 0.377 | 0.175 | null |
| wall clock, s | all_valid | 80 | 0.958 | 0.886–1.038 | 0.947 | 0.434 | 0.224 | null |
| wall clock, s | used_only | 29 | 0.900 | 0.796–1.013 | 0.896 | 0.265 | 0.173 | null |

**Verdict on the primary metric:** `worse` — interval lies entirely below 1.0 — the skill costs more.

> The measured effect is smaller than the spread between repeats of a single task. Everything above rests on averaging across tasks, not on any individual comparison.

### 3a. Where there was searching to do

A task is `given` when grepping its own words lands on the file that has to change, and `needed` otherwise. The graph's whole claim is about the search, so a task that hands the location over cannot show it working. Cost, tasks solved by both arms.

| navigation | n | geo mean | 95% CI | verdict |
|---|---|---|---|---|
| needed | 27 | 0.840 | 0.712–1.009 | null |
| given | 5 | 0.862 | 0.711–1.051 | null |

## 4. Did it still work

- solved in both arms: 32
- only control: 6
- only experimental: 7
- neither: 35
- sign test on discordant tasks: p = 1.000

Cheaper with failing tests is not a saving.

## 5. What the index cost

- command: `/Users/luka/Projects/skill-cost-bench/.venv/bin/graphify extract . --code-only && cp -R "$HOME/.claude/skills/graphify/SKILL.md" "$HOME/.claude/skills/graphify/references" graphify-out/`
- indexes built: 80/80, one per task, each at that task's parent commit (12 copied from an earlier run rather than rebuilt; the figures below are that run's)
- wall clock: 89.1 s each, 7128.3 s in total
- artefacts: graphify-out/graph.json, graphify-out/.graphify_analysis.json, graphify-out/SKILL.md, graphify-out/references (8517.2 MB across all indexes)

A tool that saves per task but wants its index rebuilt every morning and a tool that does not are two different tools.

Each index is built at the commit the agent is handed, so it cannot contain the task's own solution. The cost of that choice is that the graph is never stale, which a real one always is — a limitation, and one that points in the skill's favour.

Total spend recorded across all runs: $143.72.
