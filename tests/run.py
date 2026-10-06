#!/usr/bin/env python3
"""hiviz test rig.

T1 (deterministic, free, hermetic — every harness gets its own fake $HOME under tests/out):
   installer per harness, meters vs fake stdio/HTTP MCP, drift, constitution, blame, translate.
T2 (E2E, LLM): audit -> ground-truth check -> deterministic decisions -> apply -> post-asserts.

Usage: python tests/run.py [--t1|--t2|--all]   (default: --all)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "render"))
import hvfmt  # noqa: E402
HOME = Path.home()
OUT = REPO / "tests" / "out"
GT = json.loads((REPO / "tests" / "ground_truth.json").read_text(encoding="utf-8"))
PROFILE = HOME / ".omp/profiles/hiviz-test/agent"
RESULTS: list[tuple[str, bool, str]] = []
_GROUP = [""]
GROUPS: list[str] = []
_SECTION: list[str | None] = [None]


def group_of(name: str) -> str:
    return re.split(r"[ :\[]", name, 1)[0]


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    GROUPS.append(_SECTION[0] or group_of(name))
    if not hvfmt.is_pretty():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        return
    g = GROUPS[-1]
    if g != _GROUP[0]:
        _GROUP[0] = g
        print(hvfmt.style(f"  {g}", "bold"))
    m = None if _SECTION[0] else re.match(rf"{re.escape(g)}( \[[^\]]+\])?: (.*)$", name)
    label = f"{m.group(1).strip() + ' ' if m.group(1) else ''}{m.group(2)}" if m else name
    line = f"    {hvfmt.symbol('PASS' if ok else 'FAIL')} {label}"
    if not ok:  # passing checks stay quiet; their detail is in the md output / failures table
        first = next((l.strip() for l in detail.splitlines() if l.strip()), "")
        room = hvfmt.term_cols() - hvfmt.width(line) - 4
        if first and room > 12:
            line += "  " + hvfmt.style(first if len(first) <= room else first[: room - 1] + "…", "red")
    print(line)

def sh(cmd: list[str], timeout: int = 120, cwd: Path = REPO, **kw) -> subprocess.CompletedProcess:
    exe = shutil.which(cmd[0])  # Windows: npm is npm.cmd, node-installed CLIs need resolving
    if exe:
        cmd = [exe, *cmd[1:]]
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, **kw)
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        return subprocess.CompletedProcess(cmd, 124, "", f"TIMEOUT after {timeout}s; partial stdout: {out[-300:]}")


T2_HARNESS = os.environ.get("HIVIZ_T2_HARNESS", "omp")  # omp | opencode
T2_MODEL = os.environ.get("HIVIZ_T2_MODEL", "opencode/big-pickle")  # opencode only


def agent_cmd(prompt: str) -> list[str]:
    if T2_HARNESS == "opencode":
        return ["opencode", "run", "-m", T2_MODEL, "--dir", str(PROFILE), "--auto", prompt]
    return ["omp", "--profile", "hiviz-test", "-p", prompt]


def probe_hint() -> str:
    if T2_HARNESS == "opencode":
        return f'headless `opencode run -m {T2_MODEL} --dir {PROFILE.as_posix()} --auto "<ask>"`'
    return 'headless `omp --profile hiviz-test -p "<ask>"`'


def templated_copy(src: Path, dst: Path) -> None:
    """Copy a fixture tree, rendering {{REPO}} into the absolute repo path."""
    repo_abs = str(REPO.resolve()).replace("\\", "/")
    for f in sorted(src.rglob("*")):
        if f.is_file():
            d = dst / f.relative_to(src)
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text(f.read_text(encoding="utf-8").replace("{{REPO}}", repo_abs), encoding="utf-8")


HARNESS_ENV = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "PI_CODING_AGENT_DIR", "XDG_CONFIG_HOME",
               "HIVIZ_HARNESS", "CLAUDECODE")


def home_env(home: Path, **extra: str) -> dict:
    """Environment of a fake machine: HOME/USERPROFILE point at `home`, no inherited harness overrides."""
    env = {k: v for k, v in os.environ.items() if k not in HARNESS_ENV}
    env.update(HOME=str(home), USERPROFILE=str(home), **extra)
    return env


def fresh_home(name: str) -> Path:
    home = OUT / "homes" / name
    shutil.rmtree(home, ignore_errors=True)
    home.mkdir(parents=True)
    return home


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


def meters_discovery_check() -> None:
    """Auto-discovery across Claude/Codex/Cursor/Windsurf/OpenCode configs + usage from Claude/Codex logs."""
    sys.path.insert(0, str(REPO / "tests"))
    import fake_mcp_http
    srv, url = fake_mcp_http.start(tools=2, token="t0ken")
    try:
        home = fresh_home("meters")
        proj = home / "proj"
        proj.mkdir()
        py, fake = sys.executable, str(REPO / "tests/fake_mcp_server.py")
        stdio = {"command": py, "args": [fake, "--tools", "3", "--desc-bytes", "300"]}
        (home / ".claude.json").write_text(json.dumps({
            "mcpServers": {"cl-user": {"type": "stdio", **stdio}},
            "projects": {str(proj): {"mcpServers": {"cl-local": stdio}},
                         str(home / "elsewhere"): {"mcpServers": {"cl-other": stdio}}}}), encoding="utf-8")
        (home / ".codex").mkdir()
        (home / ".codex/config.toml").write_text(
            f"[mcp_servers.cx-stdio]\ncommand = {json.dumps(py)}\nargs = {json.dumps(stdio['args'])}\n\n"
            f"[mcp_servers.cx-http]\nurl = {json.dumps(url)}\nbearer_token_env_var = \"HV_TEST_TOKEN\"\n\n"
            f"[mcp_servers.cx-off]\ncommand = \"definitely-not-a-binary\"\nenabled = false\n", encoding="utf-8")
        (home / ".cursor").mkdir()
        (home / ".cursor/mcp.json").write_text(json.dumps({"mcpServers": {"cur": stdio}}), encoding="utf-8")
        (home / ".codeium/windsurf").mkdir(parents=True)
        (home / ".codeium/windsurf/mcp_config.json").write_text(
            json.dumps({"mcpServers": {"wind": stdio}}), encoding="utf-8")
        (home / ".config/opencode").mkdir(parents=True)
        (home / ".config/opencode/opencode.jsonc").write_text(
            '{\n  // opencode keeps comments and trailing commas\n  "mcp": {\n    "oc": {"type": "local", '
            f'"command": {json.dumps([py, *stdio["args"]])}, /* inline */ }},\n  }},\n}}\n', encoding="utf-8")
        shutil.copytree(REPO / "tests/fixture/usage/claude", home / ".claude")
        shutil.copytree(REPO / "tests/fixture/usage/codex", home / ".codex", dirs_exist_ok=True)
        r = sh([sys.executable, str(REPO / "meters/mcp_footprint.py"), "--out", str(home / "fp.json"),
                "--timeout", "3"], cwd=proj, env=home_env(home, HV_TEST_TOKEN="t0ken"), timeout=60)
        rows = {}
        if (home / "fp.json").exists():
            rows = {row["server"]: row for row in json.loads((home / "fp.json").read_text(encoding="utf-8"))["rows"]}
        errs = {n: row["error"][:60] for n, row in rows.items() if "error" in row}
        want = {"cl-user", "cl-local", "cx-stdio", "cx-http", "cur", "wind", "oc"}
        check("meters: configs of every MCP harness discovered + measured (stdio, streamable HTTP, jsonc)",
              r.returncode == 0 and set(rows) == want and not errs,
              f"servers={sorted(rows)}" + (f" errors={errs}" if errs else ""))
        calls = {n: rows[n].get("calls") for n in rows}
        ok = (calls.get("cl-user") == 1 and calls.get("cx-stdio") == 1 and calls.get("cx-http") == 1
              and calls.get("cl-local") == 0 and all(calls.get(n) is None for n in ("cur", "wind", "oc"))
              and rows.get("cx-stdio", {}).get("last_used") == "2026-09-26")
        check("meters: usage from Claude + Codex logs, unknown (not 0) where no logs exist", ok, f"calls={calls}")
    finally:
        srv.shutdown()


# Runs hvfmt against a fake kernel32/msvcrt, so the Windows branch is exercised on any OS.
WIN_SIM = r"""
import atexit, json, os, sys, types, ctypes
sys.path.insert(0, sys.argv[1])
import hvfmt
class F:
    def __init__(self, fn): self.fn = fn
    def __call__(self, *a): return self.fn(*a)
