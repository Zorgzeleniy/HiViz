"""T1: human-output checks — formats, Windows console simulation, report page and summaries."""
from __future__ import annotations

import json
import os
import re
import sys


from .core import OUT, REPO, browser_export, check, fresh_home, home_env, sh


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
                             "| R1 | /w/A.md:3 ⇄ /w/B.md:9 | the gateway is .42 | conflict: B says «the gateway is .99» — two IPs | 0 | verify |",
                             "| R2 | `/w/A.md:5` | the second | trained-dup: x | 12 | delete |",
                             "| R3 | `/w/A.md:7` ⇄ **`/w/B.md:2`** | the third | conflict: B says «other» — differs | 0 | verify |"])
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
    check("report: grammar-template headers, a missing separator row and paths wrapped in backticks / bold are tolerated",
          bool(mr and mr.line == "the gateway is .42" and mr.b == 0 and mr.verb == "verify" and mr.other == "/w/B.md:9"
               and mr.other_q == "the gateway is .99" and mr.cat == "conflict"
               and [x.where for x in rp.all_rows(mrep)] == ["/w/A.md:3", "/w/A.md:5", "/w/A.md:7"]
               and rp.all_rows(mrep)[2].other == "/w/B.md:2"), "")
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
    sm_md = sh([sys.executable, "render/report.py", "--md", str(fx), "--summary", "--format", "md"], env=env)
    check("report: --summary --format md is plain markdown (no box drawing, no color) for agents and CI",
          sm_md.returncode == 0 and sm_md.stdout.startswith("# ") and "| id | verb |" in sm_md.stdout
          and "| D16 |" in sm_md.stdout and not any(ch in sm_md.stdout for ch in "╭│─✔✘\x1b"), "")
    exp = browser_export(page, "<script>var q=function(k,v){document.querySelector('.row[data-id='+k+'] button[data-v='+v+']').click()};"
                              "q('C2','no');q('D05','cond');var n=document.querySelector('.row[data-id=D05] input.note');"
                              "n.value='only the relevant tests';n.dispatchEvent(new Event('input',{bubbles:true}));n.blur();"
                              "q('D19','keep');document.querySelector('.chip[data-cat=trained-dup] button').click();</script>")
    if exp is None:
        check("report: export round-trip in a browser (skipped — no Chrome/Chromium/Edge, or it produced no DOM)", True, "")
        return
    row = lambda k: next((l for l in exp.splitlines() if l.startswith(f"| {k} |")), "")
    ok = (bool(exp) and row("C2").endswith("| delete | no |") and row("D19").endswith("| delete | keep |")
          and row("D05").endswith("| rewrite | as-condition: only the relevant tests |")
          and row("D01").endswith("| delete | yes |") and row("D06").endswith("| rewrite |  |")
          and row("C1").endswith("| verify |  |") and row("K12").endswith("| keep | keep |")
          and "\\| Excuse \\| Reality" in row("D16") and "⇄" in row("C1") and "## ⚪ Kept safe" in exp)
    check("report: browser export — decisions, batch skips decided rows, undecided stays empty, pipes escaped", ok,
          f"{len(exp.splitlines())} lines" if exp else "no preview")


