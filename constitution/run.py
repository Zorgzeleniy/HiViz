#!/usr/bin/env python3
"""hiviz constitution runner — probe tests for standing instructions.

Each test is a TOML file: an `ask` sent headlessly to a harness, plus marker
expectations for the answer (no expectations = the backticked `guards` marker,
or `guards_needle`, must be quoted back). Verdicts: PASS / FAIL / FLAKY (failed once,
passed on retry — reported, does not fail CI) / ORPHANED (the guarded
instruction line is gone from the corpus — report, not fail) / ERROR (harness
timed out, exited non-zero or failed to start twice; or the test has nothing to check).

Stdlib only. Costs one model call per probe (+1 on retry).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
if sys.version_info < (3, 11):  # tomllib is stdlib from 3.11
    sys.exit(f"hiviz constitution needs Python >= 3.11 (found {sys.version.split()[0]}) — install a newer Python or run it with `python3.11`")
import tomllib  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "render"))
import hvfmt  # noqa: E402
import control  # noqa: E402  (negative control: sits next to this file in every install)


VERDICT_ORDER = {"FAIL": 0, "ERROR": 1, "UNPROVEN": 2, "ORPHANED": 3, "FLAKY": 4, "PASS": 5}
# Headless one-shot commands. {ask} becomes ONE argv element — never shell-parsed.
HARNESSES = {
    "omp": 'omp -p "{ask}"',
    "pi": 'pi -p "{ask}"',
    "claude": 'claude -p "{ask}"',
    "codex": 'codex exec "{ask}"',
    "cursor": 'cursor-agent -p "{ask}"',
    "opencode": 'opencode run "{ask}"',
}


def load_tests(tests_dir: Path) -> list[dict]:
    tests = []
    for p in sorted(tests_dir.glob("*.toml")):
        t = tomllib.loads(p.read_text(encoding="utf-8"))
        t.setdefault("id", p.stem)
        t["_path"] = str(p)
        tests.append(t)
    return tests


def guard_orphaned(t: dict, corpus: Path | None) -> bool:
    """ORPHANED when guards references a corpus marker that no longer exists."""
    needle = guard_needle(t)
    if not (corpus and needle):
        return False

    for f in corpus.rglob("*"):
        if f.is_file() and f.suffix in (".md", ".mdc", ".toml", ".json"):
            try:
                if needle in f.read_text(encoding="utf-8", errors="replace"):
                    return False
            except OSError:
                continue
    return True


def guard_needle(t: dict) -> str | None:
    """Text that must exist in the corpus: guards_needle, else the backticked guards marker."""
    m = re.search(r"`([^`]+)`", t.get("guards") or "")
    return t.get("guards_needle") or (m.group(1) if m else None)


def build_argv(template: str, ask: str, cwd: Path | None = None) -> list[str]:
    posix = os.name != "nt"  # keep Windows backslash paths intact
    parts = shlex.split(template, posix=posix)
    if not posix:
        # strip single OR double quotes a caller's shlex.join left around paths
        parts = [x[1:-1] if len(x) >= 2 and x[0] == x[-1] in ("'", '"') else x for x in parts]
    if not any("{ask}" in x for x in parts):
        parts.append("{ask}")
    here = str(cwd or Path.cwd())
    argv = [part.replace("{ask}", ask).replace("{cwd}", here) for part in parts]
    if not argv:
        return []
    exe = shutil.which(argv[0])  # resolves Windows .cmd shims (npm-installed CLIs)
    if exe:
        argv[0] = exe
    return argv


def run_probe(harness_cmd: str, ask: str, timeout: float, cwd: Path | None = None) -> tuple[str | None, str]:
    """Returns (answer, error). The answer is stdout only: stderr carries harness
    noise (logs, "command not found") that must never satisfy a marker. `cwd` is where the harness starts
    (default: here); $PWD is set to match — Bun/Node harnesses take their directory from it."""
    argv = build_argv(harness_cmd, ask, cwd)
    if not argv:
        return None, "empty harness command"
    try:
        r = subprocess.run(argv, capture_output=True, text=True, cwd=cwd, env=control.probe_env(cwd or Path.cwd()),
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"harness TIMEOUT after {timeout}s"
    except OSError as e:
        return None, f"harness failed to start: {e}"[:160]
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
        return None, f"harness exit {r.returncode}: {tail[0][:120]}"
    return r.stdout or "", ""


def evaluate(answer: str, t: dict) -> tuple[bool, str]:
    include = t.get("must_include_any") or []
    if not include and not t.get("must_not_match"):
        # no explicit expectations: the guarded marker itself must be quoted back
        needle = guard_needle(t)
        include = [re.escape(needle)] if needle else []
    for pattern in include:
        if re.search(pattern, answer, re.IGNORECASE):
            break
    else:
        if include:
            return False, "none of must_include_any matched"
    for pattern in t.get("must_not_match") or []:
        if re.search(pattern, answer, re.IGNORECASE):
            return False, f"must_not_match matched: {pattern}"
    return True, "markers ok"


# "I have no directives about git stash" contains `git stash`: the commonest way a marker passes without the rule
_REFUSAL = re.compile(r"\b(no|not|none|nothing|n't|without)\b[^.]{0,60}\b(directive|instruction|rule|mention|guidance)", re.I)


def judge(t: dict, harness_cmd: str, corpus: Path | None, timeout: float, retried: dict,
          ctl: "control.Controller | None" = None, notools: bool = False, skip_reason: str = "--control off") -> tuple[str, str, dict]:
    """-> (verdict, detail, proof). proof = {"proof": line|project|none|skipped|"", "control": text}.
    A PASS/FLAKY is only worth something when the same question WITHOUT the rule's line does not pass too."""
    none: dict = {"proof": "", "control": ""}
    if guard_orphaned(t, corpus):
        return "ORPHANED", "guarded line not found in corpus", none
    if not (t.get("must_include_any") or t.get("must_not_match") or guard_needle(t)):
        return "ERROR", "nothing to check against: a PASS would be vacuous", none
    ask = control.with_note(t["ask"], notools)
    answer, err = run_probe(harness_cmd, ask, timeout)
    if err:
        return "ERROR", err, none
    ok, why = evaluate(answer, t)
    verdict, detail = ("PASS", why) if ok else ("FAIL", why)
    if not ok and not retried.get(t["id"]):
        retried[t["id"]] = True
        answer2, err2 = run_probe(harness_cmd, ask, timeout)
        if err2:
            return "ERROR", err2, none
        ok2, why2 = evaluate(answer2, t)
        if ok2:
            verdict, detail = "FLAKY", f"first attempt: {why}"
    if verdict == "FAIL" or ctl is None:
        return verdict, detail, ({"proof": "skipped", "control": skip_reason} if verdict != "FAIL" else none)
    c = ctl.check(t, harness_cmd, timeout)
    if c.status == "present":
        why = ("the answer is a refusal that repeats your marker — use words only the rule itself contains"
               if _REFUSAL.search(c.excerpt) else
               "harness default, the rule also lives elsewhere, or the markers are generic")
        return ("UNPROVEN", f"{c.detail}: “{c.excerpt}” — this probe does not show the rule binds ({why})",
                {"proof": "none", "control": c.detail})
    if c.status == "absent":
        return verdict, detail, {"proof": c.kind, "control": c.detail}
    return verdict, detail, {"proof": "skipped", "control": c.detail}