class S:
    encoding = "utf-8"
    def isatty(self): return True
    def fileno(self): return 1
    def write(self, t): return len(t)
    def flush(self): pass
def scenario(mode=None, set_ok=True, msvcrt_ok=True):
    sets, restores = [], []
    def get(h, p):
        if mode is None: return 0
        p._obj.value = mode; return 1
    def sett(h, m):
        sets.append(m); return 1 if set_ok else 0
    ctypes.windll = types.SimpleNamespace(kernel32=types.SimpleNamespace(GetConsoleMode=F(get), SetConsoleMode=F(sett)))
    sys.modules["msvcrt"] = types.SimpleNamespace(get_osfhandle=lambda fd: 7) if msvcrt_ok else None
    real, hvfmt.atexit = hvfmt.atexit, types.SimpleNamespace(register=lambda f, *a: restores.append(a))
    real_name, os.name = os.name, "nt"
    try:
        hvfmt.configure("pretty", S())
    finally:
        os.name, hvfmt.atexit = real_name, real
    return {"color": hvfmt._STATE["color"], "sets": sets, "restore": [r[1] for r in restores]}
out = {
    "vt_capable": scenario(mode=3),
    "vt_already_on": scenario(mode=7),
    "legacy_console": scenario(mode=3, set_ok=False),
    "redirected": scenario(mode=None),
    "no_msvcrt": scenario(mode=3, msvcrt_ok=False),
}
print(json.dumps(out))
"""


def format_checks() -> None:
    drift = [sys.executable, "drift/check.py", "--facts", "tests/fixture/hiviz/facts.toml",
             "--base", "tests/fixture"]
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "HIVIZ_FORMAT")}
    env["PYTHONIOENCODING"] = "utf-8"   # piped stdout is cp1251/cp1252 on Windows, which folds the box to ASCII
    md = sh(drift, env=env)
    pr = sh(drift + ["--format", "pretty"], env=env)
    col = sh(drift + ["--format", "pretty"], env={**env, "FORCE_COLOR": "1"})
    nocol = sh(drift + ["--format", "pretty"], env={**env, "FORCE_COLOR": "1", "NO_COLOR": "1"})
    viaenv = sh(drift, env={**env, "HIVIZ_FORMAT": "pretty"})
    md_ok = md.stdout.startswith("| status | fact | detail |") and "╭" not in md.stdout and "\x1b" not in md.stdout
    check("format: piped stdout stays markdown (agents, CI)", md_ok, md.stdout.splitlines()[0] if md.stdout else md.stderr[-80:])
    pr_ok = "╭" in pr.stdout and "✘ STALE" in pr.stdout and "\x1b" not in pr.stdout and pr.stdout == viaenv.stdout
    check("format: --format pretty / HIVIZ_FORMAT draw the table, no color off a TTY", pr_ok,
          f"{len(pr.stdout.splitlines())} lines")
    check("format: FORCE_COLOR colors, NO_COLOR wins", "\x1b[" in col.stdout and "\x1b" not in nocol.stdout)
    simenv = {k: v for k, v in env.items() if k != "TERM"}
    sim = sh([sys.executable, "-c", WIN_SIM, str(REPO / "render")], env=simenv)
    try:
        w = json.loads(sim.stdout)
    except ValueError:
        w = {}
    check("format: Windows console (simulated kernel32) — VT switched on and restored; legacy, redirected and no-msvcrt stay plain",
          bool(w) and w["vt_capable"] == {"color": True, "sets": [7], "restore": [3]}
          and w["vt_already_on"] == {"color": True, "sets": [], "restore": []}
          and w["legacy_console"]["color"] is False and w["redirected"]["color"] is False and w["no_msvcrt"]["color"] is False,
          (sim.stderr.strip().splitlines() or [""])[-1])
    ar = sh(drift + ["--format", "pretty"], env={**env, "HIVIZ_ASCII": "1"})
    check("format: HIVIZ_ASCII=1 forces the ASCII symbol set on a UTF-8 stream",
          ar.returncode in (0, 1) and not any(ch in ar.stdout for ch in "╭╮╰╯│─✔✘○◐") and "| x STALE" in ar.stdout, "")
    oem = sh(drift[:-2], env={**env, "PYTHONIOENCODING": "cp866"})
    check("format: markdown output survives a stream that cannot encode its text (cp866)",
          oem.returncode in (0, 1) and "Traceback" not in oem.stderr and oem.stdout.startswith("| status |"),
          (oem.stderr.strip().splitlines() or [""])[-1])
    for enc in ("ascii", "cp1252"):
        a = sh(drift + ["--format", "pretty"], env={**env, "PYTHONIOENCODING": enc})
        check(f"format: no crash on a {enc} stream, symbols fold to ASCII",
              "Traceback" not in a.stderr and a.stdout.isascii() and "| x STALE" in a.stdout.replace("│", "|"),
              (a.stderr.strip().splitlines() or [""])[-1])


def report_checks() -> None:
    import report as rp
    fx = REPO / "tests/fixture/report.md"
    out = OUT / "report_fx.html"
    r = sh([sys.executable, "render/report.py", "--md", str(fx), "--out", str(out)])
    page = out.read_text(encoding="utf-8") if out.exists() else ""
    md = fx.read_text(encoding="utf-8")
    rep = rp.parse(md)
    rows = rp.all_rows(rep) if rep else []
    byid = {x.id: x for x in rows}
    c1, d16, d05 = byid.get("C1"), byid.get("D16"), byid.get("D05")
    parsed = bool(rep and len(rows) == 14 and rep.has_where and rep.has_b and rep.corpus == 19377
                  and c1 and c1.conflict and c1.other.endswith("SKILL.md:9") and c1.other_q.startswith("10.0.0.99")
                  and d16 and rp.unwrap(d16.line).startswith("| Excuse | Reality |") and d16.b == 864
                  and d05 and d05.cat == "90%-rule" and d05.ev == "" and byid["D13"].ev == "fact")
    check("report: contract parsed (where, B, category, conflict sides, escaped pipes)", parsed,
          f"{len(rows)} rows" if rows else "no rows")
    no_net = not re.search(r"""(?:src|href)=["']https?:""", page)
    check("report: HTML view — sticky header, 11 decision rows, safe lines folded, offline",
          r.returncode == 0 and "position:sticky" in page and len(re.findall(r'<div class="row [^"]*"[^>]* data-need>', page)) == 11
          and "<details class=\"safe\">" in page and no_net and "Export decisions.md" in page,
          f"{len(page):,} bytes")
    hostile = rp.render(md.replace("baseline behaviour", "</script><script>alert(1)</script><!-- x"), "t")
    hm = re.search(r"<script type='application/json' id='hv-data'>(.*?)</script>", hostile, re.S)
    try:
        blob = json.loads(hm.group(1)) if hm else {}
    except ValueError:
        blob = {}
    check("report: model-written text cannot break out of the page (escaped cells, safe JSON blob)",
          bool(blob) and "<script>alert(1)" not in hostile.replace(hm.group(0), "") and any("alert(1)" in r["why"] for r in blob.get("rows", [])),
          "")
    legacy = "\n".join(["# t", "", "🔴 1 act now · 🟡 1 your call · ⚪ 0 fine · corpus 1.0 KB → shed −1.0%", "",
                        "## 🔴 Act now", "", "| id | line | why | → |", "|---|---|---|---|",
                        "| C1 | `x` | conflict: smelly:9 says `y` — two values | verify |", "",
                        "## 🟡 Your call", "", "| id | line | why | → verb |", "|---|---|---|---|",
                        "| D1 | `a \\| b` | trained-dup: default | → delete |"])
    model_style = "\n".join(["🔴 1 act now · 🟡 0 your call · ⚪ 0 fine · corpus 1.0 KB → shed −1%", "",
                             "## 🔴 Act now", "",
                             "| id | where | line ≤60 chars | why ≤80 chars | B | → verb |",
                             "| R1 | /w/A.md:3 ⇄ /w/B.md:9 | the gateway is .42 | conflict: B says «the gateway is .99» — two IPs | 0 | verify |"])
    def winify(text: str, sep: str) -> str:
        return re.sub(r"/work/profile[^ |:]*", lambda m: "C:" + m.group(0).replace(
            "/work/profile", "/Users/dev/.omp/profiles/hiviz-test/agent").replace("/", sep), text)
    wins = {}
    for label, text in (("bs", winify(md, "\\")), ("fs", winify(md, "/")), ("bom-crlf", "\ufeff" + md.replace("\n", "\r\n"))):
        wr = rp.parse(text)
        wrows = rp.all_rows(wr) if wr else []
        wins[label] = (wr, wrows, rp.common_dir(wrows) if wrows else "")
    ok_win = (all(len(v[1]) == 14 for v in wins.values())
              and rp.short(wins["bs"][1][0].where, wins["bs"][2]) == "AGENTS.md:13"
              and rp.short(wins["bs"][1][0].other, wins["bs"][2]) == "skills/smelly-skill/SKILL.md:9"
              and rp.short(wins["fs"][1][0].where, wins["fs"][2]) == "AGENTS.md:13"
              and wins["bom-crlf"][0].title == rep.title and wins["bom-crlf"][0].corpus == 19377
              and rp.common_dir(rp.all_rows(rp.parse(winify(md, "\\").replace("C:\\Users", "c:\\users", 3)))) != "")
    check("report: Windows reports — C:\\ and C:/ paths shorten, drive-letter case ignored, BOM + CRLF parse",
          ok_win, "")
    mrep = rp.parse(model_style)
    mr = rp.all_rows(mrep)[0] if mrep and rp.all_rows(mrep) else None
    check("report: grammar-template headers and a missing separator row are tolerated",
          bool(mr and mr.line == "the gateway is .42" and mr.b == 0 and mr.verb == "verify" and mr.other == "/w/B.md:9"
               and mr.other_q == "the gateway is .99" and mr.cat == "conflict"), "")
    lrep = rp.parse(legacy)
    lh = rp.render(legacy, "legacy")
    check("report: older 4-column reports still render (no where / B)",
          bool(lrep and not lrep.has_where and not lrep.has_b and len(rp.all_rows(lrep)) == 2
               and rp.all_rows(lrep)[0].other_q == "y" and rp.all_rows(lrep)[1].verb == "delete"
               and "data-need" in lh),
          "2 rows")
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "HIVIZ_FORMAT")}
    sm = sh([sys.executable, "render/report.py", "--md", str(fx), "--summary", "--format", "pretty"], env=env)
    sa = sh([sys.executable, "render/report.py", "--md", str(fx), "--summary", "--format", "pretty"],
            env={**env, "PYTHONIOENCODING": "ascii"})
    check("report: terminal summary — counts, rows by effect, conflict sides, ASCII-safe",
          sm.returncode == 0 and "2 act now" in sm.stdout and "kept safe" in sm.stdout and "D16" in sm.stdout
          and "SKILL.md:9" in sm.stdout and sa.returncode == 0 and sa.stdout.isascii() and "Traceback" not in sa.stderr,
          (sa.stderr.strip().splitlines() or [""])[-1])
    cands = ["google-chrome", "chromium", "chromium-browser", "chrome", "msedge"]
    for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(var)
        if root:
            cands += [str(Path(root) / "Google/Chrome/Application/chrome.exe"),
                      str(Path(root) / "Microsoft/Edge/Application/msedge.exe")]
    browser = next((b for b in cands if shutil.which(b)), None)
    if not browser:
        check("report: export round-trip in a browser (skipped — no Chrome/Chromium)", True)
        return
    drive = ("<script>var q=function(k,v){document.querySelector('.row[data-id='+k+'] button[data-v='+v+']').click()};"
             "q('C2','no');q('D05','cond');var n=document.querySelector('.row[data-id=D05] input.note');"
             "n.value='only the relevant tests';n.dispatchEvent(new Event('input',{bubbles:true}));n.blur();"
             "q('D19','keep');document.querySelector('.chip[data-cat=trained-dup] button').click();</script>")
    # fresh localStorage key per run: the page persists decisions, a custom --user-data-dir hangs headless Chrome here
    fresh = re.sub(r'"key": "[0-9a-f]+"', f'"key": "t{time.time_ns()}"', page, count=1)
    drv = OUT / "report_drive.html"
    drv.write_text(fresh.replace("</body>", drive + "</body>"), encoding="utf-8")
    dom = sh([browser, "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=4000",
              "--dump-dom", drv.as_uri()], timeout=60)
    import html as _h
    m = re.search(r"<pre id=\"prev\">(.*?)</pre>", dom.stdout or "", re.S)
    exp = _h.unescape(m.group(1)) if m else ""
    if dom.returncode == 124 or not (dom.stdout or "").strip():
        check("report: browser export round-trip (skipped — the browser produced no DOM)", True, "")
        return
    row = lambda k: next((l for l in exp.splitlines() if l.startswith(f"| {k} |")), "")
    ok = (bool(exp) and row("C2").endswith("| delete | no |") and row("D19").endswith("| delete | keep |")
          and row("D05").endswith("| rewrite | as-condition: only the relevant tests |")
          and row("D01").endswith("| delete | yes |") and row("D06").endswith("| rewrite |  |")
          and row("C1").endswith("| verify |  |") and row("K12").endswith("| keep | keep |")
          and "\\| Excuse \\| Reality" in row("D16") and "⇄" in row("C1") and "## ⚪ Kept safe" in exp)
    check("report: browser export — decisions, batch skips decided rows, undecided stays empty, pipes escaped", ok,
          f"{len(exp.splitlines())} lines" if exp else (dom.stderr or "no preview")[-100:])


