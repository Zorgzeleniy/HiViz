# Installing HiViz

Two ways in, same six skills (`hv-audit`, `hv-apply`, `hv-drift`, `hv-constitution`, `hv-blame`, `hv-translate`) and the same python engines.

## 1. npm installer — every harness

```bash
npx @zorgzeleniy/hiviz init          # install / update (safe to re-run)
npx @zorgzeleniy/hiviz init --dry    # show what it would write
npx @zorgzeleniy/hiviz status        # what is detected and installed
```

It detects each harness by its config dir and writes:

| Harness     | Detected by                          | Gets                                                                 |
| ----------- | ------------------------------------ | -------------------------------------------------------------------- |
| Claude Code | `$CLAUDE_CONFIG_DIR` or `~/.claude`  | slash commands `/hv-audit` … in `<dir>/commands/`                    |
| OpenCode    | `$XDG_CONFIG_HOME/opencode` or `~/.config/opencode` | slash commands in `<dir>/commands/` + the shared skills |
| omp         | `~/.omp/agent`                       | skills in `~/.omp/agent/skills/`                                     |
| Codex       | `$CODEX_HOME` or `~/.codex`          | the shared skills                                                    |
| pi          | `$PI_CODING_AGENT_DIR` or `~/.pi/agent` | the shared skills                                                 |
| Cursor      | `~/.cursor`                          | the shared skills                                                    |
| Windsurf    | `~/.codeium/windsurf`                | the shared skills                                                    |

The shared skills live once in `~/.agents/skills/` — the cross-agent skills dir that Codex, pi, Cursor, Windsurf and OpenCode all read. The engines go to `~/.hiviz/engines/`; `init` mirrors them, so files a new version dropped are deleted.

## 2. The harness's own plugin manager

| Harness     | Install                                                                            | Remove                              |
| ----------- | ---------------------------------------------------------------------------------- | ----------------------------------- |
| Claude Code | `/plugin marketplace add Zorgzeleniy/hiviz` → `/plugin install hiviz@hiviz`        | `/plugin uninstall hiviz@hiviz`     |
| omp         | `/marketplace add Zorgzeleniy/hiviz` → `/marketplace install hiviz@hiviz`          | `/marketplace` → uninstall          |
| Codex       | `codex plugin marketplace add Zorgzeleniy/hiviz` → `codex plugin add hiviz@hiviz`  | `codex plugin remove hiviz@hiviz`   |
| pi          | `pi install npm:@zorgzeleniy/hiviz`                                                | `pi remove npm:@zorgzeleniy/hiviz`  |

The plugin (`plugin/` in this repo) bundles the engines next to the skills, so nothing else is needed. In Claude Code plugin skills are namespaced: `/hiviz:hv-audit`. Cursor Marketplace listing is pending — the repo already ships `.cursor-plugin/marketplace.json` and an Agent Plugins `plugin.json`.

If you use both ways, `hiviz init` notices the plugin and skips that harness, so skills never show up twice. The one exception: when another harness on the machine needs `~/.agents/skills`, Codex or pi will see both copies — `init` warns about it.

## Uninstall

```bash
npx @zorgzeleniy/hiviz uninstall --dry   # preview
npx @zorgzeleniy/hiviz uninstall
```

- Deletes only files hiviz wrote — each one is checked for the HiViz procedure heading — plus `~/.hiviz/engines`.
- Keeps your own files, even inside a hiviz skill dir, and keeps `~/.hiviz/` when it holds your data (ledger, reports from an audit run in `$HOME`).
- Never follows or removes symlinks (e.g. skills linked by `npx skills`), and prunes only the empty dirs it leaves behind; harness config dirs are never removed.
- A file it cannot delete is reported as `FAILED` and the command exits 1; everything else is still removed.
- Plugin installs are not touched — uninstall prints the harness command that removes them.

## Session logs HiViz reads

`hv-blame` and the MCP usage meter mine local session logs: omp `~/.omp/agent/sessions`, pi `~/.pi/agent/sessions`, Claude Code `~/.claude/projects`, Codex `~/.codex/sessions` (env overrides above are honored). Cursor, Windsurf and OpenCode keep no minable JSONL history — there usage shows as unknown, never as zero.
