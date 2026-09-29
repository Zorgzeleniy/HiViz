---
name: hv-drift
description: "Deterministic drift check: standing instructions vs the live environment. Reads .hiviz/facts.toml, runs checkers (file_exists/file_contains/dir_glob/shell/port_open), reports OK/STALE/UNVERIFIABLE. Triggers on: instruction drift, are my AGENTS.md facts stale, environment mismatch, 'факты протухли'. STALE = prompt debt — propose resolutions, human decides."
---

# HiViz Drift Procedure

Drift = standing instructions that no longer match the environment. This
procedure is deterministic-first: the machine judges, the model only drafts.

## 1. Run the registry
```
python <hiviz>/drift/check.py --facts .hiviz/facts.toml --base <repo-or-profile-root>
```

`<hiviz>` = the hiviz engines dir, first that exists: `engines/` two levels above this skill's `SKILL.md` (plugin installs: `<skill dir>/../../engines`), `~/.hiviz/engines` (npm installer), or a hiviz repo checkout. It contains `drift/check.py`.

Statuses: `OK` (fact holds) · `STALE` (fact contradicts the environment — this
is prompt debt) · `UNVERIFIABLE` (no check defined) · `ERROR` (checker broke).

MCP pay-vs-use is picked up automatically: if `<base>/.hiviz/mcp_footprint.json` exists (written by meters during audit, or manually), every server becomes a fact — `mcp:<server>` — STALE when its standing token cost meets no usage (0 calls, or last used older than `--mcp-stale-days`, default 30; threshold `--mcp-min-tokens`, default 500).

## 2. Read the STALE table, propose resolutions

For every STALE row: find the instruction lines that assume this fact (grep the
corpus for the fact's keywords), and write the contradiction explicitly:

> instruction says: <line, file>
> environment says: <checker detail>

Propose ONE of: update the instruction line · delete it · update the fact
checker (if the environment, not the instruction, is the anomaly). **Do not
apply anything** — output the table plus proposals to `.hiviz/drift-report.md`.

## 3. Draft facts for UNVERIFIABLE assumptions (ingest)

Scan instruction surfaces for environment assumptions that have no registry
entry (paths, versions, ports, installed tools, host addresses). For each,
append a draft to `.hiviz/facts.toml`:

```toml
[facts.<kebab-id>]
description = "<what the instructions assume>"
check = { type = "file_exists|file_contains|dir_glob|shell|port_open", ... }
```

Draft conservative checkers (shell only when a cheaper type cannot express it).
Then re-run step 1 and show the new table. Never invent facts about the
environment you have not checked.

## 4. Human decides

The drift report is a decision table like any other audit: the user approves
each proposal; applying goes through the apply procedure (backups, probes).

