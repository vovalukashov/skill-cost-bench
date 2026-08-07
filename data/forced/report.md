# graphify-superset-forced

Generated 2026-08-07T09:07:03Z. Control arm `control`, experimental arm `graphify`. Advertised factor under test: 70.0x.

## 1. Did the skill run at all

- runs recorded: 72
- invalid: 0 (0.0%)

| arm | could reach the skill | evidence |
|---|---|---|
| graphify | yes | tool_name: …mcp__graphify__graph_stats… |

- `graphify`: skill offered in 36 valid runs, used in 36, left untouched in 0 (0%)

A valid run in which the model was handed the skill and did not touch it counts, and is reported above. Excluding it would average only over the runs where the skill happened to appeal. That reading holds because the positive control shows the arm could reach the skill; without it, the same transcript would mean nothing at all.

## 2. How noisy is one task

- repeat cells measured: 24
- median geometric SD of cost within a cell: 1.254
- median max/min spread within a cell: 1.530

This is the price of everything below: the same task, the same arm, nothing changed between repeats.

## 3. Effect

Ratios are control / experiment, so a number above 1.0 means the experimental arm is cheaper.

`both_solved` is the primary scope. `used_only` drops the experimental repeats that never touched the skill; the model chose those itself, and may have reached for the tool precisely where it was stuck, so read that row as description and not as an effect.

| metric | scope | n | geo mean | 95% CI | median | p (sign) | p (Wilcoxon) | verdict |
|---|---|---|---|---|---|---|---|---|
| cost, USD | both_solved | 6 | 0.683 | 0.556–0.819 | 0.724 | 0.031 | 0.031 | worse |
| cost, USD | all_valid | 12 | 0.862 | 0.708–1.050 | 0.818 | 0.388 | 0.204 | null |
| cost, USD | used_only | 6 | 0.683 | 0.556–0.819 | 0.724 | 0.031 | 0.031 | worse |
| tokens, all kinds | both_solved | 6 | 0.602 | 0.438–0.831 | 0.557 | 0.219 | 0.094 | worse |
| tokens, all kinds | all_valid | 12 | 0.831 | 0.660–1.047 | 0.878 | 0.388 | 0.151 | null |
| tokens, all kinds | used_only | 6 | 0.602 | 0.438–0.831 | 0.557 | 0.219 | 0.094 | worse |
| output tokens | both_solved | 6 | 0.711 | 0.552–0.881 | 0.748 | 0.219 | 0.062 | worse |
| output tokens | all_valid | 12 | 0.964 | 0.761–1.281 | 0.815 | 0.388 | 0.339 | null |
| output tokens | used_only | 6 | 0.711 | 0.552–0.881 | 0.748 | 0.219 | 0.062 | worse |
| turns | both_solved | 6 | 0.680 | 0.531–0.884 | 0.659 | 0.219 | 0.058 | worse |
| turns | all_valid | 12 | 0.897 | 0.751–1.075 | 0.920 | 0.754 | 0.221 | null |
| turns | used_only | 6 | 0.680 | 0.531–0.884 | 0.659 | 0.219 | 0.058 | worse |
| wall clock, s | both_solved | 6 | 0.660 | 0.513–0.786 | 0.712 | 0.031 | 0.031 | worse |
| wall clock, s | all_valid | 12 | 0.868 | 0.722–1.055 | 0.816 | 0.146 | 0.266 | null |
| wall clock, s | used_only | 6 | 0.660 | 0.513–0.786 | 0.712 | 0.031 | 0.031 | worse |

**Verdict on the primary metric:** `worse` — interval lies entirely below 1.0 — the skill costs more.

## 4. Did it still work

- solved in both arms: 5
- only control: 1
- only experimental: 1
- neither: 5
- sign test on discordant tasks: p = 1.000

Cheaper with failing tests is not a saving.

## 5. What the index cost

- command: `/Users/luka/Projects/skill-cost-bench/.venv/bin/graphify extract . --code-only && cp -R "$HOME/.claude/skills/graphify/SKILL.md" "$HOME/.claude/skills/graphify/references" graphify-out/`
- indexes built: 12/12, one per task, each at that task's parent commit (12 copied from an earlier run rather than rebuilt; the figures below are that run's)
- wall clock: 90.3 s each, 1083.4 s in total
- artefacts: graphify-out/graph.json, graphify-out/.graphify_analysis.json, graphify-out/SKILL.md, graphify-out/references (1306.8 MB across all indexes)

A tool that saves per task but wants its index rebuilt every morning and a tool that does not are two different tools.

Each index is built at the commit the agent is handed, so it cannot contain the task's own solution. The cost of that choice is that the graph is never stale, which a real one always is — a limitation, and one that points in the skill's favour.

Total spend recorded across all runs: $34.09.
