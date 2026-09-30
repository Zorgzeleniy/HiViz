#!/usr/bin/env python3
"""hiviz meter: live MCP context footprint + usage telemetry.

For every MCP server in the discovered harness configs (Claude Code, Codex, omp,
Cursor, Windsurf, OpenCode — pi has no MCP by design):
  - measures the standing context payload (initialize + tools/list →
    names + descriptions + inputSchemas) — what EVERY session pays;
  - mines harness session logs (omp, Claude Code, Codex) for actual invocations,
    so "weight" and "usage" sit in one row: pay-vs-use. calls=null means usage is
    unknown (no minable logs for the harnesses that load the server), not zero.

Metrics kept (essential only): tools · bytes (weight) · tokens (cl100k when
available, else bytes/4 marked ~) · calls · last_used.

Never writes configs. Expands ${VAR} header values at runtime, never prints them.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
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
               "clientInfo": {"name": "hiviz-meter", "version": "0.7.1"}}
MAX_PAGES = 20


def _env_dir(var: str, default: Path) -> Path:
    v = os.environ.get(var, "").strip()
    return Path(v).expanduser() if v else default


CLAUDE_DIR = _env_dir("CLAUDE_CONFIG_DIR", HOME / ".claude")
CODEX_DIR = _env_dir("CODEX_HOME", HOME / ".codex")
XDG_CONFIG = _env_dir("XDG_CONFIG_HOME", HOME / ".config")


def loads_jsonc(text: str):
    """json.loads that tolerates // and /* */ comments and trailing commas (opencode.jsonc)."""
    def scan(src: str, on_char) -> str:
        out, i, n, in_str = [], 0, len(src), False
        while i < n:
            ch = src[i]
            if in_str:
                out.append(ch)
                if ch == "\\" and i + 1 < n:
                    out.append(src[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    in_str = False
                i += 1
                continue
            if ch == '"':
                in_str = True
                out.append(ch)
                i += 1
                continue
            i = on_char(src, i, out)
        return "".join(out)

    def strip_comments(src, i, out):
        if src.startswith("//", i):
            j = src.find("\n", i)
            return len(src) if j < 0 else j
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            return len(src) if j < 0 else j + 2
        out.append(src[i])
        return i + 1

    def strip_trailing_commas(src, i, out):
        if src[i] == ",":
            j = i + 1
            while j < len(src) and src[j] in " \t\r\n":
                j += 1
            if j < len(src) and src[j] in "}]":
                return i + 1
        out.append(src[i])
        return i + 1

    return json.loads(scan(scan(text, strip_comments), strip_trailing_commas))


def discover_configs(explicit: list[str] | None) -> list[tuple[str, Path]]:
    if explicit:
        return [("explicit", Path(p)) for p in explicit]
    cwd = Path.cwd()
    claude_json = (CLAUDE_DIR / ".claude.json") if os.environ.get("CLAUDE_CONFIG_DIR") else HOME / ".claude.json"
    candidates = [
        ("omp/default", HOME / ".omp/agent/mcp.json"),
        ("claude/global", claude_json),
        ("claude/project", cwd / ".mcp.json"),
        ("codex/global", CODEX_DIR / "config.toml"),
        ("codex/project", cwd / ".codex/config.toml"),
        ("cursor/global", HOME / ".cursor/mcp.json"),
        ("cursor/project", cwd / ".cursor/mcp.json"),
        ("windsurf/global", HOME / ".codeium/windsurf/mcp_config.json"),
        ("opencode/global", XDG_CONFIG / "opencode/opencode.json"),
        ("opencode/global", XDG_CONFIG / "opencode/opencode.jsonc"),
        ("opencode/project", cwd / "opencode.json"),
        ("opencode/project", cwd / "opencode.jsonc"),
        # pi has no MCP support by design — nothing to measure there.
    ]
    for p in sorted(HOME.glob(".omp/profiles/*/agent/mcp.json")):
        candidates.append((f"omp/{p.parts[-3]}", p))
    seen, found = set(), []
    for label, p in candidates:
        if p.exists() and p.resolve() not in seen:
            seen.add(p.resolve())
            found.append((label, p))
    return found


def _same_dir(a: str, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except OSError:
        return False


def normalize(c: dict) -> dict:
    """One server shape for every harness: {type: stdio|http|sse, command, args, env, url, headers}."""
    c = dict(c)
    if isinstance(c.get("command"), list):  # opencode local: command = [bin, *args]
        cmd = [str(x) for x in c["command"]]
        c["command"], c["args"] = (cmd[0] if cmd else ""), [*cmd[1:], *(c.get("args") or [])]
    if "environment" in c and "env" not in c:  # opencode
        c["env"] = c["environment"]
    url = c.get("url") or c.get("serverUrl") or c.get("httpUrl")  # windsurf: serverUrl
    t = str(c.get("type") or c.get("transport") or "").lower()
    if t == "sse":
        kind = "sse"
    elif t in ("http", "streamable-http", "streamablehttp", "remote") or (url and not c.get("command")):
        kind = "http"
    else:
        kind = "stdio"
    c["type"] = kind
    if url:
        c["url"] = url
    return c


def _disabled(c: dict) -> bool:
    return c.get("disabled") is True or c.get("enabled") is False


def load_servers(label: str, path: Path) -> dict[str, dict]:
    if path.suffix == ".toml":
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        out = {}
        for n, c in (data.get("mcp_servers") or {}).items():
            hdrs = dict(c.get("http_headers") or {})
            for h, var in (c.get("env_http_headers") or {}).items():
                hdrs[h] = "${%s}" % var
            if c.get("bearer_token_env_var"):
                hdrs["Authorization"] = "Bearer ${%s}" % c["bearer_token_env_var"]
            out[n] = {**c, "headers": hdrs}
    else:
        data = loads_jsonc(path.read_text(encoding="utf-8"))
        out = dict(data.get("mcpServers") or data.get("mcp_servers") or data.get("mcp") or {})
        if label.startswith("claude/"):  # local-scope servers of the current project
            for proj, pc in (data.get("projects") or {}).items():
                if isinstance(pc, dict) and _same_dir(proj, Path.cwd()):
                    out.update(pc.get("mcpServers") or {})
    return {n: normalize(c) for n, c in out.items() if isinstance(c, dict) and not _disabled(c)}


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
    env = {**os.environ, **{k: str(v) for k, v in (cfg.get("env") or {}).items()}}
    cmd, args = cfg.get("command", ""), [str(a) for a in (cfg.get("args") or [])]
    if not cmd:
        raise RuntimeError("no command configured")
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
        tools, cursor = [], None
        for page in range(MAX_PAGES):
            _send(p.stdin, {"jsonrpc": "2.0", "id": 2 + page, "method": "tools/list",
                            **({"params": {"cursor": cursor}} if cursor else {})})
            res = _read_result(p.stdout, 2 + page)
            tools += res.get("tools") or []
            cursor = res.get("nextCursor")
            if not cursor:
                break
        return tools
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


def _rpc_from_sse(resp, want_id: int) -> dict | None:
    """Read SSE events until the response for want_id arrives (servers may keep the stream open)."""
    data: list[str] = []
    for raw in resp:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
            continue
        if line or not data:
            continue
        try:
            msg = json.loads("\n".join(data))
        except json.JSONDecodeError:
            msg = None
        data = []
        for m in (msg if isinstance(msg, list) else [msg]):
            if isinstance(m, dict) and m.get("id") == want_id:
                return m
    return None


def http_tools_sync(cfg: dict, timeout: float) -> list:
    """Streamable HTTP transport (MCP 2025-03-26+): JSON or SSE responses, Mcp-Session-Id header."""
    url = cfg.get("url", "")
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    for k, raw in (cfg.get("headers") or {}).items():
        val = str(raw)
        if "${" in val:
            val = os.path.expandvars(val)
            if "${" in val:
                raise RuntimeError(f"env var not set for header '{k}'")
        headers[k] = val

    def post(payload: dict) -> dict | None:
        r = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                headers["Mcp-Session-Id"] = sid
            if "id" not in payload:
                return None
            if "text/event-stream" in (resp.headers.get("Content-Type") or ""):
                msg = _rpc_from_sse(resp, payload["id"])
            else:
                body = json.loads(resp.read().decode("utf-8", "replace") or "null")
                msg = next((m for m in (body if isinstance(body, list) else [body])
                            if isinstance(m, dict) and m.get("id") == payload["id"]), None)
        if msg is None:
            raise RuntimeError(f"no JSON-RPC response for id {payload['id']}")
        if "error" in msg:
            raise RuntimeError(str(msg["error"].get("message", "rpc error"))[:120])
        return msg.get("result") or {}

    init = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT_PARAMS})
    headers["MCP-Protocol-Version"] = init.get("protocolVersion") or INIT_PARAMS["protocolVersion"]
    try:
        post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    except urllib.error.HTTPError:
        pass  # some servers reject notifications they do not need; tools/list still works
    tools, cursor = [], None
    for page in range(MAX_PAGES):
        res = post({"jsonrpc": "2.0", "id": 2 + page, "method": "tools/list",
                    **({"params": {"cursor": cursor}} if cursor else {})})
        tools += res.get("tools") or []
        cursor = res.get("nextCursor")
        if not cursor:
            break
    return tools


def measure_sync(name: str, cfg: dict, timeout: float) -> dict:
    row: dict = {"server": name}
    try:
        if cfg.get("type") == "http":
            tools = http_tools_sync(cfg, timeout)
        elif cfg.get("type") == "sse":
            raise RuntimeError("legacy HTTP+SSE transport is not measured (use streamable HTTP)")
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


def session_sources(explicit: list[str] | None) -> dict[str, list[Path]]:
    """Session-log dirs per harness family. Cursor/Windsurf/OpenCode keep no JSONL logs we can mine."""
    if explicit:
        return {"*": [Path(p) for p in explicit]}
    return {
        "omp": [HOME / ".omp/agent/sessions", *sorted(HOME.glob(".omp/profiles/*/agent/sessions"))],
        "claude": [CLAUDE_DIR / "projects"],
        "codex": [CODEX_DIR / "sessions", CODEX_DIR / "archived_sessions"],
    }


def _mcp_refs(d: dict) -> tuple[list[str], list[str]]:
    """(tool names/paths that may carry an mcp__<server>_ prefix, servers of Codex mcp_tool_call_end events)."""
    refs, servers = [], []
    msg = d.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    for it in content if isinstance(content, list) else []:
        if isinstance(it, dict) and it.get("type") in ("toolCall", "tool_use"):  # omp/pi · Claude Code
            refs.append(str(it.get("name", "")))
            args = it.get("arguments") or it.get("input")
            if isinstance(args, dict) and isinstance(args.get("path"), str):  # omp xd:// writes
                refs.append(args["path"])
    p = d.get("payload")
    if isinstance(p, dict):
        if p.get("type") in ("function_call", "custom_tool_call"):  # Codex (older rollouts)
            refs.append(str(p.get("name", "")))
        elif p.get("type") == "mcp_tool_call_end":  # Codex (current rollouts)
            servers.append(str((p.get("invocation") or {}).get("server", "")))
    return refs, servers


def mine_usage(server_names: list[str], sources: dict[str, list[Path]]) -> tuple[dict[str, dict], set[str]]:
    """Count MCP tool invocations per server across harness session logs.

    Returns (usage, families that had at least one log file). Structural match only
    (tool-call entries), so tool listings or prose mentioning mcp__ never count.
    Codex files with mcp_tool_call_end events count those only — the matching
    function_call items would double-count."""
    out = {n: {"calls": 0, "last_used": None} for n in server_names}
    by_len = sorted(server_names, key=len, reverse=True)  # "a_b" must win over "a"
    mined: set[str] = set()

    def bump(name: str, ts: str | None, acc: dict) -> None:
        c = acc.setdefault(name, [0, None])
        c[0] += 1
        if ts and (c[1] is None or ts > c[1]):
            c[1] = ts

    for family, dirs in sources.items():
        for d in dirs:
            if not d.exists():
                continue
            for jf in d.rglob("*.jsonl"):
                mined.add(family)
                by_ref: dict = {}
                by_event: dict = {}
                try:
                    fh = jf.open(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                with fh:
                    for line in fh:
                        if "mcp" not in line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(entry, dict):
                            continue
                        ts = entry.get("timestamp")
                        ts = ts[:10] if isinstance(ts, str) else None
                        refs, servers = _mcp_refs(entry)
                        for srv in servers:
                            if srv in out:
                                bump(srv, ts, by_event)
                        for ref in refs:
                            hit = next((n for n in by_len if f"mcp__{n}_" in ref), None)
                            if hit:
                                bump(hit, ts, by_ref)
                                break
                for name, (calls, lu) in (by_event or by_ref).items():
                    out[name]["calls"] += calls
                    if lu and (out[name]["last_used"] is None or lu > out[name]["last_used"]):
                        out[name]["last_used"] = lu
    return out, mined


def main() -> int:
    ap = argparse.ArgumentParser(description="hiviz MCP footprint + usage meter")
    ap.add_argument("--config", action="append", help="explicit mcp config path (repeatable)")
    ap.add_argument("--sessions", action="append", default=None,
                    help="session-log dir to mine for usage (repeatable; replaces the omp/Claude/Codex defaults)")
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
    sources = session_sources(args.sessions)
    usage, mined = mine_usage(sorted(registry), sources)
    for r in rows:
        labels = registry.get(r["server"], [])
        r["harnesses"] = ",".join(sorted(labels))
        # usage is only known when logs of a harness that loads this server were mined;
        # otherwise calls=None (unknown), never a misleading 0
        known = bool(mined) if ("*" in sources or "explicit" in labels) else \
            any(lbl.split("/")[0] in mined for lbl in labels)
        u = usage.get(r["server"])
        r["calls"] = u["calls"] if (known and u) else None
        r["last_used"] = u["last_used"] if (known and u) else None
    rows.sort(key=lambda r: -(r.get("bytes") or 0))

    print("| server | harnesses | tools | bytes | tokens | calls | last used |")
    print("|---|---|---:|---:|---:|---:|---|")
    ok = 0
    for r in rows:
        if "error" in r:
            print(f"| {r['server']} | {r['harnesses']} | ERR | {r['error']} | | | |", file=sys.stderr)
        else:
            mark = "~" if r["tokens_approx"] else ""
            unknown = r.get("calls") is None
            lu = "?" if unknown else (r.get("last_used") or "never")
            calls = "?" if unknown else r["calls"]
            print(f"| {r['server']} | {r['harnesses']} | {r['tools']} | {r['bytes']:,} | "
                  f"{mark}{r['tokens']:,} | {calls} | {lu} |")
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
