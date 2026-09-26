#!/usr/bin/env python3
"""Verifier for the bug-hunt task: behaviors restored by three REAL pyjwt fixes
(#1186 793a302, #1039 9085670, #670 c8ab900 — tests ported from their suites).
Score 0-10; exit 0 iff >= 8."""
import os
import sys
import time
import warnings

sys.path.insert(0, os.getcwd())
warnings.filterwarnings("ignore")

KEY = "0123456789abcdef0123456789abcdef"  # 32 bytes: no key-length warnings


def main() -> int:
    if not os.path.isdir("jwt"):
        print("SCORE: 0/10 — jwt/ package missing in the working directory")
        return 1
    try:
        import jwt
        from jwt.api_jwt import PyJWT
        inst = PyJWT()
    except Exception as e:
        print(f"SCORE: 0/10 — cannot import jwt: {e}")
        return 1

    score = 0
    fails = []

    def check(label, fn):
        nonlocal score
        try:
            fn()
            score += 1
        except Exception as e:
            fails.append(f"{label}: {type(e).__name__}: {str(e)[:60]}")

    # --- bug #1186 (real test: test_decode_raises_clean_error_if_claim_is_non_numeric_type)
    def b1_exp_list():
        tok = jwt.encode({"exp": [1]}, KEY)
        try:
            jwt.decode(tok, KEY, algorithms=["HS256"])
        except jwt.DecodeError as e:
            assert "exp" in str(e); return
        raise AssertionError("expected DecodeError")
    check("exp=[1] -> DecodeError", b1_exp_list)

    def b1_nbf_dict():
        tok = jwt.encode({"nbf": {"a": 1}}, KEY)
        try:
            jwt.decode(tok, KEY, algorithms=["HS256"])
        except jwt.DecodeError as e:
            assert "nbf" in str(e); return
        raise AssertionError("expected DecodeError")
    check("nbf={a:1} -> DecodeError", b1_nbf_dict)

    def b1_iat_none():
        tok = jwt.encode({"iat": None}, KEY)
        try:
            jwt.decode(tok, KEY, algorithms=["HS256"])
        except jwt.InvalidIssuedAtError as e:
            assert "iat" in str(e); return
        raise AssertionError("expected InvalidIssuedAtError")
    check("iat=None -> InvalidIssuedAtError", b1_iat_none)

    def b1_exp_inf():
        tok = jwt.encode({"exp": float("inf")}, KEY)
        try:
            jwt.decode(tok, KEY, algorithms=["HS256"])
        except jwt.DecodeError as e:
            assert "exp" in str(e); return
        raise AssertionError("expected DecodeError")
    check("exp=inf -> DecodeError", b1_exp_inf)

    # --- bug #1039 (real tests: test_encode_with_non_str_iss, test_validate_iss_*)
    def b2_encode_type():
        try:
            jwt.encode({"iss": 123}, KEY)
        except TypeError:
            return
        raise AssertionError("expected TypeError")
    check("encode iss=123 -> TypeError", b2_encode_type)

    def b2_container_numeric_match():
        try:
            inst._validate_iss({"iss": 123}, issuer=[123])
        except jwt.InvalidIssuerError:
            return
        raise AssertionError("non-str iss must not validate against numeric container")
    check("iss=123 vs issuer=[123] -> InvalidIssuerError", b2_container_numeric_match)

    def b2_decode_non_str():
        try:
            inst._validate_iss({"iss": 777}, issuer="urn:x")
        except jwt.InvalidIssuerError as e:
            assert "must be a string" in str(e); return
        raise AssertionError("expected InvalidIssuerError")
    check("validate iss=777 -> type error message", b2_decode_non_str)

    def b2_container_of_str_ok():
        inst._validate_iss({"iss": "urn:expected"}, issuer=["urn:expected", "urn:other"])
    check("container issuer accepted", b2_container_of_str_ok)

    # --- bug #670 (real tests: aud-null handling)
    def b3_aud_null_with_audience():
        tok = jwt.encode({"aud": None, "exp": int(time.time()) + 15}, KEY)
        try:
            jwt.decode(tok, KEY, algorithms=["HS256"], audience="urn:me")
        except jwt.MissingRequiredClaimError:
            return
        raise AssertionError("expected MissingRequiredClaimError")
    check("aud=None + audience -> MissingRequiredClaimError", b3_aud_null_with_audience)

    def b3_aud_null_without_audience():
        tok = jwt.encode({"aud": None, "exp": int(time.time()) + 15}, KEY)
        jwt.decode(tok, KEY, algorithms=["HS256"])
    check("aud=None without audience -> decodes", b3_aud_null_without_audience)

    print(f"SCORE: {score}/10" + (f" — fails: {'; '.join(fails[:4])}" if fails else " — all three hunts verified"))
    return 0 if score >= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
