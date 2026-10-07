#!/usr/bin/env python3
"""hiviz apply verifier — did apply change exactly what was approved? Deterministic, no model, stdlib only.

Reads the decisions file (the audit report's rows plus a DECISION column), compares every file it names with its
`<file>.bak-<date>` backup, and checks:
  * rows decided no / keep / empty, and every ⚪ Kept safe line: unchanged
  * rows decided yes: the verb's edit is there (delete/disable: gone; rewrite/merge: changed — the new text is
    listed for a human to read, a machine cannot judge it)
  * rows decided as-condition: always listed for a human (the condition is free text)
  * nothing else changed: no other line removed or altered, no added line that no decision covers
  * every edited file has a backup, and no backup exists for a file no decision names
  * the ledger has an entry per approved decision (core/APPLY.md, step 5)
Blank lines are ignored (deleting a bullet often leaves one). The verifier never writes anything but --out.

Row status: OK · REVIEW (needs a human look) · UNVERIFIABLE (cannot be located / compared) · FAIL.
Every FAIL says what to do: `restore` the file from its backup, or `apply` the missing approved edit.
Exit: 0 no FAIL · 1 any FAIL (UNVERIFIABLE too with --strict) · 2 unusable input.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "render"))
import hvfmt  # noqa: E402
import report as rp  # noqa: E402

BAK = re.compile(r"\.bak-[\w.-]+$")
LEDGER_KEYS = ("file", "marker", "written_at", "model", "reason", "action")
WORST = {"FAIL": 0, "UNVERIFIABLE": 1, "REVIEW": 2, "OK": 3}


def split_lines(text: str) -> list[str]:
    lines = re.split(r"\r\n|\r|\n", text.lstrip("\ufeff"))
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def read_lines(p: Path) -> list[str]:
    return split_lines(p.read_text(encoding="utf-8", errors="replace"))


def norm(s: str) -> str:
    return re.sub(r"[`\s]+", " ", s).strip().lower()


def key(p: Path | str) -> str:
    return os.path.normcase(os.path.abspath(p))


def fragments(quote: str) -> list[str]:
    return [n for n in (norm(p) for p in re.split(r"…|\.\.\.", quote)) if n]


def find_ordered(text: str, frs: list[str]) -> bool:
    pos = 0
    for f in frs:
        i = text.find(f, pos)
        if i < 0:
            return False
        pos = i + len(f)
    return True


def anchor(lines: list[str], lo: int | None, hi: int | None, frs: list[str]) -> tuple[int | None, int | None, str]:
    """Where the row's text sits in `lines`. The audit's line numbers are trusted when the quote is there;
    otherwise the quote is searched. -> (lo, hi, note) or (None, None, reason)."""
    n = len(lines)
    span = (hi - lo + 1) if lo and hi else 1
    texts = [norm(x) for x in lines]

    def window(i: int) -> str:
        return " ".join(texts[i:i + span])

    if lo and hi and 1 <= lo <= hi <= n and (not frs or find_ordered(window(lo - 1), frs)):
        return lo, hi, ""
    if not frs:
        return None, None, "no quoted line, and the stated lines do not exist"
    hits = [i for i in range(0, max(0, n - span + 1)) if find_ordered(window(i), frs)]
    if not hits:
        return None, None, "the quoted line was not found"
    if len(hits) > 1:
        if not lo:
            return None, None, f"the quoted line appears {len(hits)} times and no line number was given"
        dist = sorted(abs(i + 1 - lo) for i in hits)
        if dist[0] == dist[1]:
            return None, None, f"the quoted line appears {len(hits)} times"
        hits = [min(hits, key=lambda i: abs(i + 1 - lo))]
    i = hits[0]
    note = f"line number was {lo}, found at {i + 1}" if lo and lo != i + 1 else ""
    return i + 1, i + span, note


@dataclass
class Side:
    row: rp.Row
    kind: str                      # yes | cond | hold | unknown
    path: Path
    lo: int | None
    hi: int | None
    quote: str
    label: str = ""                # what the decision cell said, for messages
    lo_a: int | None = None        # anchored span in the compared text
    hi_a: int | None = None
    note: str = ""


@dataclass
class Result:
    id: str
    status: str
    detail: str
    where: str = ""
    decision: str = ""
    verb: str = ""
    action: str = ""               # restore | apply | review | report | ""
    old: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)


def kind_of(r: rp.Row) -> tuple[str, str]:
    cell = r.decision.strip().strip("`*").strip()
    low = cell.lower()
    if r.sec == "safe" or r.verb == "keep":
        return "hold", "kept-safe" if r.sec == "safe" else "keep"
    if not low:
        return "hold", "empty"
    if low in ("yes", "y"):
        return "yes", "yes"
    if low in ("no", "n", "keep", "k"):
        return "hold", low
    if re.match(r"as[- ]condition\b", low):
        return "cond", cell
    return "unknown", cell


def parse_loc(loc: str) -> tuple[str, int | None, int | None]:
    path, ln = rp.split_loc(loc)
    if not ln:
        return path, None, None
    a, _, b = ln.partition("-")
    return path, int(a), int(b or a)


def ctime(p: Path) -> float:
    """When the file came to be on this machine. `cp -p` / copy2 keep the old mtime but not the ctime, so this is
    max(ctime, mtime): a backup made by this apply is never older than the decisions it carried out."""
    st = p.stat()
    return max(st.st_ctime, st.st_mtime)


def newest_backup(path: Path, since: float) -> Path | None:
    """The backup this apply made: `<file>.bak-*`, newest name, not older than the decisions file. An older one
    belongs to an earlier apply and would show that apply's edits as unapproved."""
    cands = sorted(p for p in path.parent.glob(path.name + ".bak-*") if BAK.search(p.name) and ctime(p) >= since)
    return cands[-1] if cands else None