def t1() -> None:
    print(hvfmt.heading("T1 · deterministic", "hermetic fake $HOME per harness · no model calls") if hvfmt.is_pretty()
          else "== T1: deterministic ==")
    _SECTION[0] = "installer / uninstall"
    installer_checks()
    uninstall_checks()
    uninstall_edge_checks()
    plugin_install_checks()
    _SECTION[0] = None

    mcp_cfg = OUT / "mcp_rendered.json"
    _mcp = json.loads((REPO / "tests/fixture/agent/mcp.json").read_text(encoding="utf-8"))
    _mcp["mcpServers"]["fake-bloated"]["command"] = sys.executable
    mcp_cfg.write_text(json.dumps(_mcp), encoding="utf-8")
    r = sh([sys.executable, "meters/mcp_footprint.py", "--config", str(mcp_cfg),
            "--sessions", "tests/fixture/blame/sessions",
            "--out", "tests/out/fake_mcp.json"])
    ok = r.returncode == 0
    row = {}
    if ok:
        data = json.loads((OUT / "fake_mcp.json").read_text(encoding="utf-8"))
        rows = [x for x in data["rows"] if "error" not in x]
        row = rows[0] if rows else {}
    check("meters: fake MCP measured", ok and bool(row), r.stderr.strip()[-120:] if not ok else "")
    if row:
        check("meters: weight + tokens + usage telemetry",
              row.get("tools") == 3 and 1200 <= row.get("bytes", 0) <= 4000
              and row.get("calls", 0) >= 2 and row.get("last_used") == "2026-09-03",
              f"tools={row.get('tools')} bytes={row.get('bytes')} tokens={row.get('tokens')} "
              f"calls={row.get('calls')} last={row.get('last_used')}")
    meters_discovery_check()

    d = sh([sys.executable, "drift/check.py", "--facts", "tests/fixture/hiviz/facts.toml",
            "--base", "tests/fixture",
            "--mcp-footprint", "tests/fixture/hiviz/mcp_footprint.json",
            "--out", "tests/out/drift.json"])
    d_ok = d.returncode == 1
    detail = (d.stderr or "")[-120:]
    if d_ok:
        drows = json.loads((OUT / "drift.json").read_text(encoding="utf-8"))
        stales = sorted(r["id"] for r in drows if r["status"] == "STALE")
        n_unv = len([r for r in drows if r["status"] == "UNVERIFIABLE"])
        n_ok = len([r for r in drows if r["status"] == "OK"])
        d_ok = (stales == ["legacy-runner-doc", "mcp:heavy-unused", "v3-migration-done"]
                and n_unv == 2 and n_ok == 6)
        detail = f"OK={n_ok} STALE={stales} UNVERIFIABLE={n_unv}"
    check("drift: planted statuses + MCP pay-vs-use detected", d_ok, detail)
    fp = OUT / "fp_unknown.json"
    fp.write_text(json.dumps({"rows": [
        {"server": "no-logs", "harnesses": "cursor/global", "tokens": 900, "calls": None, "last_used": None},
        {"server": "bad-date", "harnesses": "explicit", "tokens": 900, "calls": 3, "last_used": "never"}]}),
        encoding="utf-8")
    (OUT / "empty_facts.toml").write_text("[facts]\n", encoding="utf-8")
    d2 = sh([sys.executable, "drift/check.py", "--facts", str(OUT / "empty_facts.toml"), "--base", str(OUT),
             "--mcp-footprint", str(fp), "--out", str(OUT / "drift_unknown.json")])
    st = {}
    if (OUT / "drift_unknown.json").exists() and d2.returncode == 0:
        st = {r["id"]: r["status"] for r in json.loads((OUT / "drift_unknown.json").read_text(encoding="utf-8"))}
    check("drift: unknown usage / bad dates are UNVERIFIABLE, never STALE or a crash",
          st == {"mcp:no-logs": "UNVERIFIABLE", "mcp:bad-date": "UNVERIFIABLE"},
          f"rc={d2.returncode} {st or d2.stderr[-100:]}")

    fake_harness = f'"{sys.executable}" tests/fake_harness.py "{{ask}}"'
    (REPO / "tests/fake_harness.py").with_suffix(".state").unlink(missing_ok=True)
    c = sh([sys.executable, "constitution/run.py", "--tests", "tests/const_fixture",
           "--harness", fake_harness,
           "--corpus", "tests/fixture", "--out", "tests/out/constitution.json"])
    c_ok = c.returncode == 1
    cdetail = (c.stderr or "")[-140:]
    if c_ok:
        crows = json.loads((OUT / "constitution.json").read_text(encoding="utf-8"))
        v = {r["id"]: r["verdict"] for r in crows}
        c_ok = (v.get("pass-secrets") == "PASS" and v.get("pass-commit") == "PASS"
                and v.get("pass-language") == "PASS" and v.get("fail-offtopic") == "FAIL"
                and v.get("flaky-once") == "FLAKY" and v.get("orphaned-gone") == "ORPHANED"
                and v.get("error-crash") == "ERROR")
        cdetail = f"verdicts: {v}"
    check("constitution: all verdict classes produced", c_ok, cdetail)
    for f in ("PWNED", "PWNED2"):
        (OUT / f).unlink(missing_ok=True)
    c2 = sh([sys.executable, "constitution/run.py", "--tests", "tests/const_fixture_edge",
             "--harness", fake_harness, "--corpus", "tests/fixture", "--out", "tests/out/constitution_edge.json"])
    v2 = {}
    if (OUT / "constitution_edge.json").exists():
        v2 = {r["id"]: r["verdict"] for r in json.loads((OUT / "constitution_edge.json").read_text(encoding="utf-8"))}
    pwned = [f for f in ("PWNED", "PWNED2") if (OUT / f).exists()]
    check("constitution: ask never shell-executed, harness failure = ERROR, guards_needle honored",
          c2.returncode == 1 and not pwned and v2 == {"injection": "PASS", "harness-broken": "ERROR",
                                                      "needle-gone": "ORPHANED"},
          f"verdicts={v2} executed={pwned}")

    fx = OUT / "blame_fx"
    shutil.rmtree(fx, ignore_errors=True)
    templated_copy(REPO / "tests/fixture/blame/sessions", fx / "sessions")
    templated_copy(REPO / "tests/fixture/blame", fx / "meta")
    b = sh([sys.executable, "blame/blame.py", "--file", "tests/fixture/agent/AGENTS.md",
           "--marker", "10.0.0.42", "--sessions", str(fx / "sessions"),
           "--ledger", str(fx / "meta/ledger.jsonl"),
           "--constitution", "tests/fixture/blame/constitution.json"])
    b_ok = b.returncode == 0 and all(s in (b.stdout or "") for s in
                                     ["zai/glm-test-model", "TOUCHED THIS LINE", "fixture plant"])
    check("blame: ledger + mined history + line-touch flag", b_ok,
          ((b.stdout or "").splitlines() or [""])[0][:100])
    for h, model, session in [("claude", "claude-test-model", "claude: move gateway note"),
                              ("codex", "codex-test-model", "rollout-2026-09-05T10-00"),
                              ("pi", "testprov/pi-test-model", "pi: gateway fix")]:
        templated_copy(REPO / "tests/fixture/blame/harnesses" / h, fx / h)
        bh = sh([sys.executable, "blame/blame.py", "--file", "tests/fixture/agent/AGENTS.md",
                 "--marker", "10.0.0.42", "--sessions", str(fx / h)])
        lines = [x for x in (bh.stdout or "").splitlines() if x.strip().startswith("- ")]
        ok = (bh.returncode == 0 and len(lines) == 1 and model in lines[0] and session in lines[0]
              and "TOUCHED THIS LINE" in lines[0])
        check(f"blame [{h}]: session log mined (model, session, touched line)", ok,
              lines[0].strip()[:110] if lines else (bh.stdout or bh.stderr).strip()[-110:])
    gw_line = next(i for i, l in enumerate((REPO / "tests/fixture/agent/AGENTS.md")
                   .read_text(encoding="utf-8").splitlines(), 1) if "10.0.0.42" in l)
    bl = sh([sys.executable, "blame/blame.py", "--file", "tests/fixture/agent/AGENTS.md",
             "--line", str(gw_line), "--sessions", str(fx / "sessions"),
             "--ledger", str(fx / "meta/ledger.jsonl"),
             "--constitution", "tests/fixture/blame/constitution.json"])
    check("blame: --line selects the whole line's history too",
          bl.returncode == 0 and "TOUCHED THIS LINE" in (bl.stdout or ""),
          ((bl.stdout or "").splitlines() or [""])[0][:80])

    shutil.rmtree(OUT / "tr", ignore_errors=True)
    emitted, tr_err = {}, ""
    for t in ["omp", "claude", "codex", "pi", "opencode", "cursor", "windsurf"]:
        e = sh([sys.executable, "translate/emit.py", "--ir", "tests/fixture/ir.jsonl", "--target", t,
                "--out", f"tests/out/tr/{t}"])
        chk = sh([sys.executable, "translate/emit.py", "--ir", "tests/fixture/ir.jsonl", "--target", t,
                  "--out", f"tests/out/tr/{t}", "--check"])
        if e.returncode or chk.returncode:
            tr_err += f"{t}: {(e.stderr or chk.stdout)[-80:]} "
        emitted[t] = {f.relative_to(OUT / "tr" / t).as_posix(): f.read_text(encoding="utf-8")
                      for f in (OUT / "tr" / t).rglob("*") if f.is_file()}
    tr_ok = not tr_err
    if tr_ok:
        om, cl = emitted["omp"], emitted["claude"]
        single = {"claude": "CLAUDE.md", "codex": "AGENTS.md", "pi": "AGENTS.md", "opencode": "AGENTS.md",
                  "cursor": ".cursor/rules/hiviz.mdc", "windsurf": ".windsurf/rules/hiviz.md"}
        tr_ok = ("redact" in om["RULES.md"] and "explicit request" in om["RULES.md"]
                 and "redact" not in om["AGENTS.md"] and "10.0.0.99" in om["AGENTS.md"]
                 and "best practices" not in om["AGENTS.md"]
                 and "dedup" in om["translation-report.md"].lower() and om["translation-report.md"].count("| r") >= 5
                 and all(f in emitted[t] and "10.0.0.99" in emitted[t][f]
                         and emitted[t][f].find("redact") < emitted[t][f].find("10.0.0.99")
                         for t, f in single.items())
                 and emitted["cursor"][single["cursor"]].startswith("---\n")
                 and "alwaysApply: true" in emitted["cursor"][single["cursor"]]
                 and "trigger: always_on" in emitted["windsurf"][single["windsurf"]])
    check("translate: every target placed (omp split, safety first, cursor/windsurf rule frontmatter) + --check",
          tr_ok, f"7 targets, claude CLAUDE({len(cl['CLAUDE.md'].splitlines())}L)" if tr_ok
          else (tr_err or "content mismatch")[-160:])
    format_checks()
    report_checks()
    plugin_checks()

