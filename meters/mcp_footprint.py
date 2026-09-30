#!/usr/bin/env python3
"""hiviz meter: live MCP context footprint + usage telemetry.

For every MCP server in the discovered harness configs:
  - measures the standing context payload (initialize + tools/list →
    names + descriptions + inputSchemas) — what EVERY session pays;
  - mines harness session logs for actual invocations (mcp__<server>_ patterns),
    so "weight" and "usage" sit in one row: pay-vs-use.

Metrics kept (essential only): tools · bytes (weight) · tokens (cl100k when
available, else bytes/4 marked ~) · calls · last_used.

Never writes configs. Expands ${VAR} header values at runtime, never prints them.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path


try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def toks(b: bytes) -> tuple[int, bool]:
        return len(_enc.encode(b.decode("utf-8", "replace"), allowed_special="all")), False
except ImportError:
    def toks(b: bytes) -> tuple[int, bool]:
        return max(1, len(b) // 4), True  # rough approximation

HOME = Path.home()
INIT_PARAMS = {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "hiviz-meter", "version": "0.7.0"}}


def discover_configs(explicit: list[str] | None) -> list[tuple[str, Path]]:
    if explicit:
        return [("explicit", Path(p)) for p in explicit]
    found: list[tuple[str, Path]] = []
    candidates = [
        ("omp/default", HOME / ".omp/agent/mcp.json"),
        ("claude/global", HOME / ".claude.json"),
        ("claude/project", Path.cwd() / ".mcp.json"),
        ("codex/global", HOME / ".codex/config.toml"),
    ]
    import glob as _g
    for p in _g.glob(str(HOME / ".omp/profiles/*/agent/mcp.json")):
        candidates.append((f"omp/{Path(p).parts[-3]}", Path(p)))
    for label, p in candidates:
        if p.exists():
            found.append((label, p))
    return found


def load_servers(label: str, path: Path) -> dict[str, dict]:
    if path.suffix == ".toml":
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        raw = data.get("mcp_servers") or {}
        return {n: {"type": "stdio", "command": c.get("command", ""), "args": c.get("args", []),
                    "env": c.get("env", {})} for n, c in raw.items()}
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("mcpServers") or data.get("mcp_servers") or {}
    return {n: dict(c) for n, c in raw.items()}


def _send(fd_in, payload: dict) -> None:
    fd_in.write((json.dumps(payload) + "\n").encode())
    fd_in.flush()


def _read_result(fd_out, want_id: int) -> dict:
    for line in fd_out:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == want_id:
            if "error" in msg:
                raise RuntimeError(str(msg["error"].get("message", "rpc error"))[:120])
            return msg.get("result") or {}
    raise RuntimeError("server closed stdout before answering")


def stdio_tools_sync(cfg: dict, timeout: float) -> list:
    env = {**os.environ, **{k: v for k, v in (cfg.get("env") or {}).items()}}
    cmd, args = cfg.get("command", ""), [str(a) for a in (cfg.get("args") or [])]
    if sys.platform == "win32" and cmd in ("npx", "node"):
        cmd, args = "cmd", ["/c", cmd, *args]
    p = subprocess.Popen([cmd, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, env=env, cwd=cfg.get("cwd"))
    watchdog = threading.Timer(timeout, p.kill)
    watchdog.daemon = True
    watchdog.start()
    try:
        _send(p.stdin, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT_PARAMS})
        _read_result(p.stdout, 1)
        # note: "notifications/initialized" deliberately not sent — some local
        # servers (e.g. patched crawl4ai-mcp) close stdout on unknown messages.
        _send(p.stdin, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        return (_read_result(p.stdout, 2)).get("tools") or []
    finally:
        watchdog.cancel()
        try:
            p.stdin.close()  # EOF: well-behaved servers exit on their own
        except Exception:
            pass
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


def http_tools_sync(cfg: dict, timeout: float) -> list:
    headers = {"Content-Type": "application/json",
               # Streamable HTTP servers may answer as SSE and reject clients not accepting it
               "Accept": "application/json, text/event-stream",
               **{k: v for k, v in (cfg.get("headers") or {}).items()}}
    url = cfg.get("url", "")
    for k, v in list(headers.items()):
        if "${" in v:
            exp = os.path.expandvars(v)
            if exp == v:
                raise RuntimeError(f"env var not set for header '{k}'")
            headers[k] = exp

    def post(payload: dict) -> dict:
        r = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:  # session id arrives as a response header, not in the JSON body
                headers["Mcp-Session-Id"] = sid
            body = resp.read().decode("utf-8", "replace")
            if "id" not in payload:
                return {}  # notification: 202, no body
            if "text/event-stream" in (resp.headers.get("Content-Type") or ""):
                for ln in body.splitlines():
                    if ln.startswith("data:"):
                        try:
                            msg = json.loads(ln[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        if isinstance(msg, dict) and msg.get("id") == payload["id"]:
                            return msg
                raise RuntimeError("no JSON-RPC response in event stream")
            return json.loads(body)

    res = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT_PARAMS})
    if "error" in res:
        raise RuntimeError(str(res["error"].get("message", "rpc error"))[:120])
    headers["MCP-Protocol-Version"] = (res.get("result") or {}).get(
        "protocolVersion", INIT_PARAMS["protocolVersion"])
    try:
        post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    except Exception:
        pass  # lenient servers don't need it; strict ones would fail tools/list anyway
    res2 = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    if "error" in res2:
        raise RuntimeError(str(res2["error"].get("message", "rpc error"))[:120])
    return (res2.get("result") or {}).get("tools") or []


def measure_sync(name: str, cfg: dict, timeout: float) -> dict:
    row: dict = {"server": name}
    try:
        if cfg.get("type") == "http":
            tools = http_tools_sync(cfg, timeout)
        else:
            tools = stdio_tools_sync(cfg, timeout)
        payload = json.dumps(
            [{"name": t.get("name", ""), "description": t.get("description") or "",
              "inputSchema": t.get("inputSchema") or {}} for t in sorted(tools, key=lambda x: x.get("name", ""))],
            separators=(",", ":"), sort_keys=True).encode()
        n, approx = toks(payload)
        row.update({"tools": len(tools), "bytes": len(payload), "tokens": n,
                    "tokens_approx": approx})
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"[:160]
    return row


def mine_usage(server_names: list[str], sessions_dirs: list[Path]) -> dict[str, dict]:
    """Count actual MCP tool invocations per server across harness session logs.

    Matches `mcp__<server>_` / `mcp__<server>__` prefixes against known server
    names (omp routes MCP through xd:// writes, claude through mcp__ toolCalls —
    both contain the prefix as a substring)."""
    out = {n: {"calls": 0, "last_used": None} for n in server_names}
    # longest name first: `mcp__foo_bar_x` belongs to server foo_bar, not foo
    frags = {f"mcp__{n}_": n for n in sorted(server_names, key=len, reverse=True)}
    files: list[Path] = []
    for d in sessions_dirs:
        if d.exists():
            files.extend(d.rglob("*.jsonl"))
    for jf in files:
        try:
            fh = jf.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if "mcp__" not in line:
                    continue
                ts = None
                m = re.search(r'"timestamp":\s*"([^"]+)"', line)
                if m:
                    ts = m.group(1)[:10]
                hit = None
                for frag, name in frags.items():
                    if frag in line:
                        hit = name
                        break
                if hit:
                    out[hit]["calls"] += 1
                    if ts and (out[hit]["last_used"] is None or ts > out[hit]["last_used"]):
                        out[hit]["last_used"] = ts
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="hiviz MCP footprint + usage meter")
    ap.add_argument("--config", action="append", help="explicit mcp config path (repeatable)")
    ap.add_argument("--sessions", action="append", default=None,
                    help="session-log dir to mine for usage (repeatable; replaces defaults)")
    ap.add_argument("--out", default=".hiviz/mcp_footprint.json")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    registry, uniq = {}, []
    for label, path in discover_configs(args.config):
        try:
            servers = load_servers(label, path)
        except Exception as e:
            print(f"[{label}] config parse error: {e}", file=sys.stderr)
            continue
        for name, cfg in servers.items():
            registry.setdefault(name, []).append(label)
            if len(registry[name]) == 1:  # measure each unique server once
                uniq.append((name, cfg))
    with ThreadPoolExecutor() as ex:
        rows = list(ex.map(lambda nc: measure_sync(nc[0], nc[1], args.timeout), uniq))
    usage = mine_usage(sorted(registry),
                       [Path(p) for p in (args.sessions or
                                          [str(HOME / ".omp/agent/sessions")] +
                                          [str(p) for p in HOME.glob(".omp/profiles/*/agent/sessions")])])
    for r in rows:
        r["harnesses"] = ",".join(sorted(registry.get(r["server"], [])))
        u = usage.get(r["server"])
        if u:
            r["calls"] = u["calls"]
            r["last_used"] = u["last_used"]
    rows.sort(key=lambda r: -(r.get("bytes") or 0))

    print("| server | harnesses | tools | bytes | tokens | calls | last used |")
    print("|---|---|---:|---:|---:|---:|---|")
    ok = 0
    for r in rows:
        if "error" in r:
            print(f"| {r['server']} | {r['harnesses']} | ERR | {r['error']} | | | |", file=sys.stderr)
        else:
            mark = "~" if r["tokens_approx"] else ""
            lu = r.get("last_used") or "never"
            print(f"| {r['server']} | {r['harnesses']} | {r['tools']} | {r['bytes']:,} | "
                  f"{mark}{r['tokens']:,} | {r.get('calls', 0)} | {lu} |")
            ok += 1
    if rows:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows},
                                  indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(out)  # atomic
    print(f"\n{ok}/{len(rows)} servers measured · json: {args.out}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
