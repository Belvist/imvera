"""Product API authentication: OTP + JWT HS256 (MVP).

MVP signs tokens with HMAC-SHA256 (`MOSS_JWT_SECRET`). Production next step
is RS256 with short-lived access tokens, rotating refresh, and a JWKS
endpoint — keep claim shape (`sub`, `typ`, `phone`) stable across that cut.

Never log OTP codes or raw tokens.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Optional


class AuthError(Exception):
    """401 / auth failure."""


class AuthConfigError(Exception):
    """503 — JWT secret missing or misconfigured."""


def phone_hash(phone_digits: str) -> str:
    return hashlib.sha256((phone_digits or "").encode("utf-8")).hexdigest()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _jwt_secret() -> bytes:
    secret = os.environ.get("MOSS_JWT_SECRET", "").strip()
    if not secret or len(secret) < 16:
        raise AuthConfigError(
            "MOSS_JWT_SECRET must be set to a strong secret (≥16 chars); "
            "HS256 MVP — migrate to RS256 + JWKS next")
    return secret.encode("utf-8")


def issue_jwt(claims: dict, ttl_seconds: int, secret: Optional[bytes] = None
              ) -> str:
    """Mint a compact HS256 JWT. Documented upgrade path: RS256."""
    key = secret if secret is not None else _jwt_secret()
    now = int(time.time())
    payload = dict(claims)
    payload.setdefault("iat", now)
    payload["exp"] = now + int(ttl_seconds)
    header = {"alg": "HS256", "typ": "JWT"}
    head = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    body = _b64url_encode(json.dumps(payload, separators=(",", ":"),
                                     ensure_ascii=False).encode())
    signing_input = f"{head}.{body}".encode("ascii")
    sig = hmac.new(key, signing_input, hashlib.sha256).digest()
    return f"{head}.{body}.{_b64url_encode(sig)}"


def verify_jwt(token: str, expected_typ: Optional[str] = None,
               secret: Optional[bytes] = None) -> dict:
    key = secret if secret is not None else _jwt_secret()
    parts = (token or "").split(".")
    if len(parts) != 3:
        raise AuthError("invalid token")
    head_b, body_b, sig_b = parts
    signing_input = f"{head_b}.{body_b}".encode("ascii")
    expected = hmac.new(key, signing_input, hashlib.sha256).digest()
    try:
        got = _b64url_decode(sig_b)
    except Exception as exc:  # noqa: BLE001
        raise AuthError("invalid token") from exc
    if not hmac.compare_digest(expected, got):
        raise AuthError("invalid token")
    try:
        header = json.loads(_b64url_decode(head_b))
        payload = json.loads(_b64url_decode(body_b))
    except Exception as exc:  # noqa: BLE001
        raise AuthError("invalid token") from exc
    if header.get("alg") != "HS256":
        raise AuthError("unsupported token alg")
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        raise AuthError("token expired")
    if expected_typ is not None and payload.get("typ") != expected_typ:
        raise AuthError("wrong token type")
    return payload


def issue_token_pair(user_id: str, phone: str,
                     access_ttl: Optional[int] = None,
                     refresh_ttl: Optional[int] = None) -> dict:
    access_ttl = access_ttl or int(
        os.environ.get("MOSS_JWT_ACCESS_TTL", "900"))
    refresh_ttl = refresh_ttl or int(
        os.environ.get("MOSS_JWT_REFRESH_TTL", "604800"))
    access = issue_jwt(
        {"sub": user_id, "phone": phone, "typ": "access"}, access_ttl)
    refresh = issue_jwt(
        {"sub": user_id, "phone": phone, "typ": "refresh",
         "jti": secrets.token_hex(8)}, refresh_ttl)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": access_ttl,
    }


# --------------------------------------------------------------------------- #
# OTP store (Redis when configured, else process-local TTL map).
# --------------------------------------------------------------------------- #


class OtpStore:
    """Abstract OTP storage. Implementations must never log codes."""

    def put(self, phone: str, code: str, ttl_seconds: int = 300) -> None:
        raise NotImplementedError

    def verify_and_consume(self, phone: str, code: str) -> bool:
        raise NotImplementedError


class MemoryOtpStore(OtpStore):
    def __init__(self, clock=time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self._items = {}  # phone -> (code, expires_at)

    def put(self, phone: str, code: str, ttl_seconds: int = 300) -> None:
        with self._lock:
            self._items[phone] = (code, self._clock() + float(ttl_seconds))

    def verify_and_consume(self, phone: str, code: str) -> bool:
        now = self._clock()
        with self._lock:
            row = self._items.get(phone)
            if row is None:
                return False
            stored, expires = row
            if expires < now:
                self._items.pop(phone, None)
                return False
            if not hmac.compare_digest(stored, code):
                return False
            self._items.pop(phone, None)
            return True


class RedisOtpStore(OtpStore):
    def __init__(self, url: str, prefix: str = "moss:otp:"):
        import redis

        self._r = redis.Redis.from_url(url, decode_responses=True)
        self._prefix = prefix
        self._r.ping()

    def _key(self, phone: str) -> str:
        return self._prefix + phone_hash(phone)

    def put(self, phone: str, code: str, ttl_seconds: int = 300) -> None:
        # Store only the hash of the code so a Redis dump does not leak OTPs.
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        self._r.setex(self._key(phone), int(ttl_seconds), digest)

    def verify_and_consume(self, phone: str, code: str) -> bool:
        key = self._key(phone)
        stored = self._r.get(key)
        if not stored:
            return False
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(stored, digest):
            return False
        self._r.delete(key)
        return True


def build_otp_store(redis_url: Optional[str] = None) -> OtpStore:
    url = redis_url if redis_url is not None else os.environ.get(
        "MOSS_REDIS_URL", "").strip()
    if url:
        try:
            return RedisOtpStore(url)
        except Exception:  # noqa: BLE001
            # Fail open to memory for local/dev; production should set Redis
            # and monitor — never silently accept without a store.
            pass
    return MemoryOtpStore()


def generate_otp_code() -> str:
    """6-digit OTP. In dev, `MOSS_OTP_DEV_CODE` forces a fixed code."""
    dev = os.environ.get("MOSS_OTP_DEV_CODE", "").strip()
    if dev:
        if not dev.isdigit() or not (4 <= len(dev) <= 8):
            raise AuthConfigError(
                "MOSS_OTP_DEV_CODE must be 4–8 digits when set")
        return dev
    return f"{secrets.randbelow(1_000_000):06d}"


def request_otp(store: OtpStore, phone_digits: str, ttl_seconds: int = 300
                ) -> dict:
    code = generate_otp_code()
    store.put(phone_digits, code, ttl_seconds=ttl_seconds)
    # SMS / push delivery is out of scope for Э4 MVP; never return the code.
    return {"ok": True, "expires_in": ttl_seconds}


def verify_otp(store: OtpStore, phone_digits: str, code: str) -> bool:
    code = (code or "").strip()
    if not code:
        return False
    if store.verify_and_consume(phone_digits, code):
        return True
    # Dev override: accept MOSS_OTP_DEV_CODE even if a prior random OTP remains.
    dev = os.environ.get("MOSS_OTP_DEV_CODE", "").strip()
    if not (dev and hmac.compare_digest(dev, code)):
        return False
    _clear_otp(store, phone_digits)
    return True


def _clear_otp(store: OtpStore, phone_digits: str) -> None:
    if isinstance(store, MemoryOtpStore):
        with store._lock:
            store._items.pop(phone_digits, None)
        return
    if isinstance(store, RedisOtpStore):
        try:
            store._r.delete(store._key(phone_digits))
        except Exception:  # noqa: BLE001
            pass