def fmt_lines(nums: list[int]) -> str:
    nums = sorted(nums)
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] <= nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ", ".join(out)


def diff_file(old: list[str], new: list[str]) -> tuple[set[int], list[dict]]:
    """Blank lines are dropped on both sides. -> (old line numbers removed or changed, hunks)."""
    so = [i for i, x in enumerate(old) if x.strip()]
    sn = [i for i, x in enumerate(new) if x.strip()]
    sm = difflib.SequenceMatcher(None, [old[i].rstrip() for i in so], [new[i].rstrip() for i in sn], autojunk=False)
    hunks, changed = [], set()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        nums = [so[k] + 1 for k in range(i1, i2)]
        changed.update(nums)
        hunks.append({"old": nums, "old_text": [old[so[k]] for k in range(i1, i2)],
                      "new": [sn[k] + 1 for k in range(j1, j2)], "new_text": [new[sn[k]] for k in range(j1, j2)]})
    return changed, hunks


def verify_file(path: Path, sides: list[Side], base: str, since: float) -> tuple[list[Result], list[Result], dict]:
    """-> (per-side results, file-level results, info)."""
    shown = rp.short(str(path), base)
    cur = read_lines(path) if path.exists() else None
    bak = newest_backup(path, since)
    old = read_lines(bak) if bak else None
    info = {"file": str(path), "backup": str(bak) if bak else None, "hunks": 0}
    out: list[Result] = []
    file_level: list[Result] = []
    if cur is None:
        for s in sides:
            out.append(Result(s.row.id, "FAIL", f"{shown} does not exist", shown, s.label, s.row.verb, "restore"))
        return out, file_level, info
    text = old if old is not None else cur
    for s in sides:
        s.lo_a, s.hi_a, s.note = anchor(text, s.lo, s.hi, fragments(s.quote))
    if old is None:   # nothing to compare with: conclusions only from the current file
        edited = False
        joined = norm(" ".join(cur))
        for s in sides:
            frs = fragments(s.quote)
            if not frs and s.lo_a is None:
                out.append(Result(s.row.id, "UNVERIFIABLE", f"no backup, and {s.note}", shown, s.label, s.row.verb))
                continue
            gone = bool(frs) and not find_ordered(joined, frs)
            at = f"{shown}:{s.lo_a}" if s.lo_a else (f"{shown}:{s.lo}" if s.lo else shown)
            if s.kind in ("yes", "cond") and gone:
                edited = True
                out.append(Result(s.row.id, "FAIL", "the line is gone but there is no backup — an edit without a backup",
                                  at, s.label, s.row.verb, "report"))
            elif s.kind in ("yes", "cond"):
                out.append(Result(s.row.id, "UNVERIFIABLE", "no backup, and the line is still there — cannot tell "
                                  "whether anything was applied", at, s.label, s.row.verb))
            else:
                out.append(Result(s.row.id, "FAIL" if gone else "OK",
                                  "the line is gone and there is no backup" if gone else "unchanged; the file has no backup, so it was not edited",
                                  at, s.label, s.row.verb, "report" if gone else ""))
        if edited:
            file_level.append(Result(f"file:{path.name}", "FAIL", f"{shown} was edited without a backup (invariant: never edit "
                                     f"without {path.name}.bak-<date>)", shown, "", "", "report"))
        return out, file_level, info

    changed, hunks = diff_file(old, cur)
    info["hunks"] = len(hunks)
    covered: set[int] = set()
    line_eff: dict[int, set[str]] = {}   # old line -> what the decisions on it permit: free | remove | hold
    insert_anywhere = False              # a merge / condition may put text elsewhere in the file
    for s in sides:
        if s.lo_a is None:
            continue
        span = {n for n in range(s.lo_a, s.hi_a + 1) if old[n - 1].strip()}
        covered |= span
        free = s.kind == "cond" or (s.kind == "yes" and s.row.verb not in ("delete", "disable"))
        for n in span:
            line_eff.setdefault(n, set()).add("free" if free else "remove" if s.kind == "yes" else "hold")
        insert_anywhere = insert_anywhere or (free and (s.kind == "cond" or s.row.verb == "merge"))
    review_inserts = [h for h in hunks if not h["old"]] if insert_anywhere else []

    for s in sides:
        rid = s.row.id
        if s.lo_a is None:
            out.append(Result(rid, "UNVERIFIABLE", f"cannot locate the line in the backup: {s.note}", shown, s.label, s.row.verb))
            continue
        span = {n for n in range(s.lo_a, s.hi_a + 1) if old[n - 1].strip()}
        touched = span & changed
        where = f"{shown}:{s.lo_a}" + (f"-{s.hi_a}" if s.hi_a != s.lo_a else "")
        mine = [h for h in hunks if set(h["old"]) & span]
        old_t = [t for h in mine for t in h["old_text"]]
        new_t = [t for h in mine for t in h["new_text"]]
        if s.kind == "cond" or s.row.verb == "merge":
            new_t += [t for h in review_inserts for t in h["new_text"]]
        note = f" ({s.note})" if s.note else ""
        verb = s.row.verb
        if s.kind in ("hold", "unknown"):
            if touched:
                what = "a kept-safe (invariant) line" if s.label == "kept-safe" else f"a row decided '{s.label}'"
                out.append(Result(rid, "FAIL", f"{what} was changed: line {fmt_lines(sorted(touched))}",
                                  where, s.label, verb, "restore", old_t, new_t))
            elif s.kind == "unknown":
                out.append(Result(rid, "REVIEW", f"unrecognized DECISION '{s.label}' — treated as undecided; the line stayed" + note,
                                  where, s.label, verb, "review"))
            else:
                out.append(Result(rid, "OK", "unchanged" + note, where, s.label, verb))
        elif s.kind == "yes" and verb in ("delete", "disable"):
            if touched == span:
                out.append(Result(rid, "OK", f"removed line {fmt_lines(sorted(span))}" + note, where, s.label, verb, "", old_t))
            elif touched:
                out.append(Result(rid, "FAIL", f"only part of the block was removed (line {fmt_lines(sorted(span - touched))} is still there)",
                                  where, s.label, verb, "apply", old_t, new_t))
            else:
                out.append(Result(rid, "FAIL", "approved, not applied — the line is still there", where, s.label, verb, "apply"))
        elif s.kind == "yes" and verb != "verify":   # rewrite, merge, anything else with an edit
            if touched == span:
                out.append(Result(rid, "REVIEW", "edited as approved — the new text is yours to read" + note,
                                  where, s.label, verb, "review", old_t, new_t))
            elif touched:
                out.append(Result(rid, "REVIEW", f"only part of the block changed (line {fmt_lines(sorted(span - touched))} did not)" + note,
                                  where, s.label, verb, "review", old_t, new_t))
            else:
                out.append(Result(rid, "FAIL", "approved, not applied — the line did not change", where, s.label, verb, "apply"))
        elif touched:   # as-condition, or `verify` decided yes: free text, no machine verdict
            out.append(Result(rid, "REVIEW", "changed — check it matches the condition" + note, where, s.label, verb,
                              "review", old_t, new_t))
        elif s.kind == "yes":
            out.append(Result(rid, "OK", "no edit required" + note, where, s.label, verb))
        else:
            out.append(Result(rid, "REVIEW", "unchanged — the condition may not have applied" + note, where, s.label, verb, "review"))

    loose = sorted(changed - covered)
    if loose:
        lost = [t for h in hunks if set(h["old"]) & set(loose) for t in h["old_text"]]
        file_level.append(Result(f"file:{path.name}", "FAIL", f"{shown}: line {fmt_lines(loose)} was removed or changed but no decision "
                                 f"covers it (e.g. “{lost[0].strip()[:60]}”)", shown, "", "", "restore", lost, []))
    extra: list[str] = []
    surplus: list[str] = []
    for h in hunks:
        if not h["new_text"]:
            continue
        if not h["old"]:                          # text appeared out of nowhere
            if not insert_anywhere:
                extra += h["new_text"]
            continue
        effs = set().union(*(line_eff.get(n, {"loose"}) for n in h["old"]))
        if "free" in effs:
            # neighbouring edits merge into one hunk, so a deletion's replacement cannot be told from a rewrite's text:
            # more new lines than the rewritten rows had is shown to a human instead of failing
            room = sum("free" in line_eff.get(n, ()) for n in h["old"])
            if "remove" in effs and len(h["new_text"]) > room:
                surplus += h["new_text"]
        elif "hold" not in effs:                  # a hold row's replacement is already FAILed on its own row
            extra += h["new_text"]
    if surplus:
        file_level.append(Result(f"file:{path.name}", "REVIEW", f"{shown}: {len(surplus)} line(s) added next to a deletion, more than the "
                                 f"rewritten rows held — make sure they belong to the rewrite (e.g. “{surplus[0].strip()[:60]}”)",
                                 shown, "", "", "review", [], surplus))
    if extra:
        file_level.append(Result(f"file:{path.name}", "FAIL", f"{shown}: {len(extra)} line(s) added that no decision covers "
                                 f"(e.g. “{extra[0].strip()[:60]}”)", shown, "", "", "restore", [], extra))
    return out, file_level, info


