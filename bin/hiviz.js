#!/usr/bin/env node
// hiviz — uniform installer for Claude Code / Codex / omp / pi / Cursor / Windsurf / OpenCode adapters.
// Zero dependencies. Renders adapters from core/ + templates/ so all harnesses share one source of truth.
// Marketplace installs use the prebuilt plugin/ tree (scripts/build-plugin.js renders it with the same code).
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
// Every rendered adapter embeds a core procedure, and each one starts with this heading.
// Uninstall only deletes files that carry it, so same-named user files survive.
const OWNERSHIP_MARK = "# HiViz ";
const ENGINE_DIRS = ["meters", "drift", "constitution", "blame", "translate", "render", "core"];

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
const ENGINES = path.join(HOME, ".hiviz", "engines");

function templates() {
  return {
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
}

// [skill dir name, SKILL.md content] — shared by the installer and the plugin build.
function skillSet(T = templates()) {
  return [
    ["hv-audit", render(T.skill)],
    ["hv-apply", render(T.skillApply)],
    ["hv-drift", render(T.skillDrift)],
    ["hv-constitution", render(T.skillConstitution)],
    ["hv-blame", render(T.skillBlame)],
    ["hv-translate", render(T.skillTranslate)],
  ];
}

function commandSet(T = templates()) {
  return [
    ["hv-audit.md", render(T.cmdAudit)],
    ["hv-apply.md", render(T.cmdApply)],
    ["hv-drift.md", render(T.cmdDrift)],
    ["hv-test.md", render(T.cmdTest)],
    ["hv-blame.md", render(T.cmdBlame)],
    ["hv-translate.md", render(T.cmdTranslate)],
  ];
}

function harnesses() {
  const T = templates();
  const skills = (root) => skillSet(T).map(([name, content]) => [path.join(root, name, "SKILL.md"), content]);
  const commands = (root) => commandSet(T).map(([rel, content]) => [path.join(root, rel), content]);
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

const readText = (p) => { try { return fs.readFileSync(p, "utf8"); } catch { return null; } };
const readJson = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };

// hiviz installed through a harness's own plugin manager → the npm adapters would duplicate it.
// Returns {harnessId: how to remove it there}. Cursor keeps no readable install record.
function pluginInstalls() {
  const out = {};
  const enabled = (readJson(path.join(CLAUDE_DIR, "settings.json")) || {}).enabledPlugins || {};
  const claudeKey = Object.keys(enabled).find((k) => /^hiviz@/.test(k) && enabled[k]);
  if (claudeKey) out.claude = `/plugin uninstall ${claudeKey}`;
  const omp = readText(path.join(HOME, ".omp", "plugins", "installed_plugins.json")) || "";
  const ompKey = (omp.match(/"(hiviz@[\w.-]+)"/) || [])[1];
  if (ompKey) out.omp = `/marketplace (uninstall ${ompKey})`;
  const codexCfg = readText(path.join(CODEX_DIR, "config.toml")) || "";
  const cm = codexCfg.match(/^\[plugins\."(hiviz@[^"]+)"\][^\[]*/m);
  if (cm && !/^\s*enabled\s*=\s*false/m.test(cm[0])) out.codex = `codex plugin remove ${cm[1]}`;
  const pkgs = (readJson(path.join(PI_DIR, "settings.json")) || {}).packages || [];
  // npm/git sources name the package; local ones are paths (relative to the agent dir) to a checkout
  const isHiviz = (src) => /(@zorgzeleniy\/hiviz|zorgzeleniy\/hiviz)(?![\w-])/i.test(src) ||
    (!/^(npm|git|https?):/.test(src) && src !== "" &&
      ((readJson(path.join(path.resolve(PI_DIR, src.replace(/^~(?=$|[\\/])/, HOME)), "package.json")) || {}).name === "@zorgzeleniy/hiviz"));
  const piSrc = pkgs.map((p) => (typeof p === "string" ? p : p && p.source) || "").find(isHiviz);
  if (piSrc) out.pi = `pi remove ${piSrc}`;
  return out;
}

// Adapters written by hiviz <= 0.7, deleted only when they carry the HiViz heading.
const LEGACY_WINDSURF_HEAD = "Audit standing instructions for prompt debt (stale facts, duplicates, relics, conflicts).";
const WINDSURF_RULES = path.join(HOME, ".codeium", "windsurf", "memories", "global_rules.md");
function legacyTargets() {
  const out = ["audit", "apply", "drift", "test", "blame", "translate"]
    .map((n) => path.join(CODEX_DIR, "prompts", `hv-${n}.md`));
  out.push(path.join(CODEX_DIR, "skills", "hv-audit", "SKILL.md"));
  out.push(path.join(HOME, ".cursor", "rules", "hiviz.mdc"));
  out.push(path.join(XDG_CONFIG, "opencode", "command", "hiviz.md"));
  return out.filter((p) => owned(p));
}
// Old installers overwrote the user's whole global_rules.md; it may since hold user edits,
// so it is moved aside, never deleted.
const legacyWindsurf = () => (readText(WINDSURF_RULES) || "").startsWith(LEGACY_WINDSURF_HEAD);

// Node 16's rmSync swallows EACCES (the file stays, no error), so verify instead of trusting it.
function rmChecked(p, opts) {
  fs.rmSync(p, opts);
  if (fs.existsSync(p) || isLink(p)) { const e = new Error(`EACCES: permission denied, rm '${p}'`); e.code = "EACCES"; throw e; }
}
const owned = (p) => (readText(p) || "").includes(OWNERSHIP_MARK);
const isLink = (p) => { try { return fs.lstatSync(p).isSymbolicLink(); } catch { return false; } };

// Empty dirs hiviz may have created are pruned upward; harness config roots and HOME never are.
function stopDirs() {
  return new Set([HOME, CLAUDE_DIR, CODEX_DIR, PI_DIR, OMP_DIR, XDG_CONFIG, path.join(HOME, ".config"),
    path.join(HOME, ".cursor"), path.join(HOME, ".codeium", "windsurf"), path.join(XDG_CONFIG, "opencode")]
    .map((d) => path.resolve(d)));
}
function pruneEmpty(dir, dry, log) {
  const stop = stopDirs();
  let pruned = 0;
  let d = path.resolve(dir);
  while (!stop.has(d) && d !== path.dirname(d) && !isLink(d)) {
    let entries;
    try { entries = fs.readdirSync(d); } catch { break; }
    if (entries.length) break;
    if (!dry) fs.rmdirSync(d);
    log(`${dry ? "  ~ would remove" : "  - removed"} empty ${path.relative(HOME, d) || d}/`);
    pruned++;
    if (dry) break;  // parents still hold this dir in a dry run
    d = path.dirname(d);
  }
  return pruned;
}

// Removes one adapter file hiviz owns. Skill dirs go only when nothing of the user's is left in them.
// Returns 1 when something was (or would be) removed. Failures are reported and counted, never thrown.
function removeAdapter(file, label, dry, log) {
  const dir = path.dirname(file);
  const isSkill = path.basename(file) === "SKILL.md";
  const shown = path.relative(HOME, isSkill ? dir : file);
  try {
    if (isLink(file) || (isSkill && isLink(dir))) {
      log(`  ! kept ${shown} — a symlink managed by another tool (e.g. npx skills); remove it there`);
      return 0;
    }
    if (!fs.existsSync(file)) {
      // a kept dir may have been emptied by the user since the last uninstall
      return !dry && fs.existsSync(dir) && pruneEmpty(dir, dry, log) > 0 ? 1 : 0;
    }
    if (!owned(file)) { log(`  ! kept ${path.relative(HOME, file)} — not written by hiviz`); return 0; }
    if (dry) log(`  ~ would remove ${label} ${shown}`);
    else { rmChecked(file, { force: true }); log(`  - removed ${label} ${shown}`); }
    if (isSkill) {
      const rest = (fs.existsSync(dir) ? fs.readdirSync(dir) : []).filter((n) => !(dry && n === "SKILL.md"));
      if (rest.length) log(`  ! kept ${path.relative(HOME, dir)}/ — holds files hiviz did not write: ${rest.slice(0, 3).join(", ")}`);
    }
    if (!dry) pruneEmpty(dir, dry, log);
    return 1;
  } catch (e) {
    log(`  ! FAILED to remove ${shown}: ${e.code || e.message}`);
    failures++;
    return 0;
  }
}
let failures = 0;

function removeLegacy(dry, log) {
  let n = 0;
  for (const p of legacyTargets()) n += removeAdapter(p, "legacy", dry, log);
  if (legacyWindsurf()) {
    const bak = `${WINDSURF_RULES}.hiviz-bak`;
    try {
      if (!dry) fs.renameSync(WINDSURF_RULES, bak);
      log(`  ${dry ? "~ would move" : "- moved"} legacy hiviz Windsurf rules ${path.relative(HOME, WINDSURF_RULES)} -> ${path.relative(HOME, bak)} (restore your own lines from it)`);
      n++;
    } catch (e) { log(`  ! FAILED to move ${path.relative(HOME, WINDSURF_RULES)}: ${e.code || e.message}`); failures++; }
  }
  return n;
}

// Deletes an engines dir, then its parent only when empty: ~/.hiviz doubles as the project data
// dir when an audit ran in $HOME (ledger, reports, facts).
function removeEngineDir(engines, shown, dry, log) {
  let n = 0;
  try {
    if (fs.existsSync(engines)) {
      if (!dry) rmChecked(engines, { recursive: true, force: true });
      log(`  ${dry ? "~ would remove" : "- removed"} ${shown}/engines`);
      n++;
    }
    const parent = path.dirname(engines);
    if (!fs.existsSync(parent)) return n;
    const rest = fs.readdirSync(parent).filter((f) => !(dry && f === "engines"));
    if (rest.length) log(`  ! kept ${shown}/ — holds your data: ${rest.slice(0, 3).join(", ")}${rest.length > 3 ? ", …" : ""}`);
    else if (!dry) { fs.rmdirSync(parent); log(`  - removed empty ${shown}/`); n++; }
  } catch (e) { log(`  ! FAILED to remove ${shown}/engines: ${e.code || e.message}`); failures++; }
  return n;
}

// Mirror src into dst: copy changed files, delete files the new version no longer ships.
// __pycache__ is left alone (python regenerates it; deleting would break idempotency output).
function syncTree(src, dst, dry) {
  let wrote = 0, removed = 0;
  const srcNames = new Set();
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    if (e.name === "__pycache__") continue;
    srcNames.add(e.name);
    const s = path.join(src, e.name), d = path.join(dst, e.name);
    if (e.isDirectory()) {
      const r = syncTree(s, d, dry);
      wrote += r.wrote; removed += r.removed;
    } else {
      if (fs.existsSync(d) && fs.readFileSync(d).equals(fs.readFileSync(s))) continue;
      if (!dry) { fs.mkdirSync(path.dirname(d), { recursive: true }); fs.copyFileSync(s, d); }
      wrote++;
    }
  }
  if (fs.existsSync(dst)) {
    for (const e of fs.readdirSync(dst, { withFileTypes: true })) {
      if (e.name === "__pycache__" || srcNames.has(e.name)) continue;
      if (!dry) rmChecked(path.join(dst, e.name), { recursive: true, force: true });
      removed++;
    }
  }
  return { wrote, removed };
}

