#!/usr/bin/env python3
"""Verifier for tx-kv: 10 deterministic checks with a controlled clock
(patches store.time.time) and a seeded reference-model diff. Score 0-10;
exit 0 iff >= 8."""
import json
import os
import random
import sys

sys.path[:] = [p for p in sys.path if "site-packages" not in p.replace("\\", "/")]
sys.path.insert(0, os.getcwd())

if not os.path.isfile("store.py"):
    print("SCORE: 0/10 — store.py file missing in the working directory")
    sys.exit(1)

CLOCK = [1000.0]


def main() -> int:
    try:
        import store
        from store import Store, StoreError, MissingKey, TxConflict, TxDiscarded
    except Exception as e:
        print(f"SCORE: 0/10 — cannot import store contract: {e}")
        return 1

    store.time.time = lambda: CLOCK[0]

    score = 0
    fails = []

    def check(label, fn):
        nonlocal score
        try:
            fn()
            score += 1
        except Exception as e:
            fails.append(f"{label}: {type(e).__name__}: {e}")

    # 1. basic
    def t1():
        s = Store()
        s.set("b", 2); s.set("a", "x"); s.set("c", [1, "y"])
        assert s.get("b") == 2 and s.get("c") == [1, "y"]
        assert s.keys() == ["a", "b", "c"]
        s.delete("a")
        assert s.keys() == ["b", "c"]
        for bad in ({"d": 1}, 1.5, [1.25], [[1]], {1, 2}):
            try:
                s.set("bad", bad)
                raise AssertionError(f"no TypeError for {type(bad)}")
            except TypeError:
                pass
        try:
            s.get("zz")
            raise AssertionError("no MissingKey")
        except MissingKey as e:
            assert e.key == "zz"
    check("basic", t1)

    # 2. context manager
    def t2():
        s = Store()
        with s.begin() as tx:
            tx.set("k", 1)
        assert s.get("k") == 1
        closed = None
        try:
            with s.begin() as tx2:
                tx2.set("k", 99)
                closed = tx2
                raise ValueError("boom")
        except ValueError:
            pass
        assert s.get("k") == 1
        for call in (lambda: closed.set("x", 1), lambda: closed.get("k"),
                     lambda: closed.commit(), lambda: closed.rollback()):
            try:
                call()
                raise AssertionError("no TxDiscarded")
            except TxDiscarded:
                pass
    check("context manager", t2)

    # 3. ttl lazy expiry (patched clock)
    def t3():
        s = Store()
        s.set("t", "v", ttl=10)
        assert abs(s.ttl("t") - 10.0) < 1e-9
        CLOCK[0] += 4
        assert abs(s.ttl("t") - 6.0) < 1e-9
        CLOCK[0] += 6  # exactly at expiry -> dead
        for fn in (s.get, s.delete, s.ttl):
            try:
                fn("t")
                raise AssertionError("expired key alive")
            except MissingKey:
                pass
        assert s.keys() == [] and s.snapshot() == {}
        s.set("t", "v2", ttl=5)
        CLOCK[0] += 1
        s.set("t", "v3")  # clears ttl
        CLOCK[0] += 100
        assert s.get("t") == "v3"
    check("ttl lazy", t3)

    # 4. nested savepoints
    def t4():
        w = os.path.abspath("_wal4.jsonl")
        if os.path.exists(w):
            os.remove(w)
        s = Store(wal=w)
        s.set("base", 0)
        with s.begin() as outer:
            outer.set("x", 1)
            inner = outer.begin()
            inner.set("y", 2)
            inner.rollback()
            try:
                outer.get("y")
                raise AssertionError("inner write visible after rollback")
            except MissingKey:
                pass
            inner2 = outer.begin()
            inner2.set("z", 3)
            inner2.commit()
            outer.set("w", 4)
        assert (s.get("x"), s.get("z"), s.get("w")) == (1, 3, 4)
        assert "y" not in s.keys()
        lines = open(w, encoding="utf-8").read().splitlines()
        assert len(lines) == 2, f"wal lines={len(lines)}"  # direct set(base) + one tx line
        assert json.loads(lines[0])["txid"] == 1 and json.loads(lines[1])["txid"] == 2
        assert [o["op"] for o in json.loads(lines[1])["ops"]] == ["set", "set", "set"]
    check("nested savepoints", t4)

    # 5. isolation
    def t5():
        s = Store()
        s.set("shared", "store")
        t1_ = s.begin()
        t1_.set("shared", "tx1")
        t1_.set("only1", 1)
        t2_ = s.begin()
        assert s.get("shared") == "store"
        try:
            t2_.get("only1")
            raise AssertionError("cross-tx leak")
        except MissingKey:
            pass
        try:
            s.get("only1")
            raise AssertionError("uncommitted visible to store")
        except MissingKey:
            pass
        assert t1_.get("shared") == "tx1" and t2_.get("shared") == "store"
        t1_.commit()
        t2_.rollback()
    check("isolation", t5)

    # 6. conflict
    def t6():
        s = Store()
        s.set("k", "base")
        a = s.begin(); b = s.begin()
        a.set("k", 1); b.set("k", 2); b.set("other", 9)
        a.commit()
        try:
            b.commit()
            raise AssertionError("no TxConflict")
        except TxConflict as e:
            assert e.keys == ["k"], f"keys={e.keys}"
        try:
            b.set("k", 3)
            raise AssertionError("no TxDiscarded after conflict")
        except TxDiscarded:
            pass
        assert s.get("k") == 1 and s.keys() == ["k"]
    check("conflict", t6)

    # 7. WAL exact bytes
    def t7():
        w = os.path.abspath("_wal7.jsonl")
        if os.path.exists(w):
            os.remove(w)
        s = Store(wal=w)
        CLOCK[0] = 2000.0
        with s.begin() as tx:
            tx.set("a", 1, ttl=5)
            tx.set("b", ["x", 2])
            tx.delete("a")  # deleted in the same tx
        CLOCK[0] = 2001.0
        s.begin().commit()  # empty tx: no-op, no WAL line, no txid consumed
        lines = open(w, encoding="utf-8").read().splitlines()
        assert len(lines) == 1, f"lines={len(lines)}"
        exp1 = json.dumps({"txid": 1, "ops": [
            {"op": "set", "key": "a", "value": 1, "ttl": 2005.0},
            {"op": "set", "key": "b", "value": ["x", 2], "ttl": None},
            {"op": "delete", "key": "a"}]}, separators=(",", ":"))
        assert lines[0] == exp1, f"line1={lines[0]!r}\n  exp ={exp1!r}"
    check("wal bytes", t7)

    # 8. WAL replay
    def t8():
        w = os.path.abspath("_wal8.jsonl")
        if os.path.exists(w):
            os.remove(w)
        s = Store(wal=w)
        CLOCK[0] = 3000.0
        s.set("ttlkey", "v", ttl=100)
        s.set("plain", 7)
        s2 = Store(wal=w)
        assert s2.get("plain") == 7
        CLOCK[0] += 40
        assert abs(s2.ttl("ttlkey") - 60.0) < 1e-9
        CLOCK[0] += 61
        try:
            s2.get("ttlkey")
            raise AssertionError("replayed ttl not expired")
        except MissingKey:
            pass
    check("wal replay", t8)

    # 9. snapshot isolation
    def t9():
        s = Store()
        s.set("b", 1); s.set("a", 2)
        snap = s.snapshot()
        s.set("c", 3); s.delete("a")
        assert snap == {"a": 2, "b": 1}
        assert list(snap) == ["a", "b"]
        assert s.snapshot() == {"b": 1, "c": 3}
    check("snapshot", t9)

    # 10. seeded random diff vs reference model
    def t10():
        rng = random.Random(42)
        s = Store()
        ref: dict = {}
        ttl_ref: dict = {}
        now = 5000.0

        def live_ref():
            return {k: v for k, v in ref.items()
                    if k not in ttl_ref or now < ttl_ref[k]}

        for i in range(50):
            op = rng.randrange(6)
            if op == 0:
                k = f"k{rng.randrange(12)}"
                v = rng.choice(["s", 5, ["a", 1]])
                if rng.random() < 0.3:
                    ttl = rng.choice([1.0, 50.0, 500.0])
                    s.set(k, v, ttl=ttl)
                    ref[k] = v
                    ttl_ref[k] = now + ttl
                else:
                    s.set(k, v)
                    ref[k] = v
                    ttl_ref.pop(k, None)
            elif op == 1:
                k = f"k{rng.randrange(12)}"
                lv = live_ref()
                if k in lv:
                    s.delete(k)
                    del ref[k]
                    ttl_ref.pop(k, None)
                else:
                    try:
                        s.delete(k)
                        raise AssertionError(f"delete dead key {k} ok")
                    except MissingKey:
                        pass
            elif op == 2:
                now += rng.choice([0.0, 2.0, 60.0])
                CLOCK[0] = now
            elif op == 3:
                k = f"k{rng.randrange(12)}"
                lv = live_ref()
                if k in lv:
                    assert s.get(k) == lv[k], f"get {k}: {s.get(k)!r} != {lv[k]!r}"
                else:
                    try:
                        s.get(k)
                        raise AssertionError(f"get dead key {k} ok")
                    except MissingKey:
                        pass
            elif op == 4:
                assert s.keys() == sorted(live_ref()), f"keys diverged at op {i}"
            else:
                tx = s.begin()
                k = f"k{rng.randrange(12)}"
                tx.set(k, "tx")
                if rng.random() < 0.5:
                    tx.rollback()
                else:
                    ref[k] = "tx"
                    ttl_ref.pop(k, None)
                    tx.commit()
        CLOCK[0] = now
        got = s.snapshot()
        want = live_ref()
        assert got == want, f"final state diverged:\n got ={got}\n want={want}"
    check("random diff", t10)

    print(f"SCORE: {score}/10" + (f" — fails: {'; '.join(fails)}" if fails else " — all green"))
    return 0 if score >= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