def check_ledger(path: Path, approved: list[Side]) -> Result:
    if not path.exists():
        return Result("ledger", "FAIL", f"{path} does not exist — apply step 5 (one ledger line per approved decision) was skipped",
                      str(path), action="apply")
    entries, bad = [], []
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            miss = [k for k in LEDGER_KEYS if k not in entry] if isinstance(entry, dict) else list(LEDGER_KEYS)
        except ValueError:
            entry, miss = None, ["valid JSON"]
        if miss:
            bad.append(f"line {n} lacks {', '.join(miss)}")
        else:
            entries.append(entry)
    missing = []
    for s in approved:
        rid, quote = s.row.id, norm(s.quote)
        for entry in entries:
            marker = norm(str(entry["marker"]))
            by_id = re.search(rf"(?<![\w-]){re.escape(rid)}(?![\w-])", str(entry["reason"]), re.I)
            if key(entry["file"]) == key(s.path) and (by_id or (quote and marker and (marker in quote or quote in marker))):
                break
        else:
            missing.append(rid)
    if bad or missing:
        parts = ([f"no entry for {', '.join(sorted(set(missing)))}"] if missing else []) + bad[:3]
        return Result("ledger", "FAIL", f"{path.name}: " + "; ".join(parts), str(path), action="apply")
    return Result("ledger", "OK", f"{len(approved)} approved decision(s), all recorded in {path.name}", str(path))


