import os
import time
import json
import base64
from typing import Dict, Any

import httpx
from fastapi import Header, HTTPException
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes

# Simple in-memory JWKS cache
_JWKS_CACHE: Dict[str, Any] = {"keys": {}, "fetched": 0, "ttl": 600}


def _base64url_decode(input_str: str) -> bytes:
    # Add padding if necessary
    rem = len(input_str) % 4
    if rem:
        input_str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(input_str.encode())


def _fetch_jwks(jwks_url: str) -> Dict[str, dict]:
    try:
        resp = httpx.get(jwks_url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        keys = {k["kid"]: k for k in data.get("keys", [])}
        return keys
    except Exception as e:
        raise RuntimeError(f"failed to fetch JWKS: {e}")


def _get_jwks_map(jwks_url: str) -> Dict[str, dict]:
    now = time.time()
    if (_JWKS_CACHE["fetched"] == 0) or (now - _JWKS_CACHE["fetched"] > _JWKS_CACHE["ttl"]):
        keys = _fetch_jwks(jwks_url)
        _JWKS_CACHE["keys"] = keys
        _JWKS_CACHE["fetched"] = now
    return _JWKS_CACHE["keys"]


def _pubkey_from_jwk(jwk: dict) -> rsa.RSAPublicKey:
    # jwk contains 'n' and 'e' in base64url
    n_b = _base64url_decode(jwk["n"])
    e_b = _base64url_decode(jwk["e"])
    n = int.from_bytes(n_b, "big")
    e = int.from_bytes(e_b, "big")
    numbers = rsa.RSAPublicNumbers(e, n)
    return numbers.public_key()


def _verify_rs256(token: str, jwks_url: str, expected_issuer: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="invalid token format")

    header_b = _base64url_decode(parts[0])
    payload_b = _base64url_decode(parts[1])
    sig = _base64url_decode(parts[2])

    try:
        header = json.loads(header_b)
        payload = json.loads(payload_b)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token encoding")

    if header.get("alg") != "RS256":
        raise HTTPException(status_code=401, detail=f"unsupported alg {header.get('alg')}")

    # issuer check
    iss = payload.get("iss")
    if iss != expected_issuer:
        raise HTTPException(status_code=401, detail="invalid token issuer")

    # expiry
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or time.time() > float(exp):
        raise HTTPException(status_code=401, detail="token expired")

    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="missing kid in token header")

    jwks_map = _get_jwks_map(jwks_url)
    jwk = jwks_map.get(kid)
    if not jwk:
        # refresh once and retry
        jwks_map = _fetch_jwks(jwks_url)
        jwk = jwks_map.get(kid)
        if not jwk:
            raise HTTPException(status_code=401, detail="matching JWK not found")

    pubkey = _pubkey_from_jwk(jwk)

    signing_input = (parts[0] + "." + parts[1]).encode()

    try:
        pubkey.verify(sig, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token signature")

    return payload


def get_current_user(authorization: str | None = Header(None, alias="Authorization")) -> Dict[str, Any] | None:
    """FastAPI dependency: validate Bearer token issued by Keycloak.

    If `KEYCLOAK_ISSUER` is not set, this function raises a 503 so callers
    are aware auth isn't configured.
    """
    issuer = os.getenv("KEYCLOAK_ISSUER", "")
    if not issuer:
        raise HTTPException(status_code=503, detail="KEYCLOAK_ISSUER not configured")

    jwks_url = issuer.rstrip("/") + "/protocol/openid-connect/certs"

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing Authorization header")

    token = authorization.split(" ", 1)[1].strip()
    return _verify_rs256(token, jwks_url, issuer)
