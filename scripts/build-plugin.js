#!/usr/bin/env node
// Renders the marketplace plugin (plugin/) and the per-harness catalog manifests from core/ +
// templates/ + the engines, using the installer's own render code. The output is committed,
// because marketplaces install straight from git.
//   node scripts/build-plugin.js           write
//   node scripts/build-plugin.js --check   exit 1 when the committed tree is stale
"use strict";
const fs = require("fs");
const path = require("path");
const { ROOT, ENGINE_DIRS, skillSet } = require("../bin/hiviz.js");

const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));
const NAME = "hiviz";
const OWNER = { name: pkg.author };
const REPO_URL = pkg.homepage.replace(/#.*$/, "");
const DESC = "Audit and refactor standing AI-agent instructions for prompt debt: probe-verified cleanup, " +
  "drift checks, constitution tests, blame provenance, cross-harness translation.";
const PLUGIN_DIR = "plugin";
// Plugin engines skip core/: the skills already embed the procedures.
const PLUGIN_ENGINES = ENGINE_DIRS.filter((d) => d !== "core");
const json = (o) => JSON.stringify(o, null, 2) + "\n";

function expected() {
  const files = new Map();
  for (const [name, content] of skillSet()) files.set(`${PLUGIN_DIR}/skills/${name}/SKILL.md`, content);
  const walk = (rel) => {
    for (const e of fs.readdirSync(path.join(ROOT, rel), { withFileTypes: true })) {
      if (e.name === "__pycache__" || e.name.endsWith(".pyc")) continue;
      const r = `${rel}/${e.name}`;
      if (e.isDirectory()) walk(r);
      else files.set(`${PLUGIN_DIR}/engines/${r}`, fs.readFileSync(path.join(ROOT, r), "utf8"));
    }
  };
  PLUGIN_ENGINES.forEach(walk);
  const meta = { version: pkg.version, description: DESC, author: OWNER, homepage: REPO_URL,
    repository: REPO_URL, license: pkg.license, keywords: ["prompt-debt", "agents-md", "claude-md", "skills", "drift", "mcp"] };
  // Claude Code + omp (omp reads the Claude layout).
  files.set(`${PLUGIN_DIR}/.claude-plugin/plugin.json`, json({ name: NAME, ...meta }));
  // Agent Plugins portable manifest: Codex (canonical) and Cursor load it.
  files.set(`${PLUGIN_DIR}/plugin.json`, json({
    $schema: "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", name: NAME, ...meta,
    extensions: { "com.openai": { interface: {
      displayName: "HiViz", shortDescription: "Find and shed prompt debt in agent instructions",
      longDescription: DESC, developerName: pkg.author, category: "Productivity",
      capabilities: ["Read", "Write"], websiteURL: REPO_URL,
      defaultPrompt: ["Audit my prompt debt", "Check my agent instructions for drift"],
    } } },
  }));
  files.set(".claude-plugin/marketplace.json", json({
    name: NAME, owner: OWNER, description: DESC,
    plugins: [{ name: NAME, source: `./${PLUGIN_DIR}`, description: DESC }],
  }));
  files.set(".agents/plugins/marketplace.json", json({
    name: NAME, interface: { displayName: "HiViz" },
    plugins: [{ name: NAME, source: { source: "local", path: `./${PLUGIN_DIR}` },
      policy: { installation: "AVAILABLE", authentication: "ON_INSTALL" }, category: "Productivity" }],
  }));
  files.set(".cursor-plugin/marketplace.json", json({
    name: NAME, owner: OWNER, metadata: { description: DESC },
    plugins: [{ name: NAME, source: PLUGIN_DIR, description: DESC }],
  }));
  return files;
}

function onDisk() {
  const out = new Set();
  const walk = (rel) => {
    const abs = path.join(ROOT, rel);
    if (!fs.existsSync(abs)) return;
    for (const e of fs.readdirSync(abs, { withFileTypes: true })) {
      if (e.name === "__pycache__") continue;
      const r = `${rel}/${e.name}`;
      if (e.isDirectory()) walk(r); else out.add(r);
    }
  };
  walk(PLUGIN_DIR);
  return out;
}

function main() {
  const check = process.argv.includes("--check");
  const want = expected();
  const stale = [...want].filter(([rel, c]) => {
    const abs = path.join(ROOT, rel);
    return !fs.existsSync(abs) || fs.readFileSync(abs, "utf8") !== c;
  }).map(([rel]) => rel);
  const extra = [...onDisk()].filter((rel) => !want.has(rel));
  if (check) {
    if (!stale.length && !extra.length) { console.log(`plugin up to date (${want.size} files, v${pkg.version})`); return 0; }
    for (const r of stale) console.log(`STALE ${r}`);
    for (const r of extra) console.log(`EXTRA ${r}`);
    console.log("run: node scripts/build-plugin.js");
    return 1;
  }
  for (const rel of stale) {
    const abs = path.join(ROOT, rel);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, want.get(rel));
  }
  for (const rel of extra) fs.rmSync(path.join(ROOT, rel));
  console.log(`plugin built: ${stale.length} written, ${extra.length} removed, ${want.size} total (v${pkg.version})`);
  return 0;
}

process.exit(main());