def _shown(r: dict) -> str:
    """Detail column: why it is not green — or, for a green row, how strong the proof is."""
    if r["verdict"] != "PASS":
        return r["detail"]
    return {"line": "proven: absent without the line", "project": "proven against an empty project only",
            "skipped": f"control skipped: {r['control']}"}.get(r.get("proof", ""), "")


def detect_harness() -> str | None:
    forced = os.environ.get("HIVIZ_HARNESS", "").strip()
    if forced:
        return HARNESSES.get(forced, forced)
    if os.environ.get("CLAUDECODE") and shutil.which("claude"):  # set inside Claude Code sessions
        return HARNESSES["claude"]
    for tpl in HARNESSES.values():
        if shutil.which(tpl.split()[0]):
            return tpl
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="hiviz constitution runner")
    ap.add_argument("--tests", default=".hiviz/tests")
    ap.add_argument("--harness", default="auto",
                    help=f'harness name ({", ".join(HARNESSES)}), a command template with {{ask}}, '
                         'or "auto" (HIVIZ_HARNESS env, then the first CLI found on PATH)')
    ap.add_argument("--corpus", default=None, help="dir to check guards against (orphaned) and to copy for the negative control")
    ap.add_argument("--control", choices=("auto", "off"), default="auto",
                    help="auto: a PASS must survive the negative control — the same question in a copy of --corpus WITHOUT the rule's "
                         "line (empty project when the test names no line); off: never run it. Needs --corpus")
    ap.add_argument("--control-runs", type=int, default=3,
                    help="control samples per PASS, run in parallel: ONE clean sample proves little (a rule-free copy still met a "
                         "specific marker in 1 of 3 runs on a real harness)")
    ap.add_argument("--allow-tools", action="store_true",
                    help="do not append the note asking the session to answer from its standing instructions without reading files")
    ap.add_argument("--strict", action="store_true", help="UNPROVEN fails the run too")
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--out", default=None)
    hvfmt.add_format_arg(ap)
    a = ap.parse_args()
    hvfmt.configure(a.format)

    harness = HARNESSES.get(a.harness, a.harness)
    if harness == "auto":
        harness = detect_harness()
        if not harness:
            print(f"no harness CLI detected ({'/'.join(HARNESSES)}) — pass --harness", file=sys.stderr)
            return 2

    tests = load_tests(Path(a.tests))
    corpus = Path(a.corpus) if a.corpus else None
    notools = not a.allow_tools
    ctl = (control.Controller(corpus, run_probe, evaluate, guard_needle, a.control_runs, notools)
           if a.control == "auto" and corpus else None)
    skip_reason = "--control off" if a.control == "off" else "no --corpus: nothing to copy"
    pretty = hvfmt.is_pretty()
    as_json = hvfmt.is_json()
    if pretty:
        print(hvfmt.heading("constitution", f"{len(tests)} probes · harness: {harness.split()[0]}"))
    rows = []
    secs = {}
    retried = {}
    for i, t in enumerate(tests, 1):
        t0 = time.monotonic()
        if pretty:
            with hvfmt.Phase(f"[{i}/{len(tests)}] {t['id']}", transient=True) as ph:
                verdict, detail, proof = judge(t, harness, corpus, a.timeout, retried, ctl, notools, skip_reason)
                ph.status, ph.note = verdict, "" if verdict == "PASS" else detail
        else:
            verdict, detail, proof = judge(t, harness, corpus, a.timeout, retried, ctl, notools, skip_reason)
        secs[t["id"]] = time.monotonic() - t0
        rows.append({"id": t["id"], "verdict": verdict, "severity": t.get("severity", "normal"),
                     "guards": t.get("guards", ""), "ask": t.get("ask", ""), "detail": detail, **proof})
        if not pretty and not as_json:
            note = detail if verdict != "PASS" else (f"control skipped: {proof['control']}" if proof["proof"] == "skipped" else "")
            print(f"  {verdict:8} {t['id']}" + (f" — {note}" if note else ""))
    if ctl:
        ctl.close()

    rows.sort(key=lambda r: (VERDICT_ORDER[r["verdict"]], r["id"]))
    failed = [r for r in rows if r["verdict"] in ("FAIL", "ERROR")]
    flaky = [r for r in rows if r["verdict"] == "FLAKY"]
    orphaned = [r for r in rows if r["verdict"] == "ORPHANED"]
    unproven = [r for r in rows if r["verdict"] == "UNPROVEN"]
    if as_json:
        print(hvfmt.dumps({"summary": {v: sum(r["verdict"] == v for r in rows) for v in VERDICT_ORDER},
                           "failed": len(failed), "rows": [{**r, "seconds": round(secs[r["id"]], 3)} for r in rows]}))
    elif pretty:
        print(hvfmt.table(["verdict", "test", "guards", "time", "detail"],
                          [[r["verdict"], r["id"], r["guards"][:60], hvfmt.duration(secs[r["id"]]),
                            _shown(r)] for r in rows],
                          status_col=0, align=["l", "l", "l", "r", "l"]))
        print(hvfmt.summary({v: sum(r["verdict"] == v for r in rows) for v in VERDICT_ORDER},
                            sorted(VERDICT_ORDER, key=VERDICT_ORDER.get)))
    else:
        print("\n| verdict | test | guards |")
        print("|---|---|---|")
        for r in rows:
            print(f"| {r['verdict']} | {r['id']} | {r['guards'][:60]} |")
        print(f"\n{len(rows) - len(failed) - len(unproven)}/{len(rows)} green · {len(flaky)} flaky · "
              f"{len(orphaned)} orphaned" + (f" · {len(unproven)} unproven" if unproven else ""), file=sys.stderr)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 1 if failed or (a.strict and unproven) else 0


if __name__ == "__main__":
    sys.exit(main())
