#!/usr/bin/env python3
"""Verifier: 10 checks ported from pyjwt 2.10.1's real test suite
(tests/test_api_jwt.py, tests/test_api_jws.py — github.com/jpadilla/pyjwt, MIT).
Score 0-10; exit 0 iff >= 8. Imports ONLY a jwt.py file in the current dir —
site-packages are removed from sys.path so an installed PyJWT cannot satisfy the task."""
import os
import sys

sys.path[:] = [p for p in sys.path if "site-packages" not in p.replace("\\", "/")]
sys.path.insert(0, os.getcwd())

if not os.path.isfile("jwt.py"):
    print("SCORE: 0/10 — jwt.py file missing in the working directory")
    sys.exit(1)


def main() -> int:
    score = 0
    fails = []

    try:
        import jwt
    except Exception as e:
        print(f"SCORE: 0/10 — cannot import jwt: {e}")
        return 1
    def check(label, fn):
        nonlocal score
        try:
            fn()
            score += 1
        except Exception as e:
            fails.append(f"{label}: {type(e).__name__}: {e}")

    # 1. (real: test_decodes_valid_jwt) canonical interop token, decoded with the suite's bytes
    example_jwt = ("eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9"
                   ".eyJoZWxsbyI6ICJ3b3JsZCJ9"
                   ".tvagLDLoaiJKxOKqpBXSEGy7SYSifZhjntgm9ctpyj8")
    def t1():
        assert jwt.decode(example_jwt, "secret", algorithms=["HS256"]) == {"hello": "world"}
    check("interop decode", t1)

    # 2. (real: payload fixture + roundtrip) encode -> decode roundtrip with claims
    import time as _t
    payload = {"iss": "jeff", "exp": int(_t.time()) + 15, "claim": "insanity"}
    def t2():
        tok = jwt.encode(payload, "secret", algorithm="HS256")
        assert jwt.decode(tok, "secret", algorithms=["HS256"])["claim"] == "insanity"
    check("roundtrip", t2)

    # 3. (real: test_encode_bad_type) non-mapping payload -> TypeError
    def t3():
        try:
            jwt.encode("string", "secret")  # type: ignore[arg-type]
        except TypeError:
            return
        raise AssertionError("expected TypeError")
    check("encode bad type", t3)

    # 4. (real: test_decode_with_expiration) exp in the past -> ExpiredSignatureError
    def t4():
        import time as _t
        tok = jwt.encode({"exp": int(_t.time()) - 1}, "secret")
        try:
            jwt.decode(tok, "secret", algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return
        raise AssertionError("expected ExpiredSignatureError")
    check("expired", t4)

    # 5. (real: test_decode_with_expiration_with_leeway) leeway rescues a just-expired token
    def t5():
        import time as _t
        tok = jwt.encode({"exp": int(_t.time()) - 1}, "secret")
        jwt.decode(tok, "secret", algorithms=["HS256"], leeway=5)
    check("leeway", t5)

    # 6. (real: test_decode_with_notbefore) nbf in the future -> ImmatureSignatureError
    def t6():
        import time as _t
        tok = jwt.encode({"nbf": int(_t.time()) + 10}, "secret")
        try:
            jwt.decode(tok, "secret", algorithms=["HS256"])
        except jwt.ImmatureSignatureError:
            return
        raise AssertionError("expected ImmatureSignatureError")
    check("not before", t6)

    # 7. (real: test_check_audience_when_valid / test_raise_exception_invalid_audience)
    def t7():
        import time as _t
        p = {"aud": "urn:me", "exp": int(_t.time()) + 15}
        tok = jwt.encode(p, "secret")
        assert jwt.decode(tok, "secret", algorithms=["HS256"], audience="urn:me")["aud"] == "urn:me"
        try:
            jwt.decode(tok, "secret", algorithms=["HS256"], audience="urn:other")
        except jwt.InvalidAudienceError:
            return
        raise AssertionError("expected InvalidAudienceError")
    check("audience", t7)

    # 8. (real: test_check_issuer_when_valid / test_raise_exception_invalid_issuer)
    def t8():
        import time as _t
        p = {"iss": "jeff", "exp": int(_t.time()) + 15}
        tok = jwt.encode(p, "secret")
        jwt.decode(tok, "secret", algorithms=["HS256"], issuer="jeff")
        try:
            jwt.decode(tok, "secret", algorithms=["HS256"], issuer="bob")
        except jwt.InvalidIssuerError:
            return
        raise AssertionError("expected InvalidIssuerError")
    check("issuer", t8)

    # 9. (real: wrong-key / tampered signature -> InvalidSignatureError)
    def t9():
        tok = jwt.encode({"hello": "world"}, "secret")
        try:
            jwt.decode(tok, "wrong", algorithms=["HS256"])
        except jwt.InvalidSignatureError:
            return
        raise AssertionError("expected InvalidSignatureError")
    check("wrong key", t9)

    # 10. (real: alg confusion / alg=none -> InvalidAlgorithmError)
    def t10():
        import base64, json as _j
        h = base64.urlsafe_b64encode(_j.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(b'{"hello":"world"}').rstrip(b"=").decode()
        try:
            jwt.decode(f"{h}.{p}.", "secret", algorithms=["HS256"])
        except jwt.InvalidAlgorithmError:
            return
        raise AssertionError("expected InvalidAlgorithmError")
    check("alg none", t10)

    print(f"SCORE: {score}/10" + (f" — fails: {'; '.join(fails[:4])}" if fails else " — real-suite subset green"))
    return 0 if score >= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