def json_checks() -> None:
    """--format json: one parseable document on stdout for every engine, exit codes unchanged, ASCII-safe."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "HIVIZ_")) and k not in ("NO_COLOR", "FORCE_COLOR")}
    py = sys.executable

    def doc(cmd: list[str], **extra: str):
        r = sh(cmd + ["--format", "json"], env={**env, **extra})
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            return r.returncode, None

    rc, d = doc([py, "drift/check.py", "--facts", "tests/fixture/hiviz/facts.toml", "--base", "tests/fixture"])
    ok_drift = (rc == 1 and d and d["summary"]["STALE"] == 2 and len(d["rows"]) == 7 and d["needs_attention"] == 2
                and {"id", "status", "detail"} <= set(d["rows"][0]))
    fake = f'"{py}" tests/fake_harness.py "{{ask}}"'
    (REPO / "tests/fake_harness.py").with_suffix(".state").unlink(missing_ok=True)
    rc_c, c = doc([py, "constitution/run.py", "--tests", "tests/const_fixture", "--harness", fake, "--corpus", "tests/fixture/agent", "--control", "off"])
    ok_const = (rc_c == 1 and c and c["summary"]["PASS"] >= 3 and c["failed"] >= 1 and all("seconds" in r for r in c["rows"]))
    fx = OUT / "blame_fx"
    rc_b, b = doc([py, "blame/blame.py", "--file", "tests/fixture/agent/AGENTS.md", "--marker", "10.0.0.42",
                   "--sessions", str(fx / "sessions"), "--ledger", str(fx / "meta/ledger.jsonl")])
    ok_blame = (rc_b == 0 and b and b["marker"] == "10.0.0.42" and len(b["ledger"]) >= 1 and len(b["history"]) >= 1)
    rc_m, m = doc([py, "meters/mcp_footprint.py", "--config", str(OUT / "mcp_rendered.json"),
                   "--sessions", "tests/fixture/blame/sessions", "--out", str(OUT / "fake_mcp_json.json")])
    ok_meters = (rc_m == 0 and m and any(r.get("tools") == 3 for r in m["rows"]))
    rc_r, r = doc([py, "render/report.py", "--md", "tests/fixture/report.md", "--summary"])
    ok_report = bool(rc_r == 0 and r and r["funnel"] and [len(x["rows"]) for x in r["sections"]] == [2, 9, 3]
                     and r["corpus_bytes"] == 19377 and r["sections"][0]["rows"][1]["other"] == "")
    check("json: drift, constitution, blame, meters, report each print ONE parseable document (exit codes unchanged)",
          all([ok_drift, ok_const, ok_blame, ok_meters, ok_report]),
          f"drift={bool(ok_drift)} constitution={bool(ok_const)} blame={bool(ok_blame)} meters={bool(ok_meters)} report={bool(ok_report)}")
    tr = sh([py, "translate/emit.py", "--ir", "tests/fixture/ir.jsonl", "--target", "pi", "--out", str(OUT / "tr_json"), "--format", "json"], env=env)
    tr_env = sh([py, "translate/emit.py", "--ir", "tests/fixture/ir.jsonl", "--target", "pi", "--out", str(OUT / "tr_json")],
                env={**env, "HIVIZ_FORMAT": "json"})
    check("json: translate (no JSON output) refuses `--format json` with exit 2 and prints nothing; HIVIZ_FORMAT=json falls back to text",
          tr.returncode == 2 and "invalid choice" in tr.stderr and not tr.stdout.strip() and tr_env.returncode == 0 and "IR:" in tr_env.stdout,
          f"rc={tr.returncode}/{tr_env.returncode}")
    oem = sh([py, "drift/check.py", "--facts", "tests/fixture/hiviz/facts.toml", "--base", "tests/fixture", "--format", "json"],
             env={**env, "PYTHONIOENCODING": "cp866"})
    check("json: output is ASCII-only, so it survives any stream encoding (cp866)",
          oem.stdout.isascii() and json.loads(oem.stdout)["summary"]["OK"] == 4, (oem.stderr.strip().splitlines() or [""])[-1])


def installer_output_checks() -> None:
    """bin/hiviz.js: md (piped, unchanged) / pretty (symbols, table, color) / json (status only)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HIVIZ_") and k not in ("NO_COLOR", "FORCE_COLOR")}
    home = fresh_home("installer-output")
    for m in (".claude", ".codex"):
        (home / m).mkdir(parents=True)
    e = home_env(home, **{k: v for k, v in env.items() if k in ("PATH", "SYSTEMROOT")})
    st = sh(["node", "bin/hiviz.js", "status", "--format", "json"], env=e)
    try:
        data = json.loads(st.stdout)
    except ValueError:
        data = {}
    by = {h["harness"]: h for h in data.get("harnesses", [])}
    check("installer: `status --format json` lists every harness with detected / adapter / plugin",
          len(by) == 7 and by["Claude Code"]["detected"] and by["Codex"]["detected"] and not by["pi"]["detected"]
          and by["Codex"]["adapter"].startswith("missing") and by["pi"]["adapter"] == "n/a", f"{len(by)} harnesses")
    pe = {**e, "FORCE_COLOR": "1", "TERM_PROGRAM": "ci-rig"}   # win32 without WT_SESSION/TERM_PROGRAM folds to ASCII glyphs by design — assert the unicode path
    pretty = sh(["node", "bin/hiviz.js", "status", "--format", "pretty"], env=pe)
    dry = sh(["node", "bin/hiviz.js", "init", "--dry", "--format", "pretty"], env=pe)
    plain = sh(["node", "bin/hiviz.js", "status"], env=e)
    check("installer: pretty = box table + symbols + color; piped default stays the legacy text",
          "╭" in pretty.stdout and "\x1b[" in pretty.stdout and "○" in dry.stdout and "would write" in dry.stdout
          and "  ~ " not in dry.stdout and plain.stdout.startswith("Harnesses on this machine:") and "╭" not in plain.stdout, "")
    nc = sh(["node", "bin/hiviz.js", "status", "--format", "pretty"], env={**pe, "NO_COLOR": "1"})
    asc = sh(["node", "bin/hiviz.js", "init", "--dry", "--format", "pretty"], env={**e, "HIVIZ_ASCII": "1"})
    asc_t = sh(["node", "bin/hiviz.js", "status", "--format", "pretty"], env={**e, "HIVIZ_ASCII": "1"})
    check("installer: NO_COLOR drops color, HIVIZ_ASCII drops every non-ASCII glyph",
          "\x1b" not in nc.stdout and "╭" in nc.stdout and asc.stdout.isascii() and asc_t.stdout.isascii() and "+---" in asc_t.stdout, "")
    bad = sh(["node", "bin/hiviz.js", "init", "--format", "json"], env=e)
    envj = sh(["node", "bin/hiviz.js", "init", "--dry"], env={**e, "HIVIZ_FORMAT": "json"})
    check("installer: an explicit --format json is refused for init (exit 2, nothing written); HIVIZ_FORMAT=json is not",
          bad.returncode == 2 and "status" in bad.stderr and not (home / ".agents").exists()
          and envj.returncode == 0 and "would write" in envj.stdout, f"rc={bad.returncode}/{envj.returncode}")