// ---- output: md (plain text — what pipes, CI and agents get) | pretty (symbols + color on a terminal) | json (status only).
// Same switches as the python engines: --format, HIVIZ_FORMAT, NO_COLOR, FORCE_COLOR, HIVIZ_ASCII.
function resolveFormat(argv, env, isTTY) {
  const i = argv.indexOf("--format");
  const eq = argv.find((a) => a.startsWith("--format="));
  const flag = i >= 0 ? argv[i + 1] || "" : eq ? eq.slice(9) : "";
  const v = (flag || env.HIVIZ_FORMAT || "").trim().toLowerCase();
  return ["pretty", "md", "json"].includes(v) ? v : isTTY ? "pretty" : "md";
}
const FMT = resolveFormat(process.argv, process.env, Boolean(process.stdout.isTTY));
const COLOR = FMT === "pretty" && !process.env.NO_COLOR &&
  (Boolean(process.env.FORCE_COLOR) || (Boolean(process.stdout.isTTY) && process.env.TERM !== "dumb"));
// legacy Windows consoles lack the glyphs: Unicode there only in a modern terminal (untested on Windows)
const UNICODE = !process.env.HIVIZ_ASCII &&
  (process.platform !== "win32" || Boolean(process.env.WT_SESSION || process.env.TERM_PROGRAM || process.env.ConEmuANSI));