# ---------------------------------------------------------------- T2
def profile_setup() -> None:
    if PROFILE.parent.exists():
        shutil.rmtree(PROFILE.parent)
    PROFILE.mkdir(parents=True)
    src = REPO / "tests/fixture/agent"
    for item in ["AGENTS.md", "RULES.md", "mcp.json", "skills"]:
        s = src / item
        d = PROFILE / item
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
    # render from the checkout — T1 no longer installs into the real ~/.omp
    tpl = (REPO / "templates/skill.md").read_text(encoding="utf-8")
    (PROFILE / "skills/hv-audit").mkdir(parents=True)
    (PROFILE / "skills/hv-audit/SKILL.md").write_text(
        tpl.replace("{{AUDIT_BODY}}", (REPO / "core/AUDIT.md").read_text(encoding="utf-8")), encoding="utf-8")
    for name, sub in [("superpowers", "superpowers/skills"), ("anthropic", "anthropic-skills/skills")]:
        vendor = REPO / "tests/fixture/vendor" / sub
        for d in sorted(vendor.iterdir()):
            if d.is_dir():
                shutil.copytree(d, PROFILE / "skills" / f"{name}-{d.name}")
    if T2_HARNESS == "opencode":
        apply_tpl = (REPO / "templates/skill-apply.md").read_text(encoding="utf-8")
        (PROFILE / "skills/hv-apply").mkdir(parents=True)
        (PROFILE / "skills/hv-apply/SKILL.md").write_text(
            apply_tpl.replace("{{APPLY_BODY}}", (REPO / "core/APPLY.md").read_text(encoding="utf-8")),
            encoding="utf-8")
        # omp loads RULES.md natively; opencode needs it listed so the safety probes can quote it
        (PROFILE / "opencode.json").write_text('{"instructions": ["RULES.md"]}\n', encoding="utf-8")
        (PROFILE / ".agents").mkdir()
        (PROFILE / ".agents/skills").symlink_to("../skills", target_is_directory=True)
    (PROFILE / "config.yml").write_text(
        "modelRoles:\n  default: zai/glm-5.3-flash:high\nmemory:\n  backend: local\n"
        "skills:\n  customDirectories:\n    - " + str(PROFILE / "skills").replace("\\", "/") + "\n",
        encoding="utf-8")


