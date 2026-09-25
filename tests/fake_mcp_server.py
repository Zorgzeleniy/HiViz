#!/usr/bin/env python3
"""Fake MCP stdio server for hiviz tests: N tools with generated descriptions.

Usage: fake_mcp_server.py --tools 3 --desc-bytes 600 --delay-ms 200
Deterministic, offline, newline-delimited JSON-RPC (no initialized notification required).
"""
import argparse
import json
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--tools", type=int, default=3)
ap.add_argument("--desc-bytes", type=int, default=600)
ap.add_argument("--delay-ms", type=int, default=0)
a = ap.parse_args()

WORDS = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod "
         "tempor incididunt ut labore et dolore magna aliqua ").split()


def desc(n: int) -> str:
    out, i = [], 0
    while sum(len(w) + 1 for w in out) < n:
        out.append(WORDS[i % len(WORDS)])
        i += 1
    return " ".join(out)[:n]

TOOLS = [{"name": f"probe{i+1}",
          "description": desc(a.desc_bytes),
          "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}}
         for i in range(a.tools)]

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        time.sleep(a.delay_ms / 1000.0)
        resp = {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake", "version": "0.1"}}}
    elif method == "tools/list":
        resp = {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    else:
        if mid is None:
            continue  # notification — ignore
        resp = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown method"}}
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()
