# HiViz Blame Procedure

`blame` answers provenance questions about instruction lines: when written, by
which model, in which session, why (ledger), still verified (constitution).

## Run
```
python <hiviz>/blame/blame.py --file <path> [--line N | --marker "text fragment"]
  [--sessions <dir> ...] [--ledger .hiviz/ledger.jsonl]
  [--constitution .hiviz/constitution.json]
```

`<hiviz>` = the hiviz engines dir, first that exists: `engines/` two levels above this skill's `SKILL.md` (plugin installs: `<skill dir>/../../engines`), `~/.hiviz/engines` (npm installer), or a hiviz repo checkout. It contains `drift/check.py`.

Sources, in order of trust:
1. **ledger** (`.hiviz/ledger.jsonl`) — entries hiviz itself wrote during
   ingest/apply: `file · marker · written_at · model · reason · action`.
2. **session logs** — mined edit/write/apply_patch tool calls from harness
   session histories, all scanned by default: omp `~/.omp/agent/sessions`, pi
   `~/.pi/agent/sessions`, Claude Code `~/.claude/projects`, Codex
   `~/.codex/sessions` (`PI_CODING_AGENT_DIR` / `CLAUDE_CONFIG_DIR` / `CODEX_HOME`
   honored; `--sessions <dir>` replaces the defaults). Events carry timestamp,
   model, session title, and a `TOUCHED THIS LINE` flag when the payload
   contains the marker text. Cursor, Windsurf and OpenCode keep no minable
   JSONL history — rely on the ledger there.

## Interpretation

- `ledger` beats `history`: the ledger is a first-class record; mined events
  are reconstruction (edits that only moved surrounding lines will not carry
  the TOUCHED flag — that is correct, not a miss).
- When two lines conflict, the one with **fresher provenance and a non-FAILED
  verification** wins. State this explicitly when proposing conflict resolutions.
- Pre-hiviz corpora show "(no entry — pre-hiviz history only)" — mine the
  session logs; if they predate logging too, say `unknown origin` honestly.