DECISIONS = """# HiViz decisions (final — authored by the test operator)

| target file (ABSOLUTE path — edit exactly this file, no other copy) | marker | action |
|---|---|---|
| {P}/AGENTS.md | `10.0.0.42 (legacy)` | rewrite: update the gateway line to 10.0.0.99 (migrated 2026-03); keep `npm run deploy` |
| {P}/AGENTS.md | `Write clean, readable code and follow best practices.` | delete the line |
| {P}/AGENTS.md | `Be careful and thorough when editing files.` | delete the line |
| {P}/AGENTS.md | `Final stack state (2026-01-15)` | delete the line |
| {P}/AGENTS.md | ``NEVER use the `git stash` command.`` | rewrite as: `Prefer explicit branches over `git stash`; use stash only to rescue uncommitted noise.` |
| {P}/skills/smelly-skill/SKILL.md | `Always include a summary table in every response` | delete the line |
| {P}/skills/smelly-skill/SKILL.md | the `Example output` block (hash d41d8cd…) | delete the whole fenced block |
| {P}/RULES.md | every line | KEEP (safety) |
| {P}/skills/clean-skill/SKILL.md | every line | KEEP |

Backups: next to each edited file, as `<name>.bak-<YYYYMMDD>`.
Probes (pre-authorized, {H}; save answers to {O}/probes-before.md and {O}/probes-after.md):
- P1 ask: "Without extra text: quote your directives about secrets." expect marker: `redact`
- P2 ask: "Without extra text: quote your directives about committing." expect marker: `explicit request`
"""


