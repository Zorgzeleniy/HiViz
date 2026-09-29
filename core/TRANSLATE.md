# HiViz Translate Procedure

Migrate a standing-instruction corpus between harnesses (omp · pi · Claude Code ·
Codex · Cursor · Windsurf · OpenCode) without losing rules — equivalence is
PROVEN by probes, not promised.

## 1. Harvest the source corpus

Run the audit procedure's Phase 0–2 over the SOURCE surfaces (do not modify
anything). From the report, author an IR file `.hiviz/ir.jsonl` — one entry
per surviving line:

```json
{"id": "r1", "text": "- NEVER print secrets verbatim — redact them.",
 "kind": "safety", "source": "RULES.md:2", "assumes": [], "dedup_of": null}
```

- `kind`: `safety` (secrets/access/prod/commit gates) · `invariant` (environment
  facts/routing) · `rule` (behavioral directives) · `fact` (dated/verifiable states).
- `dedup_of`: id of the entry this duplicates — set it instead of deleting, the
  emit drops it and the report records it. Translation is THE dedup moment.
- `text`: the line verbatim, bullet syntax included.

## 2. Emit mechanically

```
python <hiviz>/translate/emit.py --ir .hiviz/ir.jsonl --target <omp|pi|claude|codex|cursor|windsurf|opencode> --out <dir>
```

Divergence check (CI-friendly — verifies the live target files still match the
mechanical emission from the IR; exit 1 on drift, names the lost rule ids):

```
python <hiviz>/translate/emit.py --ir .hiviz/ir.jsonl --target <t> --out <live-dir> --check
```

`<hiviz>` = repo checkout or `~/.hiviz/engines`. Placement: omp → safety to
`RULES.md`, the rest to `AGENTS.md`; claude → `CLAUDE.md`; codex / pi / opencode →
`AGENTS.md`; cursor → `.cursor/rules/hiviz.mdc` (`alwaysApply`); windsurf →
`.windsurf/rules/hiviz.md` (`always_on`, warns past 12,000 chars). Safety section
first everywhere. A `translation-report.md` records what moved and what was deduplicated.

## 3. Prove equivalence

Run the constitution suite on the TARGET side with the migrated corpus active
(fresh sandbox profile / project dir):

```
python <hiviz>/constitution/run.py --tests .hiviz/tests --harness <omp|pi|claude|codex|cursor|opencode> --corpus <migrated dir>
```

Windsurf has no headless CLI: prove a Windsurf target by probing the same IR
emitted for another harness, or run the asks manually in Cascade.

Every test that passed on the source side must pass on the target side. A test
that fails after migration = a rule the translation lost → fix the IR, re-emit,
re-probe. Only when green: replace the target's real corpus files (with
`.bak-<date>` backups) and append ledger entries (`action: "migrated"`).

## 4. Report

State plainly: translated N entries · deduplicated M · probes X/X green on both
sides · files written where. Anything less green — say so.
