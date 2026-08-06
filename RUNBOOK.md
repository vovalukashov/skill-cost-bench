# Runbook

Everything below runs locally. The only steps that cost money are `preflight.py`
and `run_bench.py`.

## 0. Install

```bash
python3 -m venv .venv
.venv/bin/pip install pyyaml pytest
```

Python 3.11 or newer. `git` and the `claude` CLI must be on PATH.

Check the harness before pointing it at anything:

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/selftest_stats.py --true-ratio 1.35 --tasks 40 --trials 200
```

The test suite runs the whole pipeline — mining, worktrees, hidden tests,
grading, activation checks, resume, budget cap — against a fake agent, so it
spends nothing. The stats self-test plants a known effect and reports how often
the interval covers it; it should land near 95%.

## 1. Prepare the arms

Both arms run with `--setting-sources "" --strict-mcp-config
--disable-slash-commands`, which strips settings, MCP servers and every skill on
the machine. The experimental arm gets its one skill back explicitly:

```bash
mkdir -p .arms
cp ~/.claude/skills/graphify/SKILL.md .arms/graphify-SKILL.md
cat > .arms/graphify-mcp.json <<'JSON'
{"mcpServers": {"graphify": {"command": "graphify", "args": ["--mcp"]}}}
JSON
```

A `CLAUDE_CONFIG_DIR` per arm looks tidier and does isolate correctly, but a
fresh config directory cannot authenticate — the CLI answers `Not logged in`
and every run returns a zero-token error. If you have a way to authenticate a
separate config directory, use it; otherwise the flags above do the same job.

Check the CLI can log in at all before going further:

```bash
claude -p 'say ready' < /dev/null
```

`OAuth session expired and could not be refreshed` means the sweep would produce
240 zero-token failures. Run `claude` interactively and `/login` first.

## 2. Configure

```bash
cp config.example.yaml config.yaml
```

Set at minimum:

- `target.repo` — absolute path to the repository under test;
- `target.test_cmd` — how its tests run, with `{tests}` where the paths go;
- `target.setup_cmd` — whatever a fresh checkout needs before tests can run
  (`pip install -e .`, `pnpm install --frozen-lockfile`, …);
- `agent.model`, `agent.effort` — identical for both arms, by construction;
- `run.budget_usd` — the sweep stops here and says what it did not run.

## 3. Mine tasks

```bash
.venv/bin/python scripts/build_tasks.py \
    --repo /path/to/repo \
    --test-glob 'tests/**' \
    --test-cmd 'python -m pytest -q {tests}' \
    --since 2025-01-01 --max-tasks 120 \
    --out tasks/tasks.yaml
```

It prints how many commits it rejected and why. Expect to reject far more than
you keep.

## 4. Review the tasks by hand

Open `tasks/tasks.yaml`. For each candidate, ask one question: **could an agent
that has never seen this repository infer the answer from this text alone?**

Reject when the message names the file to change, quotes the fix, or is so terse
("fix tests") that no agent could act on it. Start with the ones flagged
`leak_risk: true`.

Set `review: ok` on the survivors. Leave the rest as they are — they stay in the
manifest as part of the record.

## 5. Verify the tasks

```bash
.venv/bin/python scripts/verify_tasks.py \
    --tasks tasks/tasks.yaml --only-approved \
    --setup-cmd 'pip install -e .[dev]'
```

This runs each task's tests twice, at the commit and at its parent, and writes
`verified:` back into the manifest. Only `ok` tasks enter the sweep. It costs
nothing but time, and the time is worth it: a broken grader looks exactly like a
skill that does not work.

## 6. Preflight

```bash
.venv/bin/python scripts/preflight.py --config config.yaml
```

Two trivial prompts, roughly two cents. It prints, per arm, the tools, MCP
servers and slash commands the session was actually handed. Stop here if an arm
is not what the config claims — every later number would inherit the mistake.

## 7. Dry run

```bash
.venv/bin/python scripts/run_bench.py --config config.yaml --dry-run
```

Writes `plan.json` with every run in the order it will execute. Spends nothing.

## 8. Pilot

Set `run.repeats: 3` and `run.max_tasks: 12`, then:

```bash
.venv/bin/python scripts/run_bench.py --config config.yaml
```

72 runs. Interrupting is safe: rerun the same command and it resumes. Analyse:

```bash
.venv/bin/python scripts/analyze.py --config config.yaml --out out/<STAMP>-<name>
```

Read `report.md` top down. Section 1 is the share of invalid runs; if the
experimental arm has many, fix the wiring before reading anything else. Section 2
is the repeat-to-repeat noise; if the effect in section 3 is smaller than that,
the pilot has already answered the question and the main run is not worth paying
for.

## 9. Main run

Set `run.repeats: 2`, remove `run.max_tasks`, raise `run.budget_usd`, and run the
same command against a new output directory. Analyse the same way.

## 10. Publishing

The run directory contains the resolved config, the raw `runs.jsonl` including
invalid rows, the transcripts, `summary.json` and `report.md`. `analyze.py`
recomputes every figure from `runs.jsonl` alone, so a reader can rerun it and
disagree with the analysis without rerunning the experiment.

Transcripts contain source code from the repository under test, and the manifest
contains its commit messages. If that repository is not public, neither of those
may be published. Publish the harness and the aggregate report; keep `tasks/` and
`out/` out of the public repository.

## Troubleshooting

**Every experimental run is invalid with `skill never activated`.** The skill was
offered but never used, or `activation_patterns` do not match what it actually
emits. Read a transcript in `out/<STAMP>/transcripts/` and check which is true.
The distinction matters: the first is a finding about the skill, the second is a
bug in the config.

**`arm was not configured as declared`.** `preflight.py` prints exactly what the
session saw. Usually a wrong `CLAUDE_CONFIG_DIR` or an MCP server that failed to
start.

**Grading fails for every task.** Run `verify_tasks.py` without `--only-approved`
and look at the tally. A `fails_at_commit` majority means `setup_cmd` is not
producing a working environment.

**Worktrees pile up.** `git -C <repo> worktree prune`, then delete
`target.worktree_root`. The harness prunes on its own, but a hard kill can leave
one behind.