def _file_hint(path: Path, label: str) -> str:
    if not path.exists():
        return f"{label}: not written yet"
    return f"{label}: {len(path.read_text(encoding='utf-8', errors='replace').splitlines())} lines"


def _bak_hint() -> str:
    n = len(list(PROFILE.glob("**/*.bak-*")))
    return f"{n} backup(s) written" if n else "no edits yet"


def report_view(report: Path, body: str) -> None:
    """Contract check on the model's report + what a human sees after the audit."""
    import report as rp
    rep = rp.parse(body)
    rows = rp.all_rows(rep) if rep else []
    good = [r for r in rows if re.search(r":\d+(-\d+)?$", r.where.split("⇄")[0].strip())
            and r.line.strip() and r.b is not None and r.verb in rp.VERBS]
    check("audit: every row carries where=path:line, a quoted line, B and a known verb",
          bool(rows) and len(good) >= 0.9 * len(rows),
          f"{len(good)}/{len(rows)} rows")
    html_path = OUT / "report.html"
    html_path.write_text(rp.render(body, report.stem), encoding="utf-8")
    if hvfmt.is_pretty():
        print(rp.terminal(body, report.as_posix(), html_path.as_posix(), (OUT / "decisions.md").as_posix()))
    else:
        print(f"  report: {report.as_posix()}\n  html view: {html_path.as_posix()}")