def run(decisions: Path, base: Path, ledger: Path | None, scope: list[Path] | None) -> dict:
    rep = rp.parse(decisions.read_text(encoding="utf-8-sig"))
    rows = rp.all_rows(rep) if rep else []
    if not rows:
        raise ValueError(f"{decisions}: no decision rows found (expected the report's tables with a DECISION column)")
    shown_base = rp.common_dir(rows)
    started = ctime(decisions)
    by_file: dict[str, tuple[Path, list[Side]]] = {}
    approved: list[Side] = []

    def add(row: rp.Row, kind: str, label: str, loc: str, quote: str, primary: bool) -> None:
        path_s, lo, hi = parse_loc(loc)
        p = Path(path_s)
        p = p if p.is_absolute() else base / p
        side = Side(row, kind, p, lo, hi, quote, label)
        by_file.setdefault(key(p), (p, []))[1].append(side)
        if primary and kind in ("yes", "cond") and row.verb != "keep" and row.sec != "safe":
            approved.append(side)

    for r in rows:
        kind, label = kind_of(r)
        add(r, kind, label, r.where, rp.unwrap(r.line), True)
        if r.other:   # a conflict row names both sides
            add(r, kind, label, r.other, r.other_q, False)

    merged: dict[str, Result] = {}
    file_rows: list[Result] = []
    infos = []
    for p, sides in by_file.values():
        side_res, f_res, info = verify_file(p, sides, shown_base, started - 2)
        infos.append(info)
        file_rows += f_res
        for res in side_res:
            cur = merged.get(res.id)
            if cur is None:
                merged[res.id] = res
                continue
            worst, other = (res, cur) if WORST[res.status] < WORST[cur.status] else (cur, res)
            if other.status in ("FAIL", "UNVERIFIABLE"):   # a REVIEW / OK second side adds nothing the first does not say
                worst.detail = f"{worst.detail} · {other.where}: {other.detail}"
            worst.old += other.old
            worst.new += other.new
            merged[res.id] = worst
    results = [merged[i] for i in dict.fromkeys(r.id for r in rows) if i in merged] + file_rows

    # backups nobody asked for: a file was probably edited without a decision
    decided = set(by_file)
    dirs = [(d, True) for d in (scope or [])] or [(p.parent, False) for p, _ in by_file.values()]
    seen: set[str] = set()
    for d, deep in dirs:
        if not d.is_dir():
            continue
        for b in (d.rglob("*.bak-*") if deep else d.glob("*.bak-*")):
            if not (b.is_file() and BAK.search(b.name)) or key(b) in seen:
                continue
            seen.add(key(b))
            base_file = Path(BAK.sub("", str(b)))
            if key(base_file) not in decided and ctime(b) >= started - 2:
                shown = rp.short(str(b), shown_base)
                results.append(Result(f"stray:{b.name}", "FAIL", f"{shown}: a backup was made for a file no decision names "
                                      f"({base_file.name}) — it was probably edited without a decision", shown, "", "", "review"))
    if ledger is not None:
        results.append(check_ledger(ledger, approved))
    counts = {s: sum(r.status == s for r in results) for s in WORST}
    verdict = "FAIL" if counts["FAIL"] else "REVIEW" if (counts["REVIEW"] or counts["UNVERIFIABLE"]) else "PASS"
    return {"verdict": verdict, "summary": counts, "decisions": str(decisions), "rows": results, "files": infos}


