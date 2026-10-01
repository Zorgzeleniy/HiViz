Implement a PyJWT-compatible JWT library subset in `jwt.py` (current directory). This is a real-project task: your module must pass a verifier ported from the actual pyjwt 2.10.1 test suite (github.com/jpadilla/pyjwt, MIT).

## API contract (match PyJWT 2.x exactly)

```python
import jwt

token: str = jwt.encode(payload: dict, key: str|bytes, algorithm: str = "HS256")
claims: dict = jwt.decode(token, key, algorithms: list[str] | None = None,
                          audience: str | None = None, issuer: str | None = None,
                          leeway: int = 0)
```

Exceptions, importable from the module: `InvalidTokenError` (base), `DecodeError`,
`InvalidSignatureError`, `ExpiredSignatureError`, `ImmatureSignatureError`,
`InvalidAudienceError`, `InvalidIssuerError`, `InvalidAlgorithmError`,
`InvalidIssuedAtError`, `MissingRequiredClaimError`, plus `TypeError`/`ValueError`
for bad payload types.

## Behavior (from the real suite)

- HS256 only: base64url (no padding) header/payload/signature; HMAC-SHA256;
  constant-time comparison. Header must carry `alg`; `typ` optional.
- `decode` verifies signature first, then registered claims when present:
  `exp` (expired → `ExpiredSignatureError`, `leeway` in seconds widens the window),
  `nbf` (future → `ImmatureSignatureError`), `iat` (future → `InvalidIssuedAtError`;
  non-int → `InvalidIssuedAtError`),
  `aud` (mismatch → `InvalidAudienceError`; `audience=None` means "don't check",
  a token WITH aud claim and no audience param → `InvalidAudienceError`),
  `iss` (mismatch → `InvalidIssuerError`).
- `algorithms` is required on decode in the sense that a token whose header `alg`
  is not in the list → `InvalidAlgorithmError` (this includes `alg: none` and
  cross-algorithm confusion).
- Malformed token (wrong segment count, bad base64url, non-mapping JSON payload)
  → `DecodeError`. `encode` with a non-mapping payload → `TypeError`.
- `decode` accepts `str` or `bytes` tokens.

No external dependencies (stdlib only). No network. One file: `jwt.py`.

## Ground rules (scoring)

Work agentic or score zero: the artifacts (`jwt.py` / fixes in `jwt/`) must exist as FILES created by tool calls when the verifier runs. Narrating a solution, planning out loud, or answering in prose without creating the files scores 0. Start by acting.
