"""Naive API client — the starting point. Production-grade behavior is spec'd
in task.md; this file only shows the transport protocol shape."""
from typing import Any


class ApiClient:
    def __init__(self, transport: Any, *, timeout: int = 10):
        self._t = transport
        self._timeout = timeout

    def get(self, path: str, params: dict | None = None) -> dict:
        r = self._t.request("GET", path, params=params, timeout=self._timeout)
        if r.status >= 400:
            raise RuntimeError(f"HTTP {r.status}")
        return r.body

    def post(self, path: str, json: dict | None = None) -> dict:
        r = self._t.request("POST", path, json=json, timeout=self._timeout)
        if r.status >= 400:
            raise RuntimeError(f"HTTP {r.status}")
        return r.body

    def list_all(self, path: str, params: dict | None = None) -> list:
        r = self._t.request("GET", path, params=params, timeout=self._timeout)
        if r.status >= 400:
            raise RuntimeError(f"HTTP {r.status}")
        return list(r.body.get("items", []))