const CODES = { bold: 1, dim: 2, red: 31, green: 32, yellow: 33, cyan: 36, gray: 90 };
const paint = (text, ...names) => (COLOR && names.length ? names.map((n) => `\x1b[${CODES[n]}m`).join("") + text + "\x1b[0m" : text);
const MARKS = { "+": ["✔", "+", "green"], "=": ["✔", "=", "gray"], "~": ["○", "~", "cyan"], "!": ["!", "!", "yellow"], "-": ["–", "-", "gray"] };
const symbol = (key) => { const [u, a, c] = MARKS[key]; return paint(UNICODE ? u : a, c, "bold"); };

function say(text) {
  if (FMT !== "pretty") { console.log(text); return; }
  for (const line of String(text).split("\n")) {
    const m = /^(\s*)([+=~!-]) (.*)$/.exec(line);
    if (!m) { console.log(/^Done\./.test(line) ? paint(line, "bold") : line); continue; }
    const failed = m[2] === "!" && /FAILED/.test(m[3]);
    console.log(`${m[1]}${failed ? paint(UNICODE ? "✘" : "x", "red", "bold") : symbol(m[2])} ${failed ? paint(m[3], "red") : m[3]}`);
  }
}

function table(headers, rows) {
  const w = headers.map((h, i) => Math.max([...h].length, ...rows.map((r) => [...r[i].text].length)));
  const B = UNICODE ? { tl: "╭", tr: "╮", bl: "╰", br: "╯", h: "─", v: "│", t: "┬", b: "┴", l: "├", r: "┤", x: "┼" }
    : { tl: "+", tr: "+", bl: "+", br: "+", h: "-", v: "|", t: "+", b: "+", l: "+", r: "+", x: "+" };
  const rule = (l, m, r) => paint(l + w.map((n) => B.h.repeat(n + 2)).join(m) + r, "gray");
  const v = paint(B.v, "gray");
  const cell = (text, i, ...style) => paint(text, ...style) + " ".repeat(w[i] - [...text].length);
  const out = [rule(B.tl, B.t, B.tr), v + headers.map((h, i) => ` ${cell(h, i, "bold")} `).join(v) + v, rule(B.l, B.x, B.r)];
  for (const r of rows) out.push(v + r.map((c, i) => ` ${cell(c.text, i, ...(c.style || []))} `).join(v) + v);
  out.push(rule(B.bl, B.b, B.br));
  return out.join("\n");
}