def t2() -> None:
    print(hvfmt.heading("T2 · end-to-end", f"{T2_HARNESS}"
                        + (f" · {T2_MODEL}" if T2_HARNESS == "opencode" else "")
                        + " · real model, ~10–20 min") if hvfmt.is_pretty()
          else "== T2: E2E on sandbox profile ==")
    OUT.mkdir(parents=True, exist_ok=True)
    o = OUT.as_posix()
    profile_setup()
    if T2_HARNESS == "omp" and not os.environ.get("ZAI_API_KEY"):
        # consistent online snapshot of the default profile's stored login (live db → use backup API)
        import sqlite3
        src_db = sqlite3.connect(str(HOME / ".omp/agent/agent.db"))
        dst_db = sqlite3.connect(str(PROFILE / "agent.db"))
        with dst_db:
            src_db.backup(dst_db)
        dst_db.close()
        src_db.close()
        check("t2: auth snapshot from default profile (agent.db)", (PROFILE / "agent.db").exists())
    with hvfmt.Phase(f"pre-flight: {T2_HARNESS} boots", budget=180) as ph:
        pf = sh(agent_cmd("Reply with the single word OK."), timeout=180)
        ph.status = "OK" if "OK" in (pf.stdout or "") else "FAIL"
    check(f"t2: profile pre-flight ({T2_HARNESS} boots)", "OK" in (pf.stdout or ""),
          "" if "OK" in (pf.stdout or "") else (pf.stderr or "")[-120:])
    vendor_installed = sorted(p.name for p in (PROFILE / "skills").glob("superpowers-*"))[:3]
    check("t2: popular vendor skills present in sandbox", len(vendor_installed) >= 3,
          f"{len(list((PROFILE / 'skills').glob('superpowers-*')))} superpowers + "
          f"{len(list((PROFILE / 'skills').glob('anthropic-*')))} anthropic")
    surfaces = [PROFILE / "AGENTS.md", PROFILE / "RULES.md",
                PROFILE / "skills/smelly-skill/SKILL.md", PROFILE / "skills/clean-skill/SKILL.md",
                PROFILE / "skills/superpowers-systematic-debugging/SKILL.md",
                PROFILE / "skills/anthropic-docx/SKILL.md"]
    audit_prompt = (
        "Use the hv-audit skill. Audit ONLY these instruction surfaces:\n"
        + "\n".join(str(p) for p in surfaces)
        + f"\nWrite {o}/report.md INCREMENTALLY — append each phase's table as soon as "
          "it is computed, do not hold the report in chat. Also write the decisions template to "
          f"{o}/decisions.md (DECISION column empty). Do NOT modify any audited file. "
          "Your final chat reply: one summary line only. English.")
    report = OUT / "report.md"
    reuse = os.environ.get("HIVIZ_REUSE") == "1"
    if reuse and report.exists() and "10.0.0.42" in (PROFILE / "AGENTS.md").read_text(encoding="utf-8"):
        print("  [skip] reusing existing report.md (HIVIZ_REUSE=1)")
    else:
        with hvfmt.Phase("audit — model reads the corpus and writes report.md", budget=1500,
                         hint=lambda: _file_hint(report, "report.md")) as ph:
            r = sh(agent_cmd(audit_prompt), timeout=1500)
            ph.status = "OK" if report.exists() else "FAIL"
        (OUT / "audit-last-output.txt").write_text(
            ((r.stdout or "")[-4000:]) + "\n--STDERR--\n" + ((r.stderr or "")[-1500:]), encoding="utf-8")
    check("audit: completed & report written", report.exists(),
          "see tests/out/audit-last-output.txt" if not report.exists() else "")
    if not report.exists():
        return
    body = report.read_text(encoding="utf-8-sig")
    report_view(report, body)
    missing = [m for m in GT["must_find"] if m not in body]
    check(f"audit recall {len(GT['must_find']) - len(missing)}/{len(GT['must_find'])}",
          not missing, "missing: " + ", ".join(missing) if missing else "all planted smells found")
    import hashlib
    _h = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()
    fx_files = {str(p): _h(p) for root in ["tests/fixture/agent", "tests/fixture/vendor"]
                for p in (REPO / root).rglob("*") if p.is_file()}
    (OUT / "decisions.md").write_text(
        DECISIONS.format(P=PROFILE.as_posix(), O=o, H=probe_hint()),
        encoding="utf-8")
    apply_prompt = (
        f"Use the hv-apply procedure. The decisions file is {o}/decisions.md — "
        "it is complete and final; apply exactly its rows, nothing else. "
        "Back up every edited file (.bak-<date>). The two probes at the bottom are pre-authorized: "
        f"run them before and after the edits and save answers to {o}/probes-before.md "
        f"and {o}/probes-after.md ({probe_hint()}). "
        "ORDER: make ALL file edits FIRST, then run the probes (before-snapshot from backups is acceptable "
        "if the session budget is tight). Do not commit. English.")
    with hvfmt.Phase("apply — model edits files, then runs probes", budget=2400,
                     hint=lambda: _bak_hint()) as ph:
        r = sh(agent_cmd(apply_prompt), timeout=2400)
    (OUT / "apply-last-output.txt").write_text(
        ((r.stdout or "")[-4000:]) + "\n--STDERR--\n" + ((r.stderr or "")[-1500:]), encoding="utf-8")
    changed_fx = [p for p, h in fx_files.items() if _h(p) != h]
    check("fixture source untouched by apply", not changed_fx,
          "edited: " + ", ".join(Path(p).name for p in changed_fx) if changed_fx else "")

    for rel, markers in GT["post_apply_absent"].items():
        f = PROFILE / rel
        txt = f.read_text(encoding="utf-8") if f.exists() else ""
        left = [m for m in markers if m in txt]
        check(f"apply: {rel} cleaned", not left, "still present: " + ", ".join(left) if left else "")
    for rel, markers in GT["post_apply_present"].items():
        f = PROFILE / rel
        txt = f.read_text(encoding="utf-8") if f.exists() else ""
        gone = [m for m in markers if m not in txt]
        check(f"apply: {rel} keeps invariants", not gone, "LOST: " + ", ".join(gone) if gone else "")
    baks = list(PROFILE.glob("**/*.bak-*")) + list((PROFILE / "skills").glob("**/*.bak-*"))
    check("apply: backups created", len(baks) >= 2, f"{len(baks)} .bak files")
    pa = OUT / "probes-after.md"
    check("apply: probes ran", pa.exists() and "redact" in pa.read_text(encoding="utf-8").lower(),
          "probes-after.md with safety quote" if pa.exists() else "no probes-after.md")
    with open(REPO / "tests/results.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M')} harness={T2_HARNESS} "
                f"model={T2_MODEL if T2_HARNESS == 'opencode' else 'glm-5.3-flash:high'} "
                f"passed={len(RESULTS) - len([r for r in RESULTS if not r[1]])}/{len(RESULTS)}\n")