def _decision(r: Result) -> str:
    """The table shows the decision's keyword; a condition's text is in the JSON and in the review block."""
    return "as-condition" if r.decision.lower().startswith("as-condition") else r.decision


def _block(r: Result) -> list[str]:
    return ["- " + t.strip()[:110] for t in r.old[:4]] + ["+ " + t.strip()[:110] for t in r.new[:4]]


def render_pretty(res: dict) -> str:
    out = [hvfmt.heading("apply verify", f"{Path(res['decisions']).name} · {len(res['rows'])} checks · {len(res['files'])} file(s)")]
    rows = [[r.status, r.id, _decision(r), r.verb, r.where,
             r.detail + (f"  → {r.action}" if r.action in ("restore", "apply") else "")] for r in res["rows"]]
    out.append(hvfmt.table(["status", "row", "decision", "verb", "where", "detail"], rows, status_col=0, dim_cols=(2, 3, 4)))
    out.append(hvfmt.summary(res["summary"], ["FAIL", "UNVERIFIABLE", "REVIEW", "OK"]) + "   → " + res["verdict"])
    shown = [r for r in res["rows"] if r.status in ("REVIEW", "FAIL") and (r.old or r.new)]
    if shown:
        out.append(hvfmt.heading("read these edits"))
        for r in shown:
            out.append(f"  {hvfmt.badge(r.status)}  {hvfmt.style(r.id, 'bold')}  {hvfmt.style(r.where, 'gray')}")
            out += ["    " + hvfmt.style(line, "red" if line.startswith("- ") else "green") for line in _block(r)]
    return "\n".join(out)