function installEngines(dry) {
  let wrote = 0, removed = 0;
  for (const dir of ENGINE_DIRS) {
    const r = syncTree(path.join(ROOT, dir), path.join(ENGINES, dir), dry);
    wrote += r.wrote; removed += r.removed;
  }
  const mark = wrote + removed === 0 ? "=" : dry ? "~" : "+";
  say(`  ${mark} engines -> ~/.hiviz/engines (${wrote} file${wrote === 1 ? "" : "s"} changed, ${removed} removed)`);
}

const detected = () => harnesses().filter((h) => fs.existsSync(h.marker));

function status() {
  const plugins = pluginInstalls();
  const legacy = legacyTargets().length + (legacyWindsurf() ? 1 : 0);
  const rows = harnesses().map((h) => {
    const det = fs.existsSync(h.marker);
    const inst = h.targets.every(([p]) => fs.existsSync(p));
    const plug = Boolean(plugins[h.id]);
    const adapter = !det ? "n/a" : inst ? "INSTALLED" : plug ? "not needed" : "missing (run: hiviz init)";
    return { h, det, plug, adapter };
  });
  if (FMT === "json") {
    console.log(JSON.stringify({
      harnesses: rows.map((r) => ({ harness: r.h.name, id: r.h.id, detected: r.det, adapter: r.adapter, plugin: r.plug })),
      legacyAdapters: legacy,
    }, null, 2));
    return;
  }
  if (FMT === "pretty") {
    say("");
    console.log(paint("hiviz status", "bold") + paint("  harnesses on this machine", "gray"));
    console.log(table(["harness", "detected", "adapter"], rows.map((r) => [
      { text: r.h.name },
      { text: r.det ? "detected" : "not found", style: [r.det ? "green" : "gray"] },
      { text: r.adapter + (r.plug ? " · plugin INSTALLED" : ""),
        style: [r.adapter === "INSTALLED" || r.adapter === "not needed" ? "green" : r.adapter === "n/a" ? "gray" : "yellow"] },
    ])));
    if (legacy) say(`  ! legacy adapters from an older hiviz: ${legacy} (run: hiviz init to migrate)`);
    return;
  }
  say("Harnesses on this machine:");
  for (const r of rows) {
    say(`  ${r.h.name.padEnd(12)} ${r.det ? "detected" : "not found"} · adapter ${r.adapter}${r.plug ? " · plugin INSTALLED" : ""}`);
  }
  if (legacy) say(`  legacy adapters from an older hiviz: ${legacy} (run: hiviz init to migrate)`);
}