def summary(elapsed: float = 0.0) -> int:
    failed = [r for r in RESULTS if not r[1]]
    if not hvfmt.is_pretty():
        print(f"\n== {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed ==")
        return 1 if failed else 0
    groups: dict[str, list[bool]] = {}
    for (name, ok, _), g in zip(RESULTS, GROUPS):
        groups.setdefault(g, []).append(ok)
    rows = [["PASS" if all(v) else "FAIL", g, f"{sum(v)}/{len(v)}",
             hvfmt.bar(sum(v), len(v))] for g, v in groups.items()]
    print(hvfmt.heading("results"))
    print(hvfmt.table(["", "group", "passed", "progress"], rows, status_col=0, align=["l", "l", "r", "l"]))
    if failed:
        print(hvfmt.heading("failures"))
        print(hvfmt.table(["check", "detail"], [[n, " ".join(d.split()) or "—"] for n, _, d in failed]))
    total = len(RESULTS)
    print("\n" + hvfmt.rule(f"{total - len(failed)}/{total} checks passed · {hvfmt.duration(elapsed)}",
                           "FAIL" if failed else "PASS"))
    return 1 if failed else 0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--t1", action="store_true")
    ap.add_argument("--t2", action="store_true")
    ap.add_argument("--all", action="store_true")
    hvfmt.add_format_arg(ap)
    a = ap.parse_args()
    hvfmt.configure(a.format)
    t0 = time.monotonic()
    if a.t1 or a.all or not (a.t1 or a.t2):
        t1()
    if a.t2 or a.all:
        t2()
    return summary(time.monotonic() - t0)


if __name__ == "__main__":
    sys.exit(main())
