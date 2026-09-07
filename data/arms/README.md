# What each arm was given

The experimental treatment is the whole experiment, so it belongs in the
repository rather than in a transcript a reader has to reconstruct it from.
These are the exact files the published runs used, copied verbatim from the
gitignored `.arms/` working directory.

| file | used by | what it is |
|---|---|---|
| `graphify-SKILL.natural.md` | `data/pilot` | The skill's description plus a pointer to its full text in the working tree. This is how Claude Code loads a skill in normal use: the description stays in context, the 41KB body is read on demand. |
| `graphify-SKILL.forced.md` | `data/forced`, `data/main` | The same file plus a `<required_procedure>` block that makes the first tool call a graph query. Mine, not the vendor's. It is the treatment behind the 0.843 headline. |
| `graphify-mcp.json` | both | The MCP server the experimental arm was handed. `<repo>` stands for the checkout path. |

`diff graphify-SKILL.natural.md graphify-SKILL.forced.md` is the whole
difference between the run where the model never touched the graph and the run
where it was made to.

## What this is not

Neither file is how the tool ships. `graphify install --project` writes a
CLAUDE.md section and two PreToolUse hooks that push "you MUST query the graph
before reading source files" into the session ahead of every read, glob, grep
and search; `--strict` refuses the first raw read of a session outright. The
published runs had none of that: the arms were built by this harness, and the
forced procedure is my own stand-in for a mechanism the product already has.
`config-superset-stock.yaml` runs the installed article instead; its results are
in `data/stock/`. There is no prompt file for that sweep because the harness
wrote none: the installer's own `CLAUDE.md` section and `.claude/settings.json`
hooks are the treatment, and both are reproduced by running
`graphify install --project` (or `--project --strict`) against graphify 0.9.34.

## Versions

| what | version |
|---|---|
| graphify | 0.9.34 (`pip install graphifyy`) |
| Claude Code | 2.1.220 headless |
| model | `claude-sonnet-5`, reasoning effort `low` |
| target | apache/superset, tasks dated 2026-07-18 to 2026-08-06 |

The commands that produced each directory are in `RUNBOOK.md`.