function install(dry) {
  const list = detected();
  const plugins = pluginInstalls();
  if (!list.length) say("No supported harness detected — installing the python engines only.");
  // Shared targets (~/.agents/skills) are written once, labeled with every harness that reads them.
  const plan = new Map();
  for (const h of list) {
    if (plugins[h.id]) { say(`  = ${h.name}: hiviz already installed through its plugin manager — adapters not needed`); continue; }
    for (const [dest, content] of h.targets) {
      if (!plan.has(dest)) plan.set(dest, { content, names: [] });
      plan.get(dest).names.push(h.name);
    }
  }
  const sharedReaders = list.filter((h) => plugins[h.id] && h.targets.some(([p]) => plan.has(p)));
  for (const h of sharedReaders) {
    say(`  ! ${h.name} will list the hiviz skills twice (plugin + ~/.agents/skills, needed by other harnesses)`);
  }
  for (const [dest, { content, names }] of plan) {
    const label = names.join("/");
    if (fs.existsSync(dest) && fs.readFileSync(dest, "utf8") === content) {
      say(`  = ${label}: up-to-date ${path.relative(HOME, dest)}`);
      continue;
    }
    if (isLink(dest) || (path.basename(dest) === "SKILL.md" && isLink(path.dirname(dest)))) {
      say(`  ! ${label}: kept ${path.relative(HOME, dest)} — a symlink managed by another tool`);
      continue;
    }
    if (fs.existsSync(dest) && !owned(dest)) {
      say(`  ! ${label}: kept ${path.relative(HOME, dest)} — not written by hiviz, remove it to install`);
      continue;
    }
    if (dry) { say(`  ~ ${label}: would write ${path.relative(HOME, dest)}`); continue; }
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, content);
    say(`  + ${label}: wrote ${path.relative(HOME, dest)}`);
  }
  removeLegacy(dry, say);
  installEngines(dry);
  if (!dry) say(
    "\nDone. Commands (Claude Code / OpenCode): /hv-audit, /hv-apply, /hv-drift, /hv-test, /hv-blame, /hv-translate.\n" +
    "Skills (Codex / omp / pi / Cursor / Windsurf / OpenCode): hv-audit, hv-apply, hv-drift, hv-constitution, hv-blame, hv-translate —\n" +
    "invoke by name or just ask \"audit my prompt debt\" / \"check instruction drift\" / \"blame this line\".\n" +
    "Python engines: ~/.hiviz/engines");
}

function uninstall(dry) {
  let n = 0;
  const seen = new Set();
  for (const h of harnesses()) {
    for (const [dest] of h.targets) {
      if (seen.has(dest)) continue;
      seen.add(dest);
      n += removeAdapter(dest, h.name, dry, say);
    }
  }
  n += removeLegacy(dry, say);
  n += removeEngineDir(ENGINES, "~/.hiviz", dry, say);
  for (const [id, how] of Object.entries(pluginInstalls())) {
    const h = harnesses().find((x) => x.id === id);
    say(`  ! ${h.name}: hiviz is also installed as a plugin — remove it there: ${how}`);
  }
  if (!n && !failures) say("  nothing to remove");
  if (failures) { say(`\n${failures} item(s) could not be removed — see FAILED above`); process.exitCode = 1; }
}

module.exports = { ROOT, ENGINE_DIRS, OWNERSHIP_MARK, skillSet, commandSet, syncTree };

if (require.main === module) {
  const args = process.argv.slice(2).filter((a, i, all) => !a.startsWith("-") && all[i - 1] !== "--format");
  const cmd = args[0] || "status";
  const dry = process.argv.includes("--dry");
  if (FMT === "json" && cmd !== "status") { console.error("hiviz: --format json is supported for `status` only"); process.exit(2); }
  if (cmd === "status") status();
  else if (cmd === "init") install(dry);
  else if (cmd === "uninstall") uninstall(dry);
  else { console.log("usage: hiviz [status | init [--dry] | uninstall [--dry]] [--format pretty|md|json]"); process.exit(2); }
}
