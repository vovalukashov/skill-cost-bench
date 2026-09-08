# graphify-superset-stock

Generated 2026-09-08T17:24:42Z. Control arm `control`, experimental arm `graphify-strict`. Advertised factor under test: 70.0x.

## 1. Did the skill run at all

- runs recorded: 320
- invalid: 2 (0.6%)

| reason | runs |
|---|---|
| graphify-strict: agent exited with an error | 2 |

| arm | could reach the skill | evidence |
|---|---|---|
| graphify-stock | yes | tool_input: …aphify-out/ 2>&1; echo \"---\"; test -f graphify-out/graph.json && echo \"graph.json exists\""}… |
| graphify-strict | yes | tool_input: …{"command": "graphify query \"what does this codebase do\" 2>&1"}… |

- `graphify-strict`: skill offered in 158 valid runs, used in 150, left untouched in 8 (5%)
  - the skill's own tooling prompted the model in 158 of them; used without any prompt in 0, prompted and still unused in 8
  - `MANDATORY: graphify-out`: 1495 hits, heard in 158 runs
  - `may be STALE`: 50 hits, heard in 30 runs
  - `graphify strict mode`: 82 hits, heard in 41 runs

| navigation | used the skill | left it untouched |
|---|---|---|
| given | 17 | 3 |
| needed | 135 | 5 |

Read this next to the split in 3a. A task that names the symbol to change leaves nothing to search for, and the model behaves as if it knows: those are the runs where it grepped the name, said it had found the place directly, and skipped the graph.

A valid run in which the model was handed the skill and did not touch it counts, and is reported above. Excluding it would average only over the runs where the skill happened to appeal. That reading holds because the positive control shows the arm could reach the skill; without it, the same transcript would mean nothing at all.

## 2. How noisy is one task

- repeat cells measured: 158
- median geometric SD of cost within a cell: 1.182
- median max/min spread within a cell: 1.266

This is the price of everything below: the same task, the same arm, nothing changed between repeats.

## 3. Effect

Ratios are control / experiment, so a number above 1.0 means the experimental arm is cheaper.

`both_solved` is the primary scope. `used_only` drops the experimental repeats that never touched the skill; the model chose those itself, and may have reached for the tool precisely where it was stuck, so read that row as description and not as an effect.

| metric | scope | n | geo mean | 95% CI | median | p (sign) | p (Wilcoxon) | verdict |
|---|---|---|---|---|---|---|---|---|
| cost, USD | both_solved | 28 | 0.792 | 0.724–0.866 | 0.775 | 0.001 | 0.000 | worse |
| cost, USD | all_valid | 80 | 0.858 | 0.771–0.951 | 0.846 | 0.010 | 0.000 | worse |
| cost, USD | used_only | 28 | 0.787 | 0.720–0.861 | 0.761 | 0.001 | 0.000 | worse |
| tokens, all kinds | both_solved | 28 | 0.804 | 0.718–0.900 | 0.793 | 0.013 | 0.002 | worse |
| tokens, all kinds | all_valid | 80 | 0.897 | 0.800–1.005 | 0.881 | 0.018 | 0.012 | null |
| tokens, all kinds | used_only | 28 | 0.804 | 0.719–0.899 | 0.790 | 0.013 | 0.001 | worse |
| output tokens | both_solved | 28 | 0.912 | 0.820–1.014 | 0.932 | 0.345 | 0.108 | null |
| output tokens | all_valid | 80 | 0.934 | 0.806–1.065 | 0.951 | 0.738 | 0.356 | null |
| output tokens | used_only | 28 | 0.917 | 0.827–1.017 | 0.932 | 0.345 | 0.119 | null |
| turns | both_solved | 28 | 0.884 | 0.806–0.967 | 0.882 | 0.029 | 0.013 | worse |
| turns | all_valid | 80 | 0.955 | 0.860–1.058 | 0.947 | 0.248 | 0.199 | null |
| turns | used_only | 28 | 0.886 | 0.810–0.968 | 0.882 | 0.029 | 0.013 | worse |
| wall clock, s | both_solved | 28 | 0.695 | 0.562–0.854 | 0.792 | 0.004 | 0.003 | worse |
| wall clock, s | all_valid | 80 | 0.679 | 0.581–0.791 | 0.780 | 0.000 | 0.000 | worse |
| wall clock, s | used_only | 28 | 0.689 | 0.560–0.845 | 0.762 | 0.004 | 0.002 | worse |

**Verdict on the primary metric:** `worse` — interval lies entirely below 1.0 — the skill costs more.

### 3a. Where there was searching to do

A task is `given` when grepping its own words lands on the file that has to change, and `needed` otherwise. The graph's whole claim is about the search, so a task that hands the location over cannot show it working. Cost, tasks solved by both arms.

| navigation | n | geo mean | 95% CI | verdict |
|---|---|---|---|---|
| needed | 22 | 0.784 | 0.706–0.870 | worse |
| given | 6 | 0.822 | 0.693–0.948 | worse |

## 4. Did it still work

- solved in both arms: 28
- only control: 9
- only experimental: 6
- neither: 37
- sign test on discordant tasks: p = 0.607

Cheaper with failing tests is not a saving.

## 5. What the index cost

- command: `/Users/luka/Projects/skill-cost-bench/.venv/bin/graphify extract . --code-only`
- indexes built: 80/80, one per task, each at that task's parent commit (80 copied from an earlier run rather than rebuilt; the figures below are that run's)
- wall clock: 89.1 s each, 7128.3 s in total
- artefacts: graphify-out/graph.json, graphify-out/.graphify_analysis.json, graphify-out/SKILL.md, graphify-out/references (8517.2 MB across all indexes)

A tool that saves per task but wants its index rebuilt every morning and a tool that does not are two different tools.

Each index is built at the commit the agent is handed, so it cannot contain the task's own solution. The cost of that choice is that the graph is never stale, which a real one always is — a limitation, and one that points in the skill's favour.

Total spend recorded across all runs: $95.69.
