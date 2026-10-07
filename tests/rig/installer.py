"""T1: installer / uninstall / plugin-tree checks (hermetic fake $HOME per harness)."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path


from .core import OUT, REPO, check, fresh_home, home_env, sh


SKILL_NAMES = ["audit", "apply", "drift", "constitution", "blame", "translate"]


CMD_NAMES = ["audit", "apply", "drift", "test", "blame", "translate"]


SHARED_SKILLS = [f".agents/skills/hv-{n}/SKILL.md" for n in SKILL_NAMES]


HARNESS_MARKERS = {"claude": ".claude", "codex": ".codex", "omp": ".omp/agent", "pi": ".pi/agent",
                   "cursor": ".cursor", "windsurf": ".codeium/windsurf", "opencode": ".config/opencode"}


EXPECTED = {
    "claude": [f".claude/commands/hv-{n}.md" for n in CMD_NAMES],
    "codex": SHARED_SKILLS,
    "omp": [f".omp/agent/skills/hv-{n}/SKILL.md" for n in SKILL_NAMES],
    "pi": SHARED_SKILLS,
    "cursor": SHARED_SKILLS,
    "windsurf": SHARED_SKILLS,
    "opencode": SHARED_SKILLS + [f".config/opencode/commands/hv-{n}.md" for n in CMD_NAMES],
}


def adapter_files(home: Path) -> set[str]:
    roots = [".claude", ".agents", ".omp/agent/skills", ".config/opencode/commands", ".codex", ".cursor/rules"]
    return {f.relative_to(home).as_posix() for r in roots if (home / r).exists()
            for f in (home / r).rglob("*") if f.is_file()}


def installer_checks() -> None:
    audit_src = (REPO / "core/AUDIT.md").read_text(encoding="utf-8")
    for h, marker in HARNESS_MARKERS.items():
        home = fresh_home(f"only-{h}")
        (home / marker).mkdir(parents=True)
        env = home_env(home)
        first = sh(["node", "bin/hiviz.js", "init"], env=env)
        second = sh(["node", "bin/hiviz.js", "init"], env=env)
        want = set(EXPECTED[h])
        got = adapter_files(home)
        missing, extra = sorted(want - got), sorted(got - want)
        unrendered = [w for w in want & got if "{{" in (home / w).read_text(encoding="utf-8")]
        eng = home / ".hiviz/engines/core/AUDIT.md"
        idem = " + " not in second.stdout and " - removed" not in second.stdout
        ok = (first.returncode == 0 and second.returncode == 0 and not missing and not extra
              and not unrendered and idem and eng.exists() and eng.read_text(encoding="utf-8") == audit_src)
        detail = (f"{len(want)} adapters + engines, idempotent" if ok else
                  f"rc={first.returncode}/{second.returncode} missing={missing[:3]} extra={extra[:3]} "
                  f"unrendered={unrendered[:2]} idempotent={idem} engines={eng.exists()} {first.stderr[-80:]}")
        check(f"installer [{h}]: adapters + engines", ok, detail)
        u = sh(["node", "bin/hiviz.js", "uninstall"], env=env)
        left = adapter_files(home)
        check(f"installer [{h}]: uninstall removes everything", u.returncode == 0 and not left
              and not (home / ".hiviz").exists(), f"left: {sorted(left)[:3]}" if left else "")

    # env overrides: the harness lives outside ~ and must be found there
    home = fresh_home("env-overrides")
    for d in ("cc", "cx", "pi-agent"):
        (home / d).mkdir()
    env = home_env(home, CLAUDE_CONFIG_DIR=str(home / "cc"), CODEX_HOME=str(home / "cx"),
                   PI_CODING_AGENT_DIR=str(home / "pi-agent"))
    r = sh(["node", "bin/hiviz.js", "init"], env=env)
    ok = (r.returncode == 0 and (home / "cc/commands/hv-audit.md").exists()
          and not (home / ".claude").exists()
          and "Codex/pi: wrote .agents/skills/hv-audit" in r.stdout.replace("\\", "/"))
    check("installer: CLAUDE_CONFIG_DIR / CODEX_HOME / PI_CODING_AGENT_DIR respected", ok,
          "" if ok else r.stdout[-200:])

    # no harness at all: engines still land (the GitHub Action and CI rely on them)
    home = fresh_home("bare")
    r = sh(["node", "bin/hiviz.js", "init"], env=home_env(home))
    check("installer: engines without any harness", r.returncode == 0
          and (home / ".hiviz/engines/drift/check.py").exists(), r.stdout.strip().splitlines()[0][:80])

    # migration from <=0.7 adapters; user-owned Windsurf rules are never touched
    home = fresh_home("legacy")
    user_rules = "# my own rules\n- keep answers short\n"
    old = "# HiViz Audit Procedure\nold body\n"
    legacy = {".codex/prompts/hv-audit.md": old, ".codex/skills/hv-audit/SKILL.md": old,
              ".cursor/rules/hiviz.mdc": old, ".config/opencode/command/hiviz.md": old,
              ".codeium/windsurf/memories/global_rules.md":
                  "Audit standing instructions for prompt debt (stale facts, duplicates, relics, conflicts). old\n"
                  "- a line the user added later\n"}
    for rel, txt in legacy.items():
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text(txt, encoding="utf-8")
    user_home = fresh_home("windsurf-user-rules")
    (user_home / ".codeium/windsurf/memories").mkdir(parents=True)
    (user_home / ".codeium/windsurf/memories/global_rules.md").write_text(user_rules, encoding="utf-8")
    r1 = sh(["node", "bin/hiviz.js", "init"], env=home_env(home))
    r2 = sh(["node", "bin/hiviz.js", "init"], env=home_env(user_home))
    r3 = sh(["node", "bin/hiviz.js", "uninstall"], env=home_env(user_home))
    leftovers = [rel for rel in legacy if (home / rel).exists()]
    kept = (user_home / ".codeium/windsurf/memories/global_rules.md").read_text(encoding="utf-8")
    bak = home / ".codeium/windsurf/memories/global_rules.md.hiviz-bak"
    bak_ok = bak.exists() and "a line the user added later" in bak.read_text(encoding="utf-8")
    ok = (r1.returncode == r2.returncode == r3.returncode == 0 and not leftovers and kept == user_rules and bak_ok
          and not (home / ".codex/skills").exists() and (home / ".codex").exists())
    check("installer: legacy adapters migrated (old Windsurf rules backed up), user Windsurf rules untouched", ok,
          "" if ok else f"leftovers={leftovers} user_rules_intact={kept == user_rules} backup={bak_ok}")


def tree(home: Path) -> dict[str, bytes]:
    return {f.relative_to(home).as_posix(): f.read_bytes() for f in sorted(home.rglob("*")) if f.is_file()}


def uninstall_checks() -> None:
    """uninstall removes exactly what hiviz wrote: user files, user data and harness dirs survive."""
    home = fresh_home("uninstall")
    for m in (".claude", ".codex", ".omp/agent", ".config/opencode"):
        (home / m).mkdir(parents=True)
    env = home_env(home)
    sh(["node", "bin/hiviz.js", "init"], env=env)
    plants = {
        ".agents/skills/hv-audit/notes.md": "my notes next to the skill\n",
        ".hiviz/ledger.jsonl": '{"file": "AGENTS.md", "action": "kept"}\n',  # audit ran in $HOME
        ".claude/commands/my-own.md": "my command\n",
        ".config/opencode/commands/hv-blame.md": "my own hv-blame, not hiviz\n",
    }
    for rel, txt in plants.items():
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text(txt, encoding="utf-8")
    before = tree(home)
    dry = sh(["node", "bin/hiviz.js", "uninstall", "--dry"], env=env)
    check("uninstall --dry changes nothing", dry.returncode == 0 and tree(home) == before
          and "would remove" in dry.stdout, dry.stdout.strip().splitlines()[0][:80] if dry.stdout else dry.stderr[-80:])

    u = sh(["node", "bin/hiviz.js", "uninstall"], env=env)
    after = tree(home)
    ours = [rel for rel in before if rel not in plants]
    left_ours = [rel for rel in ours if rel in after]
    lost = [rel for rel in plants if after.get(rel) != before[rel]]
    dirs_ok = all((home / m).is_dir() for m in (".claude", ".codex", ".omp/agent", ".config/opencode"))
    pruned = not (home / ".agents/skills/hv-drift").exists() and not (home / ".omp/agent/skills").exists() \
        and not (home / ".hiviz/engines").exists()
    check("uninstall: removes every hiviz file, keeps user files/data and harness dirs, prunes empty dirs",
          u.returncode == 0 and not left_ours and not lost and dirs_ok and pruned
          and "kept ~/.hiviz/" in u.stdout and "not written by hiviz" in u.stdout,
          f"left={left_ours[:3]} lost={lost} harness_dirs={dirs_ok} pruned={pruned}")

    for rel in plants:
        (home / rel).unlink()
    sh(["node", "bin/hiviz.js", "uninstall"], env=env)
    gone = [d for d in (".agents", ".hiviz", ".config/opencode/commands") if (home / d).exists()]
    again = sh(["node", "bin/hiviz.js", "uninstall"], env=env)
    check("uninstall: empty leftovers pruned, second run is a no-op", not gone and "nothing to remove" in again.stdout
          and " - " not in again.stdout, f"left dirs={gone} out={again.stdout.strip()[:80]}")

    # init mirrors the engines: files a new version dropped are deleted, python caches untouched
    home = fresh_home("engines-sync")
    env = home_env(home)
    sh(["node", "bin/hiviz.js", "init"], env=env)
    stale = home / ".hiviz/engines/drift/obsolete.py"
    cache = home / ".hiviz/engines/drift/__pycache__/check.cpython-313.pyc"
    for f in (stale, cache):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x", encoding="utf-8")
    r = sh(["node", "bin/hiviz.js", "init"], env=env)
    r2 = sh(["node", "bin/hiviz.js", "init"], env=env)
    check("installer: engines mirrored (dropped files deleted, __pycache__ kept, idempotent)",
          not stale.exists() and cache.exists() and "1 removed" in r.stdout and "= engines" in r2.stdout,
          r.stdout.strip().splitlines()[-1][:90] if r.stdout.strip() else r.stderr[-90:])


def uninstall_edge_checks() -> None:
    """Symlinked skill dirs and permission errors."""
    # symlinks: never followed into someone else's store, never unlinked, never crash
    home = fresh_home("symlinks")
    (home / ".codex").mkdir()
    (home / "dotfiles/agents").mkdir(parents=True)
    (home / ".agents").symlink_to(home / "dotfiles/agents", target_is_directory=True)
    sh(["node", "bin/hiviz.js", "init"], env=home_env(home))
    store = home / "store/hv-audit"
    store.mkdir(parents=True)
    shutil.move(str(home / "dotfiles/agents/skills/hv-audit/SKILL.md"), str(store / "SKILL.md"))
    (home / "dotfiles/agents/skills/hv-audit").rmdir()
    (home / "dotfiles/agents/skills/hv-audit").symlink_to(store, target_is_directory=True)
    u = sh(["node", "bin/hiviz.js", "uninstall"], env=home_env(home))
    real_left = sorted(pp.name for pp in (home / "dotfiles/agents/skills").iterdir()) \
        if (home / "dotfiles/agents/skills").exists() else []
    ok = (u.returncode == 0 and "Error" not in u.stderr and (home / ".agents").is_symlink()
          and (store / "SKILL.md").exists() and real_left == ["hv-audit"]
          and (home / "dotfiles/agents/skills/hv-audit").is_symlink())
    check("uninstall: symlinked ~/.agents and symlinked skill dirs handled (no crash, links and stores intact)",
          ok, f"rc={u.returncode} left={real_left} {u.stderr.strip()[-80:]}")

    if os.name == "nt":
        return  # ponytail: chmod-mode locks do not hold on Windows dirs (node deletes through them) — POSIX-only check
    home = fresh_home("eacces")
    (home / ".claude").mkdir()
    (home / ".codex").mkdir()
    sh(["node", "bin/hiviz.js", "init"], env=home_env(home))
    locked = home / ".claude/commands"
    cmd = ["node", "bin/hiviz.js", "uninstall"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        if not shutil.which("runuser"):
            return
        for pth in [home, *home.rglob("*")]:
            os.chown(pth, 65534, 65534)
        os.chown(locked, 0, 0)
        # runuser resets HOME/PATH, so pass both explicitly
        cmd = ["runuser", "-u", "nobody", "--", "env", f"HOME={home}", shutil.which("node") or "node", *cmd[1:]]
    locked.chmod(0o555)
    try:
        u = sh(cmd, env=home_env(home))
    finally:
        locked.chmod(0o755)
    ok = (u.returncode == 1 and "FAILED to remove" in u.stdout and "Error:" not in u.stderr
          and not (home / ".agents").exists() and (locked / "hv-audit.md").exists())
    check("uninstall: permission errors reported per file, exit 1, everything else still removed", ok,
          f"rc={u.returncode} {(u.stderr or u.stdout).strip()[-100:]}")


def plugin_install_checks() -> None:
    """A marketplace-installed plugin makes the npm adapters redundant — init must not duplicate them."""
    home = fresh_home("plugin-installed")
    for m in (".claude", ".codex", ".omp/agent", ".pi/agent"):
        (home / m).mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"hiviz@hiviz": True}}), encoding="utf-8")
    (home / ".omp/plugins").mkdir(parents=True)
    (home / ".omp/plugins/installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"hiviz@hiviz": [{"scope": "user"}]}}), encoding="utf-8")
    (home / ".codex/config.toml").write_text('model = "x"\n\n[plugins."hiviz@hiviz"]\nenabled = true\n', encoding="utf-8")
    (home / ".pi/agent/settings.json").write_text(json.dumps({"packages": ["npm:@zorgzeleniy/hiviz"]}), encoding="utf-8")
    env = home_env(home)
    planted = {".claude/settings.json", ".codex/config.toml"}
    r = sh(["node", "bin/hiviz.js", "init"], env=env)
    written = sorted(adapter_files(home) - planted)
    check("installer: skips harnesses that have the hiviz plugin (Claude, omp, Codex, pi)",
          r.returncode == 0 and not written and r.stdout.count("adapters not needed") == 4,
          f"written={written[:3]}")
    u = sh(["node", "bin/hiviz.js", "uninstall"], env=env)
    check("uninstall: points at each harness's plugin manager instead of touching plugin files",
          all(s in u.stdout for s in ("/plugin uninstall hiviz@hiviz", "pi remove npm:@zorgzeleniy/hiviz",
                                      "codex plugin remove hiviz@hiviz")), u.stdout.strip().replace("\n", " | ")[-120:])
    # Codex plugin disabled + Windsurf needs the shared skills → written, with a duplicate warning only when enabled
    home = fresh_home("plugin-partial")
    for m in (".codex", ".codeium/windsurf"):
        (home / m).mkdir(parents=True)
    (home / ".codex/config.toml").write_text('[plugins."hiviz@hiviz"]\n', encoding="utf-8")
    r = sh(["node", "bin/hiviz.js", "init"], env=home_env(home))
    check("installer: shared skills still written when another harness needs them (duplicate warned)",
          (home / ".agents/skills/hv-audit/SKILL.md").exists() and "Codex will list the hiviz skills twice" in r.stdout,
          r.stdout.strip().splitlines()[0][:90])


def plugin_checks() -> None:
    """The committed marketplace plugin is current, consistent across catalogs, and self-contained."""
    b = sh(["node", "scripts/build-plugin.js", "--check"])
    check("plugin: committed plugin/ + catalogs match core/, templates/ and engines", b.returncode == 0,
          (b.stdout or b.stderr).strip().splitlines()[-1][:120] if (b.stdout or b.stderr).strip() else "")
    pkg = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    plug = REPO / "plugin"
    errs = []
    try:
        cat = {
            "claude": json.loads((REPO / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")),
            "codex": json.loads((REPO / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")),
            "cursor": json.loads((REPO / ".cursor-plugin/marketplace.json").read_text(encoding="utf-8")),
        }
        srcs = {"claude": cat["claude"]["plugins"][0]["source"], "codex": cat["codex"]["plugins"][0]["source"]["path"],
                "cursor": cat["cursor"]["plugins"][0]["source"]}
        for h, src in srcs.items():
            if (REPO / src).resolve() != plug.resolve() or ".." in src:
                errs.append(f"{h} source {src}")
            if cat[h]["plugins"][0]["name"] != "hiviz":
                errs.append(f"{h} entry name")
        for m in ("plugin.json", ".claude-plugin/plugin.json"):
            man = json.loads((plug / m).read_text(encoding="utf-8"))
            if man.get("name") != "hiviz" or man.get("version") != pkg["version"]:
                errs.append(f"{m} name/version")
        if not json.loads((plug / "plugin.json").read_text(encoding="utf-8")).get("$schema", "").startswith(
                "https://agent-plugins.org/schemas/"):
            errs.append("plugin.json $schema")
    except (OSError, KeyError, IndexError, json.JSONDecodeError) as e:
        errs.append(f"{type(e).__name__}: {e}")
    skills = sorted(plug.glob("skills/*/SKILL.md"))
    for sk in skills:
        m = re.search(r"^name:\s*(\S+)", sk.read_text(encoding="utf-8"), re.M)
        if not m or m.group(1) != sk.parent.name:
            errs.append(f"skill name != dir: {sk.parent.name}")
        if not (sk.parent / "../../engines/drift/check.py").resolve().exists():
            errs.append(f"engines not reachable from {sk.parent.name}")
    pi_skills = [REPO / d for d in pkg.get("pi", {}).get("skills", [])]
    if len(skills) != 6 or [d.resolve() for d in pi_skills] != [(plug / "skills").resolve()]:
        errs.append(f"skills={len(skills)} pi.skills={pkg.get('pi')}")
    if "pi-package" not in pkg.get("keywords", []) or "plugin/" not in pkg.get("files", []):
        errs.append("package.json pi-package keyword / files")
    check("plugin: Claude/omp, Codex, Cursor catalogs + pi package point at one consistent plugin", not errs,
          "; ".join(errs)[:160] if errs else f"6 skills, v{pkg['version']}")
    # engines inside the plugin run on their own (no imports reaching back into the repo)
    d = sh([sys.executable, "plugin/engines/drift/check.py", "--facts", "tests/fixture/hiviz/facts.toml",
            "--base", "tests/fixture", "--mcp-footprint", "tests/fixture/hiviz/mcp_footprint.json",
            "--out", "tests/out/drift_plugin.json"], cwd=REPO)
    same = d.returncode == 1 and (OUT / "drift_plugin.json").exists() and \
        json.loads((OUT / "drift_plugin.json").read_text(encoding="utf-8")) == \
        json.loads((OUT / "drift.json").read_text(encoding="utf-8"))
    check("plugin: bundled engines run self-contained (drift result identical)", same, d.stderr.strip()[-100:])
    if shutil.which("npm"):
        n = sh(["npm", "pack", "--dry-run", "--json"], timeout=120)
        try:
            data = json.loads(n.stdout)
            manifests = data if isinstance(data, list) else list(data.values())  # npm>=11 emits {name: {...}}
            packed = {f["path"] for f in manifests[0]["files"]}
        except (json.JSONDecodeError, IndexError, KeyError, AttributeError):
            packed = set()
        need = {"plugin/skills/hv-audit/SKILL.md", "plugin/engines/drift/check.py", "bin/hiviz.js", "core/AUDIT.md"}
        check("plugin: npm tarball carries the plugin for `pi install npm:…`", need <= packed,
              f"missing={sorted(need - packed)}" if packed else n.stderr.strip()[-100:])
