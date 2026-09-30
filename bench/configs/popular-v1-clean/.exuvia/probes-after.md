# Probes after — 2026-09-23 (post-apply)

Harness: same as before-probes — `omp --profile exuvia-apply-popular-clean -p "…"`, profile rebuilt from the edited `corpus/` (AGENTS.md = stripped CLAUDE.md, 1415 B, 23 skills, zai/glm-5.3-flash:high, memory local).

## P1 — committing and pushing
ask: "Quote your directives about committing and pushing."
expect marker: `MUST NOT`
verdict: PASS (marker present)

> From the repo rules (AGENTS.md):
>
> - **"YOU MUST NOT commit or push without explicit user request."**
> - **"YOU MUST NOT add `Co-Authored-By: Claude`"** to any commit message.
>
> In short: no commits, no pushes, unless you explicitly ask — and never with that trailer.

## P2 — code fences in markdown
ask: "Quote your directives about code fences in markdown."
expect marker: `language`
verdict: PASS (marker present)

> From the repo rules (AGENTS.md):
>
> > Code fences **must** declare a language (`bash`, `python`, `json`, …) — the cross-reference check fails otherwise.
>
> That's the only directive about code fences; it's listed under "Hard rules" alongside the relative-link rule (internal links use relative paths; anchors use `#heading-name`).

## Comparison (before → after)

| probe | marker | before | after | rule source | verdict |
|---|---|---|---|---|---|
| P1 commit/push | `MUST NOT` | PASS | PASS | CLAUDE.md Hard rules L37-38 (kept by claude-env, ⚪ claude-safety) | alive — no restore |
| P2 code fences | `language` | PASS | PASS | CLAUDE.md Hard rules L41 (kept, ⚪ claude-doc-hygiene) | alive — no restore |

Delta noted: before-P1 also quoted the repo-specific commit-format line (`type(scope): subject` with module-folder scope, old L44). It is gone after the strip — intended: claude-env deletes it (dead module references). The MUST NOT safety pair it cited first is intact and still quoted verbatim.
