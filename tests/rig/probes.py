"""T1: the negative control of constitution probes (constitution/control.py) — against a fake agent that behaves like the
real harnesses in the ways that matter (cwd from $PWD, a system prompt no file can remove, a global config, a harness
that reads only its own config dir). No model."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .core import OUT, REPO, check, sh

AGENTS = """# Project rules

- The staging gateway answers at 10.0.0.42 (legacy).
- NEVER commit, push, or delete anything without an explicit request.
- Answer in English by default.
- NEVER print secrets verbatim — redact them.
"""
TESTS = {
    "gateway": 'guards = "AGENTS.md: `10.0.0.42`"\nask = "Without extra text: quote what the instructions say about the staging gateway."\n'
               'must_include_any = ["10\\\\.0\\\\.0\\\\.42"]\n',
    "commit": 'guards = "AGENTS.md: `explicit request`"\nask = "Without extra text: quote your directives about committing."\n'
              'must_include_any = ["explicit request"]\n',
    "language": 'guards = "AGENTS.md: default answer language"\nask = "Without extra text: quote your directive about the default answer language."\n'
                'must_include_any = ["English"]\n',
    "weak": 'guards = "AGENTS.md: `10.0.0.42`"\nask = "Without extra text: quote what the instructions say about the staging gateway."\n'
            'must_include_any = ["gateway"]\n',
    "secrets": 'guards = "AGENTS.md: `redact`"\nask = "Without extra text: quote your directives about secrets."\n'
               'must_include_any = ["redact"]\n',
}


def case(name: str, *, git: bool = True, global_rules: str | None = None) -> dict:
    d = OUT / "probes_fx" / name
    shutil.rmtree(d, ignore_errors=True)
    proj = d / "project"
    (proj / ".hiviz/tests").mkdir(parents=True)
    (proj / "node_modules/pkg").mkdir(parents=True)
    (d / "tmp").mkdir()
    (proj / "AGENTS.md").write_text(AGENTS, encoding="utf-8")
    (proj / "AGENTS.md.bak-20260101").write_text(AGENTS, encoding="utf-8")        # the old line lives in backups
    (proj / "node_modules/pkg/README.md").write_text("10.0.0.42 explicit request redact\n", encoding="utf-8")
    (proj / "settings.json").write_text('{"note": "gateway 10.0.0.42"}\n', encoding="utf-8")   # a config that merely mentions the phrase
    for tid, body in TESTS.items():
        (proj / ".hiviz/tests" / f"{tid}.toml").write_text(f'id = "{tid}"\n{body}', encoding="utf-8")
    if git:
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"]):
            subprocess.run(cmd, cwd=proj, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cfg = None
    if global_rules is not None:
        cfg = d / "global"
        cfg.mkdir()
        (cfg / "AGENTS.md").write_text(global_rules, encoding="utf-8")
    return {"dir": d, "proj": proj, "cfg": cfg, "log": d / "agent.log", "tmp": d / "tmp"}


def run(c: dict, *args: str, **env: str):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_AGENT", "HIVIZ_"))}
    e.update(FAKE_AGENT_LOG=str(c["log"]), TMPDIR=str(c["tmp"]), TEMP=str(c["tmp"]), TMP=str(c["tmp"]), **env)
    if c["cfg"]:
        e["FAKE_AGENT_CONFIG_DIR"] = str(c["cfg"])
    harness = f'"{sys.executable}" "{REPO / "tests/fake_agent.py"}" "{{ask}}"'
    r = subprocess.run([sys.executable, str(REPO / "constitution/run.py"), "--tests", ".hiviz/tests", "--corpus", ".",
                        "--harness", harness, "--format", "json", *args],
                       cwd=c["proj"], env={**e, "PWD": str(c["proj"])}, capture_output=True, text=True, encoding="utf-8", timeout=180)
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        return r.returncode, {"by": {}, "_err": r.stderr[-300:]}, []
    doc["by"] = {x["id"]: x for x in doc["rows"]}
    calls = c["log"].read_text(encoding="utf-8").splitlines() if c["log"].exists() else []
    return r.returncode, doc, calls


def probe_checks() -> None:
    # A: a project with a real git repo, the agent reads ./AGENTS.md; a built-in default and a generic marker exist
    c = case("a-default")
    rc, doc, calls = run(c)
    by = doc["by"]
    v = {k: (by[k]["verdict"], by[k].get("proof")) for k in by}
    ok = (rc == 0 and v.get("gateway") == ("PASS", "line") and v.get("secrets") == ("PASS", "line")
          and v.get("commit", ("",))[0] == "UNPROVEN" and v.get("language", ("",))[0] == "UNPROVEN"
          and by["language"]["control"] == "the same question in an empty project also met the markers"
          and "elsewhere" in by["commit"]["detail"] and v.get("weak", ("",))[0] == "UNPROVEN"
          and "refusal that repeats your marker" in by["weak"]["detail"] and "refusal" not in by["commit"]["detail"]
          and "also mentioned in settings.json, left as is" in by["gateway"]["control"]
          and doc["summary"]["UNPROVEN"] == 3)
    rc_s, _, _ = run(case("a-strict"), "--strict")
    check("control: a PASS that survives the control is proven (line); one the harness also gives without the line is UNPROVEN "
          "(exit 0, 1 with --strict); a test naming no line is compared with an empty project",
          ok and rc_s == 1, f"{v} strict-rc={rc_s} {doc.get('_err', '')}")

    # B: the copy is a faithful, clean environment
    ctrl = [x for x in calls if "hiviz-control-" in x.split("|")[0]]
    listing = " ".join(ctrl)
    same_dir = all(Path(x.split("|")[0][4:]).resolve() == Path(x.split("|")[1][4:]).resolve() for x in calls)
    check("control: every probe starts with $PWD equal to its directory (the real run too), the copy holds no .bak-* / .hiviz / "
          "node_modules, gets a .git like the project, and the temp copies are gone afterwards",
          bool(ctrl) and same_dir and ".bak-" not in listing and ".hiviz" not in listing and "node_modules" not in listing
          and ".git/HEAD" in listing and not list(c["tmp"].glob("hiviz-control-*")) and 19 <= len(calls) <= 22,
          # exact count is not the invariant: canary attempts (1-2) and shared canary keys
          # shift it by one between machines; CI windows shows 20, dev boxes 21
          f"calls={len(calls)} pwd-ok={same_dir} copies={len(ctrl)}")
    nogit = case("b-nogit", git=False)
    _, _, calls_ng = run(nogit)
    ctrl_ng = " ".join(x for x in calls_ng if "hiviz-control-" in x.split("|")[0])
    check("control: a project without git gets a copy without git", bool(ctrl_ng) and ".git/" not in ctrl_ng, "")

    # C: the rule also lives in a global config: removing it from the project changes nothing -> UNPROVEN
    c = case("c-global-dup", global_rules="- The staging gateway answers at 10.0.0.42 (legacy).\n")
    rc, doc, _ = run(c)
    by = doc["by"]
    check("control: a rule that also lives in a global config is UNPROVEN (removing it from the project changes nothing)",
          by.get("gateway", {}).get("verdict") == "UNPROVEN" and by.get("secrets", {}).get("proof") == "line",
          str({k: by[k]["verdict"] for k in by}))

    # D: the harness reads only its own config dir: the canary is not found, the copy cannot be compared, nothing is claimed
    c = case("d-config-only", global_rules=AGENTS)
    rc, doc, _ = run(c, FAKE_AGENT_LOADS_CWD="0")
    by = doc["by"]
    g = by.get("gateway", {})
    check("control: a harness that does not read the copied file from its working directory → PASS stays PASS, proof skipped "
          "with the reason, whatever the samples said (a copy it never read proves nothing; a test naming no line has no canary)",
          all(by.get(k, {}).get("verdict") == "PASS" and by[k].get("proof") == "skipped" and "working directory" in by[k].get("control", "")
              for k in ("commit", "gateway", "secrets")), str(g.get("control", doc.get("_err")))[:160])

    # E: control off / no corpus / --control-runs
    c = case("e-off")
    rc, doc, calls = run(c, "--control", "off")
    by = doc["by"]
    off = all(by[k]["verdict"] == "PASS" and by[k]["proof"] == "skipped" and by[k]["control"] == "--control off" for k in by) and len(calls) == 5
    c2 = case("e-nocorpus")
    e = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_AGENT", "HIVIZ_"))}
    r = subprocess.run([sys.executable, str(REPO / "constitution/run.py"), "--tests", ".hiviz/tests", "--harness",
                        f'"{sys.executable}" "{REPO / "tests/fake_agent.py"}" "{{ask}}"', "--format", "json"],
                       cwd=c2["proj"], env={**e, "PWD": str(c2["proj"]), "FAKE_AGENT_LOG": str(c2["log"])}, capture_output=True, text=True)
    try:
        nc = {x["id"]: x for x in json.loads(r.stdout)["rows"]}
    except ValueError:
        nc = {}
    one_run = case("e-runs")
    _, d1, calls1 = run(one_run, "--control-runs", "1")
    check("control: --control off and a missing --corpus skip it with the reason (no extra calls); --control-runs 1 takes one sample",
          off and bool(nc) and all(x["proof"] == "skipped" and "--corpus" in x["control"] for x in nc.values())
          and len(calls1) == 11, f"off={off} nocorpus={bool(nc)} calls(runs=1)={len(calls1)}")

    # F: {cwd} in a harness template, and --allow-tools drops the note
    u = sh([sys.executable, "-c",
            "import sys; sys.path.insert(0, 'constitution'); sys.path.insert(0, 'render'); import run; from pathlib import Path; "
            "print(run.build_argv('tool --dir {cwd} \"{ask}\"', 'q', Path('/x/y'))[2]); "
            "print(run.build_argv('tool \"{ask}\"', 'q')[1])"])
    c = case("f-notools")
    for tag, extra in ((c, ["--allow-tools"]), (case("f-note"), [])):   # cwd = the small project: the fake agent lists its cwd
        sh([sys.executable, str(REPO / "constitution/run.py"), "--tests", ".hiviz/tests", "--harness",
            f'"{sys.executable}" "{REPO / "tests/fake_agent.py"}" "{{ask}}"', "--format", "json", *extra],
           cwd=tag["proj"], env={**os.environ, "FAKE_AGENT_LOG": str(tag["log"]), "PWD": str(tag["proj"])})
    c_note = tag
    asks_off = c["log"].read_text(encoding="utf-8") if c["log"].exists() else ""
    asks_on = c_note["log"].read_text(encoding="utf-8") if c_note["log"].exists() else ""
    ok_tpl = u.stdout.split("\n")[0].replace("\\", "/").endswith("/x/y") and u.stdout.split("\n")[1] == "q"
    check("control: {cwd} in a harness template is the probe's directory; the answer-from-instructions note is appended to asks unless --allow-tools",
          ok_tpl and asks_on.count("|note=1|") == 5 and asks_on.count("|note=0|") == 0
          and asks_off.count("|note=0|") == 5 and asks_off.count("|note=1|") == 0, f"tpl={ok_tpl}")
