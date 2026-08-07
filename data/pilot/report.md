# graphify-superset-pilot

Generated 2026-08-06T23:43:34Z. Control arm `control`, experimental arm `graphify`. Advertised factor under test: 70.0x.

## 1. Did the skill run at all

- runs recorded: 72
- invalid: 0 (0.0%)

| arm | could reach the skill | evidence |
|---|---|---|
| graphify | yes | tool_name: …mcp__graphify__graph_stats… |

- `graphify`: skill offered in 36 valid runs, left untouched in 36 of them (100%)

A valid run in which the model was handed the skill and did not touch it counts, and is reported above. Excluding it would average only over the runs where the skill happened to appeal. That reading holds because the positive control shows the arm could reach the skill; without it, the same transcript would mean nothing at all.

## 2. How noisy is one task

- repeat cells measured: 24
- median geometric SD of cost within a cell: 1.340
- median max/min spread within a cell: 1.751

This is the price of everything below: the same task, the same arm, nothing changed between repeats.

## 3. Effect

Ratios are control / experiment, so a number above 1.0 means the experimental arm is cheaper.

`both_solved` is the primary scope. `used_only` drops the experimental repeats that never touched the skill; the model chose those itself, and may have reached for the tool precisely where it was stuck, so read that row as description and not as an effect.

| metric | scope | n | geo mean | 95% CI | median | p (sign) | p (Wilcoxon) | verdict |
|---|---|---|---|---|---|---|---|---|
| cost, USD | both_solved | 7 | 1.010 | 0.855–1.230 | 0.946 | 0.453 | 0.938 | null |
| cost, USD | all_valid | 12 | 1.032 | 0.905–1.188 | 0.999 | 1.000 | 0.791 | null |
| cost, USD | used_only | 0 | — | — | — | — | — | not enough pairs |
| tokens, all kinds | both_solved | 7 | 1.015 | 0.822–1.277 | 1.017 | 1.000 | 0.938 | null |
| tokens, all kinds | all_valid | 12 | 1.033 | 0.885–1.205 | 1.022 | 0.774 | 0.791 | null |
| tokens, all kinds | used_only | 0 | — | — | — | — | — | not enough pairs |
| output tokens | both_solved | 7 | 1.014 | 0.868–1.215 | 0.947 | 1.000 | 1.000 | null |
| output tokens | all_valid | 12 | 1.079 | 0.907–1.305 | 1.012 | 1.000 | 0.569 | null |
| output tokens | used_only | 0 | — | — | — | — | — | not enough pairs |
| turns | both_solved | 7 | 1.046 | 0.863–1.260 | 1.067 | 1.000 | 0.812 | null |
| turns | all_valid | 12 | 1.030 | 0.904–1.169 | 1.033 | 1.000 | 0.765 | null |
| turns | used_only | 0 | — | — | — | — | — | not enough pairs |
| wall clock, s | both_solved | 7 | 1.059 | 0.891–1.288 | 1.026 | 1.000 | 0.688 | null |
| wall clock, s | all_valid | 12 | 1.201 | 0.994–1.480 | 1.058 | 0.146 | 0.110 | null |
| wall clock, s | used_only | 0 | — | — | — | — | — | not enough pairs |

**Verdict on the primary metric:** `null` — interval covers 1.0 — parity cannot be excluded.

> The measured effect is smaller than the spread between repeats of a single task. Everything above rests on averaging across tasks, not on any individual comparison.

## 4. Did it still work

- solved in both arms: 5
- only control: 1
- only experimental: 2
- neither: 4
- sign test on discordant tasks: p = 1.000

Cheaper with failing tests is not a saving.

## 5. What the index cost

- command: `/Users/luka/Projects/skill-cost-bench/.venv/bin/graphify extract . --code-only && cp -R "$HOME/.claude/skills/graphify/SKILL.md" "$HOME/.claude/skills/graphify/references" graphify-out/`
- indexes built: 12/12, one per task, each at that task's parent commit
- wall clock: 90.3 s each, 1083.4 s in total
- artefacts: graphify-out/graph.json, graphify-out/.graphify_analysis.json, graphify-out/SKILL.md, graphify-out/references (1306.8 MB across all indexes)

A tool that saves per task but wants its index rebuilt every morning and a tool that does not are two different tools.

Each index is built at the commit the agent is handed, so it cannot contain the task's own solution. The cost of that choice is that the graph is never stale, which a real one always is — a limitation, and one that points in the skill's favour.

Total spend recorded across all runs: $36.75.
