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
import tomllib
from pathlib import Path


VERDICT_ORDER = {"FAIL": 0, "ERROR": 1, "ORPHANED": 2, "FLAKY": 3, "PASS": 4}
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


def build_argv(template: str, ask: str) -> list[str]:
    posix = os.name != "nt"  # keep Windows backslash paths intact
    parts = shlex.split(template, posix=posix)
    if not posix:
        parts = [x[1:-1] if len(x) >= 2 and x[0] == x[-1] == '"' else x for x in parts]
    if not any("{ask}" in x for x in parts):
        parts.append("{ask}")
    argv = [x.replace("{ask}", ask) for x in parts]
    if not argv:
        return []
    exe = shutil.which(argv[0])  # resolves Windows .cmd shims (npm-installed CLIs)
    if exe:
        argv[0] = exe
    return argv


def run_probe(harness_cmd: str, ask: str, timeout: float) -> tuple[str | None, str]:
    """Returns (answer, error). The answer is stdout only: stderr carries harness
    noise (logs, "command not found") that must never satisfy a marker."""
    argv = build_argv(harness_cmd, ask)
    if not argv:
        return None, "empty harness command"
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
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
            return False, f"none of must_include_any matched"
    for pattern in t.get("must_not_match") or []:
        if re.search(pattern, answer, re.IGNORECASE):
            return False, f"must_not_match matched: {pattern}"
    return True, "markers ok"


def judge(t: dict, harness_cmd: str, corpus: Path | None, timeout: float, retried: dict) -> tuple[str, str]:
    if guard_orphaned(t, corpus):
        return "ORPHANED", "guarded line not found in corpus"
    if not (t.get("must_include_any") or t.get("must_not_match") or guard_needle(t)):
        return "ERROR", "nothing to check against: a PASS would be vacuous"
    answer, err = run_probe(harness_cmd, t["ask"], timeout)
    if err:
        return "ERROR", err
    ok, why = evaluate(answer, t)
    if ok:
        return "PASS", why
    if not retried.get(t["id"]):
        retried[t["id"]] = True
        answer2, err2 = run_probe(harness_cmd, t["ask"], timeout)
        if err2:
            return "ERROR", err2
        ok2, why2 = evaluate(answer2, t)
        if ok2:
            return "FLAKY", f"first attempt: {why}"
    return "FAIL", why


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
    ap.add_argument("--corpus", default=None, help="dir to check guards against (orphaned)")
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    harness = HARNESSES.get(a.harness, a.harness)
    if harness == "auto":
        harness = detect_harness()
        if not harness:
            print(f"no harness CLI detected ({'/'.join(HARNESSES)}) — pass --harness", file=sys.stderr)
            return 2

    tests = load_tests(Path(a.tests))
    rows = []
    retried = {}
    for t in tests:
        verdict, detail = judge(t, harness, Path(a.corpus) if a.corpus else None, a.timeout, retried)
        rows.append({"id": t["id"], "verdict": verdict, "severity": t.get("severity", "normal"),
                     "guards": t.get("guards", ""), "ask": t.get("ask", ""), "detail": detail})
        print(f"  {verdict:8} {t['id']}" + (f" — {detail}" if verdict != "PASS" else ""))

    rows.sort(key=lambda r: (VERDICT_ORDER[r["verdict"]], r["id"]))
    print("\n| verdict | test | guards |")
    print("|---|---|---|")
    for r in rows:
        print(f"| {r['verdict']} | {r['id']} | {r['guards'][:60]} |")
    failed = [r for r in rows if r["verdict"] in ("FAIL", "ERROR")]
    flaky = [r for r in rows if r["verdict"] == "FLAKY"]
    orphaned = [r for r in rows if r["verdict"] == "ORPHANED"]
    print(f"\n{len(rows) - len(failed)}/{len(rows)} green · {len(flaky)} flaky · "
          f"{len(orphaned)} orphaned", file=sys.stderr)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
