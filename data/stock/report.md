# graphify-superset-stock

Generated 2026-09-07T00:05:00Z. Control arm `control`, experimental arm `graphify-stock`. Advertised factor under test: 70.0x.

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

- `graphify-stock`: skill offered in 160 valid runs, used in 116, left untouched in 44 (28%)
  - the skill's own tooling prompted the model in 160 of them; used without any prompt in 0, prompted and still unused in 44

| navigation | used the skill | left it untouched |
|---|---|---|
| given | 14 | 6 |
| needed | 102 | 38 |

Read this next to the split in 3a. A task that names the symbol to change leaves nothing to search for, and the model behaves as if it knows: those are the runs where it grepped the name, said it had found the place directly, and skipped the graph.

A valid run in which the model was handed the skill and did not touch it counts, and is reported above. Excluding it would average only over the runs where the skill happened to appeal. That reading holds because the positive control shows the arm could reach the skill; without it, the same transcript would mean nothing at all.

## 2. How noisy is one task

- repeat cells measured: 159
- median geometric SD of cost within a cell: 1.188
- median max/min spread within a cell: 1.275

This is the price of everything below: the same task, the same arm, nothing changed between repeats.

## 3. Effect

Ratios are control / experiment, so a number above 1.0 means the experimental arm is cheaper.

`both_solved` is the primary scope. `used_only` drops the experimental repeats that never touched the skill; the model chose those itself, and may have reached for the tool precisely where it was stuck, so read that row as description and not as an effect.

| metric | scope | n | geo mean | 95% CI | median | p (sign) | p (Wilcoxon) | verdict |
|---|---|---|---|---|---|---|---|---|
| cost, USD | both_solved | 27 | 0.807 | 0.701–0.914 | 0.817 | 0.006 | 0.002 | worse |
| cost, USD | all_valid | 80 | 0.907 | 0.839–0.979 | 0.897 | 0.010 | 0.008 | worse |
| cost, USD | used_only | 22 | 0.753 | 0.643–0.864 | 0.785 | 0.001 | 0.001 | worse |
| tokens, all kinds | both_solved | 27 | 0.876 | 0.760–0.997 | 0.857 | 0.122 | 0.050 | worse |
| tokens, all kinds | all_valid | 80 | 0.952 | 0.871–1.040 | 0.936 | 0.146 | 0.166 | null |
| tokens, all kinds | used_only | 22 | 0.811 | 0.692–0.926 | 0.843 | 0.004 | 0.005 | worse |
| output tokens | both_solved | 27 | 0.949 | 0.825–1.088 | 0.931 | 0.248 | 0.435 | null |
| output tokens | all_valid | 80 | 1.008 | 0.928–1.094 | 0.967 | 0.576 | 0.824 | null |
| output tokens | used_only | 22 | 0.871 | 0.747–1.010 | 0.852 | 0.052 | 0.048 | null |
| turns | both_solved | 27 | 0.971 | 0.847–1.102 | 0.944 | 1.000 | 0.692 | null |
| turns | all_valid | 80 | 1.004 | 0.929–1.081 | 1.000 | 0.908 | 0.806 | null |
| turns | used_only | 22 | 0.902 | 0.777–1.022 | 0.927 | 0.503 | 0.126 | null |
| wall clock, s | both_solved | 27 | 0.869 | 0.724–1.033 | 0.853 | 0.442 | 0.100 | null |
| wall clock, s | all_valid | 80 | 0.890 | 0.813–0.974 | 0.895 | 0.005 | 0.010 | worse |
| wall clock, s | used_only | 22 | 0.772 | 0.637–0.917 | 0.817 | 0.052 | 0.009 | worse |

**Verdict on the primary metric:** `worse` — interval lies entirely below 1.0 — the skill costs more.

### 3a. Where there was searching to do

A task is `given` when grepping its own words lands on the file that has to change, and `needed` otherwise. The graph's whole claim is about the search, so a task that hands the location over cannot show it working. Cost, tasks solved by both arms.

| navigation | n | geo mean | 95% CI | verdict |
|---|---|---|---|---|
| needed | 22 | 0.798 | 0.672–0.922 | worse |
| given | 5 | 0.851 | 0.712–1.059 | null |

## 4. Did it still work

- solved in both arms: 27
- only control: 9
- only experimental: 10
- neither: 34
- sign test on discordant tasks: p = 1.000

Cheaper with failing tests is not a saving.

## 5. What the index cost

- command: `/Users/luka/Projects/skill-cost-bench/.venv/bin/graphify extract . --code-only`
- indexes built: 80/80, one per task, each at that task's parent commit (80 copied from an earlier run rather than rebuilt; the figures below are that run's)
- wall clock: 89.1 s each, 7128.3 s in total
- artefacts: graphify-out/graph.json, graphify-out/.graphify_analysis.json, graphify-out/SKILL.md, graphify-out/references (8517.2 MB across all indexes)

A tool that saves per task but wants its index rebuilt every morning and a tool that does not are two different tools.

Each index is built at the commit the agent is handed, so it cannot contain the task's own solution. The cost of that choice is that the graph is never stale, which a real one always is — a limitation, and one that points in the skill's favour.

Total spend recorded across all runs: $96.30.
