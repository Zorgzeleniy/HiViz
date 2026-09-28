#!/usr/bin/env python3
"""Verifier for harden-client: 10 behavioral scenarios with an injected fake
transport. Deterministic, no network, no LLM. Sleeps are intercepted by
patching client.time.sleep. Score 0-10; exit 0 iff >= 8."""
import os
import sys

sys.path[:] = [p for p in sys.path if "site-packages" not in p.replace("\\", "/")]
sys.path.insert(0, os.getcwd())

if not os.path.isfile("client.py"):
    print("SCORE: 0/10 — client.py file missing in the working directory")
    sys.exit(1)


class TransportTimeout(Exception):
    pass


class ConnectionDropped(Exception):
    pass


class Resp:
    def __init__(self, status, headers=None, body=None):
        self.status = status
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.body = body


class Scripted:
    """Fake transport: replays scripted outcomes (Resp or exception instances)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None, timeout=None):
        self.calls.append({"method": method, "path": path, "params": dict(params or {}),
                           "json": json, "timeout": timeout})
        out = self.script.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def main() -> int:
    try:
        import client
        from client import (ApiClient, ApiError, AuthError, RateLimitError, ServerError,
                            ClientTimeoutError)
    except Exception as e:
        print(f"SCORE: 0/10 — cannot import client contract: {e}")
        return 1

    sleeps = []
    if hasattr(client, "time"):
        client.time.sleep = lambda s: sleeps.append(s)

    def fresh(script):
        return Scripted(script)

    def approx(a, b, tol=1e-9):
        return len(a) == len(b) and all(abs(x - y) < tol for x, y in zip(a, b))

    score = 0
    fails = []

    def check(label, fn):
        nonlocal score
        try:
            fn()
            score += 1
        except Exception as e:
            fails.append(f"{label}: {type(e).__name__}: {e}")

    # 1. 503,503,200 -> body; 3 calls; sleeps 0.05,0.1
    def t1():
        t = fresh([Resp(503), Resp(503), Resp(200, body={"ok": 1})])
        assert ApiClient(t).get("/x") == {"ok": 1}
        assert len(t.calls) == 3, f"calls={len(t.calls)}"
        assert approx(sleeps, [0.05, 0.1]), f"sleeps={sleeps}"
    check("retry 5xx then 200", t1)

    # 2. 503x3 -> ServerError 503; 3 calls; 2 sleeps
    def t2():
        del sleeps[:]
        t = fresh([Resp(503)] * 3)
        try:
            ApiClient(t).get("/x")
            raise AssertionError("no ServerError")
        except ServerError as e:
            assert e.status == 503, f"status={e.status}"
        assert len(t.calls) == 3 and len(sleeps) == 2, f"calls={len(t.calls)} sleeps={sleeps}"
    check("5xx exhausted", t2)

    # 3. 429 + retry-after -> RateLimitError.retry_after 7; no retry
    def t3():
        del sleeps[:]
        t = fresh([Resp(429, headers={"Retry-After": "7"})])
        try:
            ApiClient(t).get("/x")
            raise AssertionError("no RateLimitError")
        except RateLimitError as e:
            assert e.retry_after == 7, f"retry_after={e.retry_after}"
        assert len(t.calls) == 1 and not sleeps
    check("rate limit immediate", t3)

    # 4. 401 -> AuthError; no retry
    def t4():
        del sleeps[:]
        t = fresh([Resp(401)])
        try:
            ApiClient(t).get("/x")
            raise AssertionError("no AuthError")
        except AuthError as e:
            assert e.status == 401
        assert len(t.calls) == 1 and not sleeps
    check("auth immediate", t4)

    # 5. TransportTimeout then 200
    def t5():
        del sleeps[:]
        t = fresh([TransportTimeout(), Resp(200, body={"ok": 2})])
        assert ApiClient(t).get("/x") == {"ok": 2}
        assert len(t.calls) == 2 and approx(sleeps, [0.05])
    check("timeout retry", t5)

    # 6. TransportTimeout x3 -> ClientTimeoutError
    def t6():
        del sleeps[:]
        t = fresh([TransportTimeout()] * 3)
        try:
            ApiClient(t).get("/x")
            raise AssertionError("no ClientTimeoutError")
        except ClientTimeoutError:
            pass
        assert len(t.calls) == 3
    check("timeout exhausted", t6)

    # 7. 400 error body -> exact ApiError with parsed info
    def t7():
        t = fresh([Resp(400, body={"error": {"code": "bad_thing", "message": "hi"}})])
        try:
            ApiClient(t).get("/x")
            raise AssertionError("no ApiError")
        except ApiError as e:
            assert type(e) is ApiError, f"got subclass {type(e).__name__}"
            assert e.code == "bad_thing" and e.message == "hi" and e.status == 400
    check("error body parse", t7)

    # 8. list_all pagination cursors
    def t8():
        t = fresh([Resp(200, body={"items": [1, 2], "next": "a"}),
                   Resp(200, body={"items": [3], "next": "b"}),
                   Resp(200, body={"items": [4, 5], "next": None})])
        assert ApiClient(t).list_all("/things") == [1, 2, 3, 4, 5]
        assert t.calls[1]["params"]["cursor"] == "a" and t.calls[2]["params"]["cursor"] == "b"
    check("cursor pagination", t8)

    # 9. timeout passthrough (default 10, custom 3)
    def t9():
        t = fresh([Resp(200, body={})])
        ApiClient(t).get("/x")
        assert t.calls[0]["timeout"] == 10, f"timeout={t.calls[0]['timeout']}"
        t2_ = fresh([Resp(200, body={})])
        ApiClient(t2_, timeout=3).get("/x")
        assert t2_.calls[0]["timeout"] == 3
    check("timeout passthrough", t9)

    # 10. ConnectionDropped x2 then 200 -> success
    def t10():
        del sleeps[:]
        t = fresh([ConnectionDropped(), ConnectionDropped(), Resp(200, body={"ok": 3})])
        assert ApiClient(t).get("/x") == {"ok": 3}
        assert len(t.calls) == 3 and approx(sleeps, [0.05, 0.1])
    check("dropped retry", t10)

    print(f"SCORE: {score}/10" + (f" — fails: {'; '.join(fails)}" if fails else " — all green"))
    return 0 if score >= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
