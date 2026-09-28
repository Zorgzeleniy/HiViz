Implement a transactional in-memory KV store in `store.py` (current directory) to the exact contract below. The verifier injects a controlled clock (patches `store.time.time`) and replays a seeded random op script against a reference model. 10 checks, score 0–10; exit ≥ 8 passes.

## Values, exceptions

- Values: `str | int | list[str | int]` (heterogeneous lists allowed). Anything else → `TypeError` at call time.
- Exceptions in `store.py`: `StoreError(Exception)`; `MissingKey(StoreError)` with `.key`;
  `TxConflict(StoreError)` with `.keys` (sorted list); `TxDiscarded(StoreError)`.
- `import time` at module top; "now" is ALWAYS `time.time()`.

## Store (top level)

```python
s = Store()                      # empty, no WAL
s = Store(wal="path.jsonl")      # opens/replays the WAL, then APPENDS new commits
s.set(key, value, *, ttl: float | None = None)
s.get(key) -> value              # MissingKey if absent or expired
s.delete(key)                    # MissingKey if absent or expired
s.keys() -> sorted list[str]     # live (non-expired) keys
s.ttl(key) -> float              # remaining seconds; MissingKey if absent/expired
s.snapshot() -> dict             # plain copy of live keys->values (no ttl info)
s.begin() -> Tx                  # top-level transaction
```

TTL: `set(k, v, ttl=t)` expires at `set-time + t`. Expiry is LAZY: a key is dead when
`time.time() >= expiry`; dead keys behave as missing for get/delete/keys/ttl/snapshot/tx-reads.
`set` without `ttl` on a key that had one clears the ttl.

## Transactions

```python
tx = s.begin()
tx.set(key, value, *, ttl=None); tx.get(key); tx.delete(key)   # operate on the TX view
tx.begin()   -> Tx      # nested savepoint
tx.commit()  -> None    # nested: merge into parent; top-level: WAL-append then apply
tx.rollback() -> None   # nested: restore savepoint; top-level: discard everything
```

- Isolation: uncommitted writes are invisible to `s.*` and to other transactions. A tx sees
  its own writes plus the store state as of its `begin` (later outer commits are NOT visible).
- Context manager: `with s.begin() as tx:` commits on clean exit, rolls back on exception.
- `delete` inside tx: raises `MissingKey` (at call time, tx stays usable) if the key is not
  live in the tx view.
- After any successful top-level `commit` or a `rollback`, the Tx is CLOSED: any further
  method call → `TxDiscarded`.

### WAL (top-level commits AND direct store mutations)

- File is JSON Lines, appended in order. Sources of lines:
  a committed top-level tx that produced at least one op (set/delete) — one line with
  all its ops merged (an empty top-level tx commits as a no-op: no line, no txid consumed);
  and every DIRECT store-level `set`/`delete` — one single-op line each, same format.
- A direct store-level mutation counts as a commit for conflict detection (its key set
  is visible to the "committed after T began" rule).
- Line = `json.dumps({"txid": n, "ops": [...]}, separators=(",", ":"))` — exact bytes, no spaces.
- `txid` starts at 1, increments per line.
- Ops in commit order, merged from the whole nested tree:
  `{"op":"set","key":k,"value":v,"ttl":<ABSOLUTE expiry float or null>}` for set
  (absolute expiry = the `time.time()` moment the key would die),
  `{"op":"delete","key":k}` for delete.
- `Store(wal=p)` replays lines in order before serving; remaining ttl = expiry − now.
- WAL writes must be flushed before the commit returns (visible to an immediate re-open).

### Conflict detection

Each Tx tracks the set of keys it wrote (set/delete). On TOP-LEVEL `commit` of tx T:
if any of T's written keys was committed to the store AFTER T began (by another top-level
commit), raise `TxConflict` with `.keys` = sorted intersection, and T becomes CLOSED
(discarded). Nested commits merge writes into the parent without a conflict check.

## Ground rules (scoring)

Work agentic or score zero: `store.py` must exist as a FILE when the verifier runs;
narrating without the file scores 0. Stdlib only, no network, single file `store.py`.

## Checks (10 scenarios, exact)

1. Basic: set/get/delete/keys sorted, MissingKey on get/delete of absent, TypeError on `dict` value.
2. Context manager: clean exit commits, exception exit rolls back (store unchanged, tx closed).
3. TTL lazy expiry with patched clock: `ttl(k)` remaining, expiry boundary `now >= expiry` is dead,
   re-`set` without ttl clears it.
4. Nested savepoint: inner rollback restores inner writes; inner commit merges; outer commit persists; one WAL line total.
5. Isolation: tx writes invisible to `s.*` and a second tx; tx sees own writes.
6. Conflict: t1, t2 write same key; t1.commit ok; t2.commit → `TxConflict.keys == [k]`; t2 then closed (`TxDiscarded`).
7. WAL bytes: exact compact JSON per line — set ops always carry `"ttl"` (float or null);
   direct store-level set/delete produce their own single-op lines.
8. WAL replay: fresh `Store(wal=same)` sees all data and correct remaining ttl under the patched clock.
9. Snapshot isolation: snapshot frozen at call time; later set/delete don't affect it; snapshot keys sorted.
10. Seeded random op script (50 ops, mixed store-level + sequential txs incl. ttl and rollback)
    replayed against the verifier's reference model: final live state (keys→values) identical.
