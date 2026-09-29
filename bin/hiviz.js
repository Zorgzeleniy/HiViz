#!/usr/bin/env node
// hiviz — uniform installer for Claude Code / Codex / omp / pi / Cursor / Windsurf / OpenCode adapters.
// Zero dependencies. Renders adapters from core/ + templates/ so all harnesses share one source of truth.
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const AUDIT = read("core/AUDIT.md");
const APPLY = read("core/APPLY.md");
const DRIFT = read("core/DRIFT.md");
const TESTS = read("core/TESTS.md");
const BLAME = read("core/BLAME.md");
const TRANSLATE = read("core/TRANSLATE.md");
const render = (t) => t.replaceAll("{{AUDIT_BODY}}", AUDIT).replaceAll("{{APPLY_BODY}}", APPLY).replaceAll("{{DRIFT_BODY}}", DRIFT).replaceAll("{{TESTS_BODY}}", TESTS).replaceAll("{{BLAME_BODY}}", BLAME).replaceAll("{{TRANSLATE_BODY}}", TRANSLATE);

const HOME = os.homedir();
const envDir = (name, fallback) => {
  const v = (process.env[name] || "").trim();
  return v ? path.resolve(v.replace(/^~(?=$|[\\/])/, HOME)) : fallback;
};
const CLAUDE_DIR = envDir("CLAUDE_CONFIG_DIR", path.join(HOME, ".claude"));
const CODEX_DIR = envDir("CODEX_HOME", path.join(HOME, ".codex"));
const PI_DIR = envDir("PI_CODING_AGENT_DIR", path.join(HOME, ".pi", "agent"));
const XDG_CONFIG = envDir("XDG_CONFIG_HOME", path.join(HOME, ".config"));
const OMP_DIR = path.join(HOME, ".omp", "agent");
// Cross-agent skills root: Codex, pi, Cursor, Windsurf and OpenCode all read it (omp dedups it
// against its native dir), so one copy serves them all without duplicate skill names.
const AGENTS_SKILLS = path.join(HOME, ".agents", "skills");

function harnesses() {
  const T = {
    skill: read("templates/skill.md"),
    skillApply: read("templates/skill-apply.md"),
    skillDrift: read("templates/skill-drift.md"),
    skillConstitution: read("templates/skill-constitution.md"),
    skillBlame: read("templates/skill-blame.md"),
    skillTranslate: read("templates/skill-translate.md"),
    cmdAudit: read("templates/command-audit.md"),
    cmdApply: read("templates/command-apply.md"),
    cmdDrift: read("templates/command-drift.md"),
    cmdTest: read("templates/command-test.md"),
    cmdBlame: read("templates/command-blame.md"),
    cmdTranslate: read("templates/command-translate.md"),
  };
  const skills = (root) => [
    ["hv-audit", render(T.skill)],
    ["hv-apply", render(T.skillApply)],
    ["hv-drift", render(T.skillDrift)],
    ["hv-constitution", render(T.skillConstitution)],
    ["hv-blame", render(T.skillBlame)],
    ["hv-translate", render(T.skillTranslate)],
  ].map(([name, content]) => [path.join(root, name, "SKILL.md"), content]);
  const commands = (root) => [
    ["hv-audit.md", render(T.cmdAudit)],
    ["hv-apply.md", render(T.cmdApply)],
    ["hv-drift.md", render(T.cmdDrift)],
    ["hv-test.md", render(T.cmdTest)],
    ["hv-blame.md", render(T.cmdBlame)],
    ["hv-translate.md", render(T.cmdTranslate)],
  ].map(([rel, content]) => [path.join(root, rel), content]);
  const shared = skills(AGENTS_SKILLS);
  return [
    { id: "claude", name: "Claude Code", marker: CLAUDE_DIR, targets: commands(path.join(CLAUDE_DIR, "commands")) },
    { id: "codex", name: "Codex", marker: CODEX_DIR, targets: shared },
    { id: "omp", name: "omp", marker: OMP_DIR, targets: skills(path.join(OMP_DIR, "skills")) },
    { id: "pi", name: "pi", marker: PI_DIR, targets: shared },
    { id: "cursor", name: "Cursor", marker: path.join(HOME, ".cursor"), targets: shared },
    { id: "windsurf", name: "Windsurf", marker: path.join(HOME, ".codeium", "windsurf"), targets: shared },
    {
      id: "opencode", name: "OpenCode", marker: path.join(XDG_CONFIG, "opencode"),
      targets: [...shared, ...commands(path.join(XDG_CONFIG, "opencode", "commands"))],
    },
  ];
}

// Adapters written by hiviz <= 0.7. Removed on init/uninstall; Windsurf's global_rules.md only
// when hiviz wrote the whole file (it used to overwrite user rules).
const LEGACY_WINDSURF_HEAD = "Audit standing instructions for prompt debt (stale facts, duplicates, relics, conflicts).";
function legacyTargets() {
  const out = ["hv-audit", "hv-apply", "hv-drift", "hv-test", "hv-blame", "hv-translate"]
    .map((n) => path.join(CODEX_DIR, "prompts", `${n}.md`));
  out.push(path.join(CODEX_DIR, "skills", "hv-audit"));
  out.push(path.join(HOME, ".cursor", "rules", "hiviz.mdc"));
  out.push(path.join(XDG_CONFIG, "opencode", "command", "hiviz.md"));
  const ws = path.join(HOME, ".codeium", "windsurf", "memories", "global_rules.md");
  if (fs.existsSync(ws) && fs.readFileSync(ws, "utf8").startsWith(LEGACY_WINDSURF_HEAD)) out.push(ws);
  return out.filter((p) => fs.existsSync(p));
}

