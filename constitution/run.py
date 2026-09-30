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
        if f.is_file() and f.suffix in (".md", ".toml", ".json"):
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


def run_probe(harness_cmd: str, ask: str, timeout: float) -> tuple[str | None, str]:
    """Returns (error, answer). The template is tokenized and run without a shell,
    so `$(...)`, backticks or quotes inside an ask reach the harness verbatim."""
    if os.name == "nt":  # posix shlex would eat backslashes in Windows paths
        toks = [tok[1:-1] if len(tok) > 1 and tok[0] == tok[-1] and tok[0] in "\"'" else tok
                for tok in shlex.split(harness_cmd, posix=False)]
    else:
        toks = shlex.split(harness_cmd)
    argv = [tok.replace("{ask}", ask) for tok in toks]
    if not argv:
        return "empty harness command", ""
    argv[0] = shutil.which(argv[0]) or argv[0]
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"harness timeout after {timeout}s", ""
    except OSError as e:
        return f"harness failed to start: {e}", ""
    answer = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0:
        return f"harness exit={r.returncode}", answer
    return None, answer



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
        if re.search(pattern, answer):
            return False, f"must_not_match matched: {pattern}"
    return True, "markers ok"


def probe_once(t: dict, harness_cmd: str, timeout: float) -> str:
    err, answer = run_probe(harness_cmd, t["ask"], timeout)
    if err:
        return "ERROR"
    ok, _ = evaluate(answer, t)
    return "PASS" if ok else "FAIL"


def judge(t: dict, harness_cmd: str, corpus: Path | None, timeout: float) -> str:
    if guard_orphaned(t, corpus):
        return "ORPHANED"
    if not (t.get("must_include_any") or t.get("must_not_match") or guard_needle(t)):
        return "ERROR"  # nothing to check against: a PASS would be vacuous
    if probe_once(t, harness_cmd, timeout) == "PASS":
        return "PASS"
    second = probe_once(t, harness_cmd, timeout)
    return "FLAKY" if second == "PASS" else second


def detect_harness() -> str | None:
    for binname, cmd in [("omp", "omp -p"), ("claude", "claude -p"), ("codex", "codex exec")]:
        if shutil.which(binname):
            return f'{cmd} "{{ask}}"'
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="hiviz constitution runner")
    ap.add_argument("--tests", default=".hiviz/tests")
    ap.add_argument("--harness", default="auto", help='command template with {ask}, or "auto"')
    ap.add_argument("--corpus", default=None, help="dir to check guards against (orphaned)")
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    harness = a.harness
    if harness == "auto":
        harness = detect_harness()
        if not harness:
            print("no harness CLI detected (omp/claude/codex) — pass --harness", file=sys.stderr)
            return 2

    tests = load_tests(Path(a.tests))
    rows = []
    for t in tests:
        verdict = judge(t, harness, Path(a.corpus) if a.corpus else None, a.timeout)
        rows.append({"id": t["id"], "verdict": verdict, "severity": t.get("severity", "normal"),
                     "guards": t.get("guards", ""), "ask": t.get("ask", "")})
        print(f"  {verdict:8} {t['id']}")

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
