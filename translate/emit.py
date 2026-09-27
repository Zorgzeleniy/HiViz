#!/usr/bin/env python3
"""hiviz translator emit — mechanical placement of an instruction IR.

Input: IR jsonl, one entry per line:
  {"id": "r1", "text": "- ...", "kind": "safety|invariant|rule|fact",
   "source": "AGENTS.md:12", "assumes": ["f-x"], "dedup_of": null|"r0"}

Entries with dedup_of set are DROPPED (dedup was decided at IR authoring).
Placement per target:
  omp     -> RULES.md (safety) + AGENTS.md (invariant, rule, fact)
  claude  -> CLAUDE.md (all, safety section first)
  codex   -> AGENTS.md (all, safety section first)
  cursor  -> .cursorrules (all, safety section first)

Modes:
  default        emit files + translation-report.md into --out
  --check        verify the LIVE files at --out against the mechanical emission
                 from the IR; exit 1 on divergence (CI-friendly: catches
                 "two harness configs drifted apart" after a migration)

Stdlib only; without --check it writes only into --out.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KIND_ORDER = ["safety", "invariant", "rule", "fact"]
TARGETS = {
    "omp": [("RULES.md", ["safety"]), ("AGENTS.md", ["invariant", "rule", "fact"])],
    "claude": [("CLAUDE.md", KIND_ORDER)],
    "codex": [("AGENTS.md", KIND_ORDER)],
    "cursor": [(".cursorrules", KIND_ORDER)],
}
KIND_HEADERS = {"safety": "Safety (non-negotiable)", "invariant": "Environment invariants",
                "rule": "Rules", "fact": "Facts"}


def load_ir(path: Path) -> tuple[list[dict], list[dict]]:
    """Invalid entries abort the run: a silently skipped line is a rule lost in migration."""
    kept, dropped = [], []
    problems = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError as ex:
            problems.append(f"line {n}: invalid JSON ({ex.msg})")
            continue
        if e.get("dedup_of"):
            dropped.append(e)
            continue
        kind = str(e.get("kind", "")).strip().lower()
        if kind not in KIND_ORDER:
            problems.append(f"line {n} ({e.get('id', '?')}): kind {e.get('kind')!r} "
                            f"not one of {'|'.join(KIND_ORDER)}")
        elif not isinstance(e.get("text"), str) or not e["text"].strip():
            problems.append(f"line {n} ({e.get('id', '?')}): missing text")
        else:
            e["kind"] = kind
            kept.append(e)
    if problems:
        print(f"IR {path}: {len(problems)} invalid entr{'y' if len(problems) == 1 else 'ies'}",
              file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        sys.exit(2)
    return kept, dropped


def render_target(kept: list[dict], target: str, name: str) -> dict[str, str]:
    files = {}
    for fname, kinds in TARGETS[target]:
        sections = []
        for kind in kinds:
            rows = [e for e in kept if e.get("kind") == kind]
            if not rows:
                continue
            body = "\n".join(e["text"].rstrip() for e in rows)
            srcs = ", ".join(sorted({e.get("source", "?").split(":")[0] for e in rows}))
            sections.append(f"## {KIND_HEADERS[kind]}\n\n{body}\n\n<!-- sources: {srcs} -->")
        if not sections:
            continue
        files[fname] = f"# {name} — translated from source corpus (hiviz)\n\n" + "\n\n".join(sections)
    return files


def emit(kept: list[dict], target: str, out: Path, name: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for fname, content in render_target(kept, target, name).items():
        (out / fname).write_text(content, encoding="utf-8")
        print(f"  wrote {out / fname}")


def check(kept: list[dict], target: str, live: Path, name: str) -> int:
    bad = 0
    for fname, expected in render_target(kept, target, name).items():
        p = live / fname
        if not p.exists():
            print(f"DIVERGED {fname}: file missing")
            bad += 1
            continue
        actual = p.read_text(encoding="utf-8", errors="replace")
        if actual == expected:
            print(f"OK       {fname}")
            continue
        a_lines = set(actual.splitlines())
        missing = [l for l in expected.splitlines() if l not in a_lines and l.strip()]
        extra = [l for l in actual.splitlines() if l not in set(expected.splitlines()) and l.strip()]
        ids = [e["id"] for e in kept if e["text"].rstrip() in "\n".join(missing)]
        hint = f"rules lost: {', '.join(ids)}" if ids else "content drift"
        print(f"DIVERGED {fname}: {len(missing)} expected line(s) missing, "
              f"{len(extra)} unexpected ({hint})")
        bad += 1
    print(f"\n{len(TARGETS[target]) - bad}/{len(TARGETS[target])} files in sync" if TARGETS[target] else "")
    return 1 if bad else 0


def report(kept: list[dict], dropped: list[dict], target: str, out: Path) -> None:
    lines = [f"# Translation report — target: {target}",
             "", f"- translated: {len(kept)} entries",
             f"- deduplicated away: {len(dropped)}"]
    for d in dropped:
        lines.append(f"  - `{d['id']}` duplicate of `{d['dedup_of']}`")
    lines += ["", "| id | kind | source |", "|---|---|---|"]
    for e in kept:
        lines.append(f"| {e['id']} | {e.get('kind')} | {e.get('source', '?')} |")
    (out / "translation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {out / 'translation-report.md'}")


def main() -> int:
    ap = argparse.ArgumentParser(description="hiviz translator emit")
    ap.add_argument("--ir", required=True)
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="Agent instructions")
    ap.add_argument("--check", action="store_true",
                    help="verify live files at --out against the IR emission instead of writing")
    a = ap.parse_args()
    kept, dropped = load_ir(Path(a.ir))
    kinds = {k: sum(1 for e in kept if e.get("kind") == k) for k in KIND_ORDER}
    print(f"IR: {len(kept)} entries kept, {len(dropped)} dedup-dropped "
          f"(safety={kinds['safety']} invariant={kinds['invariant']} "
          f"rule={kinds['rule']} fact={kinds['fact']})")
    if a.check:
        return check(kept, a.target, Path(a.out), a.name)
    emit(kept, a.target, Path(a.out), a.name)
    report(kept, dropped, a.target, Path(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