function removeLegacy(dry) {
  for (const p of legacyTargets()) {
    if (dry) { console.log(`  ~ would remove legacy ${path.relative(HOME, p)}`); continue; }
    fs.rmSync(p, { recursive: true, force: true });
    console.log(`  - removed legacy ${path.relative(HOME, p)}`);
  }
}

function copyTree(src, dst, dry) {
  let wrote = 0;
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    if (e.name === "__pycache__") continue;
    const s = path.join(src, e.name), d = path.join(dst, e.name);
    if (e.isDirectory()) wrote += copyTree(s, d, dry);
    else {
      if (fs.existsSync(d) && fs.readFileSync(d, "utf8") === fs.readFileSync(s, "utf8")) continue;
      if (!dry) { fs.mkdirSync(path.dirname(d), { recursive: true }); fs.copyFileSync(s, d); }
      wrote++;
    }
  }
  return wrote;
}

function installEngines(dry) {
  const dst = path.join(HOME, ".hiviz", "engines");
  let wrote = 0;
  for (const dir of ["meters", "drift", "constitution", "blame", "translate", "render", "core"]) {
    wrote += copyTree(path.join(ROOT, dir), path.join(dst, dir), dry);
  }
  console.log(`  ${wrote === 0 && !dry ? "=" : dry ? "~" : "+"} engines -> ~/.hiviz/engines (${wrote} file${wrote === 1 ? "" : "s"} changed)`);
}

const detected = () => harnesses().filter((h) => fs.existsSync(h.marker));

function status() {
  console.log("Harnesses on this machine:");
  for (const h of harnesses()) {
    const det = fs.existsSync(h.marker);
    const inst = h.targets.every(([p]) => fs.existsSync(p));
    console.log(`  ${h.name.padEnd(12)} ${det ? "detected" : "not found"} · adapter ${!det ? "n/a" : inst ? "INSTALLED" : "missing (run: hiviz init)"}`);
  }
  const legacy = legacyTargets();
  if (legacy.length) console.log(`  legacy adapters from an older hiviz: ${legacy.length} (run: hiviz init to migrate)`);
}

function install(dry) {
  const list = detected();
  if (!list.length) console.log("No supported harness detected — installing the python engines only.");
  // Shared targets (~/.agents/skills) are written once, labeled with every harness that reads them.
  const plan = new Map();
  for (const h of list) {
    for (const [dest, content] of h.targets) {
      if (!plan.has(dest)) plan.set(dest, { content, names: [] });
      plan.get(dest).names.push(h.name);
    }
  }
  for (const [dest, { content, names }] of plan) {
    const label = names.join("/");
    if (fs.existsSync(dest) && fs.readFileSync(dest, "utf8") === content) {
      console.log(`  = ${label}: up-to-date ${path.relative(HOME, dest)}`);
      continue;
    }
    if (dry) { console.log(`  ~ ${label}: would write ${path.relative(HOME, dest)}`); continue; }
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, content);
    console.log(`  + ${label}: wrote ${path.relative(HOME, dest)}`);
  }
  removeLegacy(dry);
  installEngines(dry);
  if (!dry) console.log(
    "\nDone. Commands (Claude Code / OpenCode): /hv-audit, /hv-apply, /hv-drift, /hv-test, /hv-blame, /hv-translate.\n" +
    "Skills (Codex / omp / pi / Cursor / Windsurf / OpenCode): hv-audit, hv-apply, hv-drift, hv-constitution, hv-blame, hv-translate —\n" +
    "invoke by name or just ask \"audit my prompt debt\" / \"check instruction drift\" / \"blame this line\".\n" +
    "Python engines: ~/.hiviz/engines");
}

function uninstall() {
  const seen = new Set();
  const rm = (p, label) => {
    const target = p.endsWith("SKILL.md") ? path.dirname(p) : p;  // skill = whole dir
    if (seen.has(target)) return;
    seen.add(target);
    if (fs.existsSync(target)) { fs.rmSync(target, { recursive: true, force: true }); console.log(`  - removed ${label} ${path.relative(HOME, target)}`); }
  };
  for (const h of harnesses()) {
    for (const [dest] of h.targets) rm(dest, h.name);
  }
  removeLegacy(false);
  const eng = path.join(HOME, ".hiviz");
  if (fs.existsSync(eng)) { fs.rmSync(eng, { recursive: true, force: true }); console.log("  - removed ~/.hiviz (engines)"); }
}


const cmd = process.argv[2] || "status";
if (cmd === "status") status();
else if (cmd === "init") install(process.argv.includes("--dry"));
else if (cmd === "uninstall") uninstall();
else { console.log("usage: hiviz [status | init [--dry] | uninstall]"); process.exit(2); }
