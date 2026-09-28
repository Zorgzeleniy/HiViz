Harden the naive API client in `client.py` (current directory) to the production contract below. A behavioral verifier injects a scripted fake transport and scores 10 scenarios 0–10; exit ≥ 8 passes.

## Transport protocol (duck-typed, injected — do NOT import or name specific transport classes)

```python
transport.request(method: str, path: str, *, params: dict | None = None,
                  json: dict | None = None, headers: dict | None = None,
                  timeout: int | None = None) -> Response
```

`Response` carries `.status: int`, `.headers: dict` (lowercase keys), `.body: dict | None` (parsed JSON).
A failing transport raises an exception whose class NAME is `"TransportTimeout"` or `"ConnectionDropped"`
(catch broadly, then branch on `type(e).__name__`; anything else must propagate untouched).
No network. Stdlib only. Single file: `client.py`.

## Client contract

```python
from client import ApiClient, ApiError, AuthError, RateLimitError, ServerError, ClientTimeoutError

c = ApiClient(transport, *, timeout=10, max_attempts=3, backoff_base=0.05)
c.get(path, params=None) -> dict          # thin wrapper over the request flow
c.post(path, json=None) -> dict
c.list_all(path, params=None) -> list     # cursor pagination
```

Exceptions (all defined in `client.py`): `ApiError(Exception)` with `.status`, `.code`, `.message`;
`AuthError(ApiError)`; `RateLimitError(ApiError)` with `.retry_after: int`;
`ServerError(ApiError)`; `ClientTimeoutError(ApiError)`.

### Request flow (one `_request(method, path, ...)` path used by get/post/list_all)

1. Attempt `max_attempts` times total. Pass `timeout=self._timeout` to EVERY transport call.
2. Response handling:
   - 2xx → return `.body`.
   - 429 → raise `RateLimitError` IMMEDIATELY (no retry). `.retry_after` = int of
     `headers["retry-after"]` if present and numeric, else 0.
   - 401/403 → raise `AuthError` immediately (no retry).
   - other 4xx → raise `ApiError` immediately (no retry), error info parsed (below).
   - 5xx → retry if attempts remain, else raise `ServerError`.
3. `TransportTimeout` / `ConnectionDropped` from the transport → retry if attempts remain,
   else `ClientTimeoutError` (timeout) / `ServerError` with `.status = 0`, `.code = "connection_dropped"`.
4. Backoff: before EVERY retry call `time.sleep(backoff_base * 2 ** (attempt - 1))`
   where `attempt` is the 1-based attempt that just failed (0.05, then 0.1, ...).
   `import time` at module top and call `time.sleep(...)` exactly like that.
5. Error info for raised HTTP errors: if `.body` is `{"error": {"code": <c>, "message": <m>}}`,
   set `.code = c`, `.message = m`; otherwise `.code = None`, `.message = None`.

### Pagination (`list_all`)

GET `path` with `params`. Body: `{"items": [...], "next": <cursor-or-null>}`. While `next` is truthy,
GET again with `params["cursor"] = next` (each request goes through the full retry flow).
Return the concatenated `items` lists in order (missing `items` → `[]`).

## Ground rules (scoring)

Work agentic or score zero: `client.py` must exist as a FILE created/edited by tool calls when the
verifier runs. Narrating a solution without the file scores 0. No reading or importing verifier files;
the fake transport is injected — hardcoding to any concrete transport class name fails.

## Checks (10 scenarios, exact)

1. [503, 503, 200] → body returned; 3 transport calls; sleeps `[0.05, 0.1]`.
2. [503, 503, 503] → `ServerError` `.status == 503`; 3 calls; 2 sleeps.
3. [429, headers {"retry-after": "7"}] → `RateLimitError` `.retry_after == 7`; 1 call; 0 sleeps.
4. [401] → `AuthError` `.status == 401`; 1 call; 0 sleeps.
5. [TransportTimeout, 200] → body returned; 2 calls; 1 sleep `[0.05]`.
6. [TransportTimeout ×3] → `ClientTimeoutError`; 3 calls.
7. [400, body {"error": {"code": "bad_thing", "message": "hi"}}] → exactly `ApiError` type
   (not a subclass), `.code == "bad_thing"`, `.message == "hi"`, `.status == 400`.
8. list_all pages `{items:[1,2], next:"a"}` → `{items:[3], next:"b"}` → `{items:[4,5], next:null}`
   → `[1,2,3,4,5]`; second call has `params["cursor"] == "a"`, third `"b"`.
9. Default `timeout=10` reaches the transport on every call; `ApiClient(t, timeout=3)` → `timeout=3`.
10. [ConnectionDropped, ConnectionDropped, 200] → body returned; 3 calls; 2 sleeps.