def render_md(res: dict) -> str:
    out = [f"# apply verify — {res['verdict']}", "", "| status | row | decision | verb | where | detail |", "|---|---|---|---|---|---|"]
    for r in res["rows"]:
        detail = r.detail + (f" → {r.action}" if r.action in ("restore", "apply") else "")
        out.append("| " + " | ".join(c.replace("|", "\\|") for c in (r.status, r.id, _decision(r), r.verb, r.where, detail)) + " |")
    for r in (r for r in res["rows"] if r.status in ("REVIEW", "FAIL") and (r.old or r.new)):
        out += ["", f"{r.id} ({r.status}) {r.where}", "```diff", *_block(r), "```"]
    s = res["summary"]
    out += ["", f"{s['FAIL']} fail · {s['UNVERIFIABLE']} unverifiable · {s['REVIEW']} review · {s['OK']} ok → {res['verdict']}"]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="hiviz apply verifier — only approved edits happened")
    ap.add_argument("--decisions", default=".hiviz/decisions.md")
    ap.add_argument("--base", default=".", help="dir against which relative paths in the `where` column resolve")
    ap.add_argument("--ledger", default=None, help="default: ledger.jsonl next to the decisions file")
    ap.add_argument("--no-ledger", action="store_true", help="do not check the ledger")
    ap.add_argument("--scope", action="append", default=None,
                    help="dir scanned recursively for backups no decision names (repeatable; default: the directories of the decided files)")
    ap.add_argument("--strict", action="store_true", help="UNVERIFIABLE rows fail too")
    ap.add_argument("--out", default=None, help="optional JSON output path")
    hvfmt.add_format_arg(ap)
    a = ap.parse_args()
    hvfmt.configure(a.format)
    dec = Path(a.decisions)
    if not dec.exists():
        print(f"no decisions file at {dec} — run the hv-apply procedure on an exported or filled decisions.md", file=sys.stderr)
        return 2
    ledger = None if a.no_ledger else Path(a.ledger) if a.ledger else dec.parent / "ledger.jsonl"
    try:
        res = run(dec, Path(a.base), ledger, [Path(s) for s in a.scope] if a.scope else None)
    except (ValueError, OSError) as e:
        print(f"apply verify: {e}", file=sys.stderr)
        return 2
    doc = {k: v for k, v in res.items() if k != "rows"} | {"rows": [r.__dict__ for r in res["rows"]]}
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(hvfmt.dumps(doc) if hvfmt.is_json() else render_pretty(res) if hvfmt.is_pretty() else render_md(res))
    s = res["summary"]
    return 1 if s["FAIL"] or (a.strict and s["UNVERIFIABLE"]) else 0


if __name__ == "__main__":
    sys.exit(main())
