#!/usr/bin/env python3
"""Spec-strict fake Streamable-HTTP MCP server for hiviz T1 (MCP 2025-06-18).

Enforces what real servers enforce and naive clients get wrong: Accept must list
both application/json and text/event-stream, the session id travels in the
Mcp-Session-Id HTTP header (required after initialize), tools/list answers as an
SSE stream that stays open, and an optional bearer token is checked.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SESSION = "hv-session-1"


def start(tools: int = 2, token: str | None = None) -> tuple[ThreadingHTTPServer, str]:
    tool_list = [{"name": f"probe{i + 1}", "description": "http probe " * 20,
                  "inputSchema": {"type": "object"}} for i in range(tools)]

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _fail(self, code: int, text: str) -> None:
            body = text.encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            accept = self.headers.get("Accept", "")
            if "application/json" not in accept or "text/event-stream" not in accept:
                return self._fail(406, "Accept must list application/json and text/event-stream")
            if token and self.headers.get("Authorization") != f"Bearer {token}":
                return self._fail(401, "bad token")
            method = body.get("method")
            if method == "initialize":
                res = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {
                    "protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-http", "version": "0.1"}}}).encode()
                self.send_response(200)
                self.send_header("Mcp-Session-Id", SESSION)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(res)))
                self.end_headers()
                self.wfile.write(res)
                return
            if self.headers.get("Mcp-Session-Id") != SESSION:
                return self._fail(400, "missing Mcp-Session-Id header")
            if "id" not in body:  # notification
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if method != "tools/list":
                return self._fail(400, "unexpected method")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            msg = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"tools": tool_list}})
            self.wfile.write(f": keepalive\n\nevent: message\ndata: {msg}\n\n".encode())
            self.wfile.flush()
            time.sleep(5)  # keep the stream open: a client that reads to EOF times out
            self.close_connection = True

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/mcp"
