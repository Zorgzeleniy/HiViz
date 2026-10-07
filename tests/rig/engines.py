"""T1: engine checks — MCP meters, drift, constitution runner, blame, translate."""
from __future__ import annotations

import json
import shutil
import sys


from .core import OUT, REPO, check, fresh_home, home_env, sh, templated_copy


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


def engine_checks() -> None:
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

