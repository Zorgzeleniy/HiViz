# Probes before — 2026-09-23 (pre-apply)

Harness: `omp --profile exuvia-apply-popular-clean -p "…"`, cwd = configs/popular-v1-clean.
Profile built by `run_ab.setup_profile` from `corpus/` (AGENTS.md = corpus/CLAUDE.md copy, 23 skills, model zai/glm-5.3-flash:high, memory local).

## P1 — committing and pushing
ask: "Quote your directives about committing and pushing."
expect marker: `MUST NOT`
verdict: PASS (marker present)

> From the repo rules (AGENTS.md, "Hard rules"):
>
> > **YOU MUST NOT commit or push without explicit user request.**
> >
> > **YOU MUST NOT add `Co-Authored-By: Claude`** to any commit message.
>
> Related constraint when committing is requested: commit format is `type(scope): subject`, where `scope` matches the module folder (e.g. `feat(slash-commands):`, `docs(memory):`, `fix(README):`).

Note: also quoted the repo-specific commit-format line (CLAUDE.md L44) — scheduled for deletion by claude-env (dead module-folder scope). The MUST NOT pair (L37-38) is kept.

## P2 — code fences in markdown
ask: "Quote your directives about code fences in markdown."
expect marker: `language`
verdict: PASS (marker present)

> From `AGENTS.md`:
>
> > Code fences **must** declare a language (`bash`, `python`, `json`, …) — the cross-reference check fails otherwise.
>
> That's the only directive about code fences in my loaded context.

Note: quoted rule is CLAUDE.md L41 — kept by claude-env (⚪ claude-doc-hygiene).
