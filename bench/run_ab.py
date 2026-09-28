#!/usr/bin/env python3
"""hiviz shed-bench runner v2: A/B on deterministic tasks with real token metrics.

Uses `omp --mode=json` to capture provider-reported usage (input/output tokens,
cache reads, cost) per run. Deterministic verifiers, no LLM judges.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from statistics import median

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent
HOME = Path.home()
TASKS = ["harden-client", "bug-hunt"]  # real-jwt archived: saturates 10/10 both arms


def sh(cmd: list[str], cwd=None, timeout=2400, env=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, env=env)


def setup_profile(name: str, corpus: Path, model: str) -> Path:
    prof = HOME / ".omp/profiles" / name / "agent"
    if prof.parent.exists():
        shutil.rmtree(prof.parent)
    (prof / "skills").mkdir(parents=True)
    src_md = next((corpus / n for n in ("CLAUDE.md", "AGENTS.md") if (corpus / n).exists()), None)
    if src_md is not None:
        (prof / "AGENTS.md").write_text(src_md.read_text(encoding="utf-8"), encoding="utf-8")
    for d in sorted(set(corpus.glob("*skills*")) | set(corpus.glob("superpowers*")) | set(corpus.glob("*skills*/skills"))):
        if not d.is_dir():
            continue
        for s in sorted(d.iterdir()):
            if s.is_dir() and (s / "SKILL.md").exists():
                shutil.copytree(s, prof / "skills" / f"{d.name}-{s.name}")
    src_models = HOME / ".omp" / "agent" / "models.yml"
    if src_models.exists():
        shutil.copy2(src_models, prof / "models.yml")   # custom providers must exist in the profile too
    (prof / "config.yml").write_text(
        f"modelRoles:\n  default: {model}\nmemory:\n  backend: local\n"
        f"skills:\n  customDirectories:\n    - {(prof / 'skills').as_posix()}\n",
        encoding="utf-8")
    src = sqlite3.connect(str(HOME / ".omp/agent/agent.db"))
    dst = sqlite3.connect(str(prof / "agent.db"))
    with dst:
        src.backup(dst)
    src.close(); dst.close()
    return prof


def seed_workdir(task: str, wd: Path) -> None:
    wd.mkdir(parents=True, exist_ok=True)
    fx = BENCH / "tasks" / task / "fixtures"
    if fx.exists():
        for f in fx.iterdir():
            if f.is_dir():
                shutil.copytree(f, wd / f.name, dirs_exist_ok=True)
            else:
                shutil.copy2(f, wd / f.name)


def verify(task: str, wd: Path, config_dir: Path) -> tuple[bool, str, float]:
    tdir = BENCH / "tasks" / task
    for side in ("conventions.json", "qa.json"):
        src = config_dir / side
        if src.exists():
            shutil.copy2(src, wd / side)
    r = sh([sys.executable, str(tdir / "verify.py")], cwd=wd, timeout=120)
    out = (r.stdout or r.stderr).strip()
    m = re.search(r"SCORE:\s*([0-9.]+)(?:/10)?", out)
    score = float(m.group(1)) if m else (10.0 if r.returncode == 0 else 0.0)
    return r.returncode == 0, out.splitlines()[-1] if out else "?", score


def parse_json_metrics(jsonl: str) -> dict:
    """Extract aggregated usage from omp --mode=json output.
    input_tokens is TOTAL input seen by the model: fresh input + cache reads.
    A run where ANY turn reports zero usage (local proxies) is estimated
    CONSISTENTLY from the transcript (chars/4) — never a real/estimated mix."""
    m = {"input_tokens": 0, "output_tokens": 0, "cache_read": 0,
         "cost_total": 0.0, "turns": 0, "tokens_approx": False}
    turns = []  # (prior_chars, out_chars, usage)
    seen_chars = 0
    for line in jsonl.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") not in ("message_start", "message_end"):
            continue
        msg = d.get("message") or {}
        parts = (msg.get("content") or []) if isinstance(msg.get("content"), list) else []
        text_len = sum(len(p.get("text", "")) for p in parts if isinstance(p, dict))
        if msg.get("role") != "assistant":
            seen_chars += text_len
            continue
        if d.get("type") == "message_end":
            u = msg.get("usage") or {}
            turns.append((seen_chars, text_len, u))
        seen_chars += text_len
    m["turns"] = len(turns)
    if turns and all((u.get("input", 0) + u.get("cacheRead", 0) + u.get("output", 0)) > 0
                     for _, _, u in turns):
        for _, _, u in turns:
            m["input_tokens"] += u.get("input", 0) + u.get("cacheRead", 0)
            m["output_tokens"] += u.get("output", 0)
            m["cache_read"] += u.get("cacheRead", 0)
            m["cost_total"] += (u.get("cost") or {}).get("total", 0.0)
    else:
        m["tokens_approx"] = True
        for prior, out_len, _ in turns:
            m["input_tokens"] += prior // 4
            m["output_tokens"] += out_len // 4
    return m


def run_arm_task(profile: str, task: str, repeat: int, runs_dir: Path, label_dir: Path) -> dict:
    wd = runs_dir / task / f"r{repeat}"
    seed_workdir(task, wd)
    task_md = label_dir / "tasks" / task / "task.md"
    if not task_md.exists():
        task_md = BENCH / "tasks" / task / "task.md"
    prompt = task_md.read_text(encoding="utf-8")
    prompt += "\n\nWork strictly in the current directory. No git commits."
    t0 = time.monotonic()
    r = sh(["omp", "--profile", profile, "-p", prompt, "--mode=json"], cwd=wd)
    wall = round(time.monotonic() - t0)
    ok, detail, score = verify(task, wd, label_dir)
    (wd / "omp_transcript.jsonl").write_text(r.stdout or "", encoding="utf-8", errors="replace")
    metrics = parse_json_metrics(r.stdout or "")
    row = {"task": task, "rep": repeat, "pass": ok, "detail": detail, "score": score,
           "wall_s": wall, **metrics}
    (wd / "run_meta.json").write_text(json.dumps(
        {"task": task, "rep": repeat, "wall_s": wall}), encoding="utf-8")
    return row


def _wall_stats(sub: list[dict]) -> dict:
    walls = [r["wall_s"] for r in sub if r.get("wall_s") is not None]
    if not walls:
        return {"wall_med": None, "wall_min": None, "wall_max": None}
    return {"wall_med": median(walls), "wall_min": min(walls), "wall_max": max(walls)}


def aggregate(rows: list[dict]) -> list[dict]:
    """Per-task per-arm medians."""
    agg = []
    for arm in sorted({r.get("arm", "?") for r in rows}):
        for task in sorted({r["task"] for r in rows}):
            sub = [r for r in rows if r.get("arm") == arm and r["task"] == task]
            if not sub:
                continue
            agg.append({
                "arm": arm, "task": task,
                "pass_rate": sum(r["pass"] for r in sub) / len(sub),
                "score_med": median(r["score"] for r in sub),
                "score_min": min(r["score"] for r in sub),
                "score_max": max(r["score"] for r in sub),
                **_wall_stats(sub),
                "tok_in_med": median(r["input_tokens"] for r in sub),
                "tok_out_med": median(r["output_tokens"] for r in sub),
                "cache_med": median(r["cache_read"] for r in sub),
                "cost_med": median(r["cost_total"] for r in sub),
                "turns_med": median(r["turns"] for r in sub),
                "n": len(sub),
            })
    return agg


def render_results(agg: list[dict], raw: list[dict]) -> str:
    lines = ["# Shed-Bench Results", "",
             "| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for a in agg:
        wall = (f"{a['wall_med']:.0f}s ({a['wall_min']}-{a['wall_max']})"
                if a['wall_med'] is not None else "n/a")
        lines.append(
            f"| {a['arm']} | {a['task']} | {a['pass_rate']:.0%} | "
            f"{a['score_med']:.1f} ({a['score_min']:.0f}-{a['score_max']:.0f}) | "
            f"{wall} | "
            f"{a['tok_in_med']:,.0f} | {a['tok_out_med']:,.0f} | "
            f"{a['cache_med']:,.0f} | {a['cost_med']:.4f} | {a['turns_med']:.0f} |")
    # summary deltas
    tasks = sorted({a["task"] for a in agg})
    arms = sorted({a["arm"] for a in agg})
    if len(arms) == 2:
        lines += ["", "## Deltas (A → B)", "",
                  "| task | wall | tok in | tok out | cost |",
                  "|---|---:|---:|---:|---:|"]
        for t in tasks:
            ra = next((a for a in agg if a["arm"] == arms[0] and a["task"] == t), {})
            rb = next((a for a in agg if a["arm"] == arms[1] and a["task"] == t), {})
            def delta(key, fmt="{:+.0f}%"):
                va, vb = ra.get(key, 0), rb.get(key, 0)
                if va == 0:
                    return "n/a"
                return fmt.format((vb - va) / va * 100)
            lines.append(f"| {t} | {delta('wall_med')} | {delta('tok_in_med')} | "
                         f"{delta('tok_out_med')} | {delta('cost_med', '{:+.1f}%')} |")
    lines += ["", f"_Generated {time.strftime('%Y-%m-%d %H:%M')} · {len(raw)} runs total · model {raw[0].get('model', '?') if raw else '?'} · tok in = fresh input + cache reads_"]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="hiviz shed-bench v2")
    ap.add_argument("--arm-a", required=True)
    ap.add_argument("--arm-b", default=None)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--model", default="zai/glm-5.3:max")
    ap.add_argument("--tasks", nargs="*", default=TASKS)
    ap.add_argument("--setup-only", action="store_true")
    ap.add_argument("--resume", default=None, help="existing run dir: completed (arm,task,rep) with transcripts are kept")
    a = ap.parse_args()

    arms = {"a": a.arm_a}
    if a.arm_b:
        arms["b"] = a.arm_b
    profiles = {}
    config_dirs = {}
    for k, corp in arms.items():
        corp_path = Path(corp)
        if (corp_path / "corpus").is_dir():          # config dir given -> mount its corpus/
            config_dirs[k] = corp_path
            corp_path = corp_path / "corpus"
        else:
            config_dirs[k] = corp_path.parent
        profiles[k] = f"bench-{k}"
        prof = setup_profile(profiles[k], corp_path, a.model)
        n = len(list((prof / "skills").glob("*/")))
        print(f"[arm {k}] profile {profiles[k]}: {n} skills, corpus mounted={(prof / 'AGENTS.md').exists()}, model {a.model}")
    if a.setup_only:
        return 0
    runs_dir = Path(a.resume) if a.resume else BENCH / "runs" / time.strftime("%Y%m%d-%H%M%S")
    label_dir = config_dirs["a"]   # labeling (qa/conventions/task.md) lives in the baseline arm's config
    rows = []
    for k, prof_name in profiles.items():
        for task in a.tasks:
            for rep in range(1, a.repeats + 1):
                wd = runs_dir / f"arm-{k}" / task / f"r{rep}"
                done = wd / "omp_transcript.jsonl"
                if a.resume and done.exists() and done.stat().st_size > 0:
                    print(f"  resume arm {k} · {task} · r{rep}: kept (transcript on disk)")
                    metrics = parse_json_metrics(done.read_text(encoding="utf-8", errors="replace"))
                    ok, detail, score = verify(task, wd, label_dir)
                    meta = {}
                    if (wd / "run_meta.json").exists():
                        try:
                            meta = json.loads((wd / "run_meta.json").read_text(encoding="utf-8"))
                        except json.JSONDecodeError:
                            pass
                    row = {"task": task, "rep": rep, "pass": ok, "detail": detail, "score": score,
                           "wall_s": meta.get("wall_s"), **metrics}
                else:
                    row = run_arm_task(prof_name, task, rep, runs_dir / f"arm-{k}", label_dir)
                row["arm"] = k
                row["model"] = a.model
                rows.append(row)
                print(f"  arm {k} · {task} · r{rep}: {'PASS' if row['pass'] else 'FAIL'} "
                      f"({row['wall_s']}s, score {row['score']:.0f}, {row['input_tokens']:,}→{row['output_tokens']:,} tok, "
                      f"${row['cost_total']:.4f}) — {row['detail'][:50]}")

    agg = aggregate(rows)
    out_md = runs_dir / "results.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_results(agg, rows), encoding="utf-8")
    (runs_dir / "results.json").write_text(
        json.dumps({"model": a.model, "repeats": a.repeats, "aggregate": agg, "raw": rows}, indent=1), encoding="utf-8")
    sh([sys.executable, str(REPO / "render/report.py"), "--md", str(out_md),
        "--out", str(runs_dir / "results.html")])
    print(f"\nresults: {out_md} (+html)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
