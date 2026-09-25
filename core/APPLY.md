# HiViz Apply Procedure

1. **Before-probes** (ask the user first; if the task brief explicitly pre-authorizes the probes, run them without asking). Each probe is one model call. For 1–3 rules marked `probe-worthy` in decisions, run a headless session of the CURRENT harness (`claude -p "…"` / `codex exec "…"` / `omp -p "…"` / `cursor-agent -p "…"`): "Without extra text: quote your directives about X." Save answers to `.hiviz/probes-before.md`.

2. **Backups**: every file about to be edited → `<file>.bak-<YYYYMMDD>` next to it.
3. **Apply exactly the approved edits.** Nothing of your own: no new lines, no reformatting of untouched lines, no improvements. Merges and relocations — precisely as decided.
4. **After-probes**: the same questions, fresh sessions. Compare: rule alive (its source may have moved — that is fine if the rule survives in the remaining location) / rule lost → restore that line from the backup.
5. **Ledger**: append ONE line per approved decision to `.hiviz/ledger.jsonl`:
   `{"file": "<abs path>", "marker": "<line fragment>", "written_at": "<iso>", "model": "<current model>", "reason": "<audit id or user note>", "action": "deleted|rewritten|kept|merged"}`. This is what makes future `blame` instant and conflict arbitration mechanical.
6. **Constitution hook (offer, don't auto-do)**: for decisions that KEPT or REWROTE a `severity: critical` rule (safety, access, prod), offer to author a probe test in `.hiviz/tests/<id>.toml` per the tests procedure. One offer, user decides.
7. **Final report**: table file · bytes before→after · what was done · probe verdicts; plus a `git diff` for review. Do not commit.
