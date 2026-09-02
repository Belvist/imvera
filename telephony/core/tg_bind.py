"""Telegram deep-link binding helper (ROADMAP E6).

Usage with existing tg/bot.py:
  /start bind_<token>  → store chat_id into contacts for household.

Token is minted by Product API and shown in the iOS app as a QR / link
``https://t.me/<bot>?start=bind_<token>``.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time


def mint_bind_token(household_id: str, ttl_sec: int = 3600) -> str:
    secret = os.environ.get("MOSS_JWT_SECRET") or os.environ.get(
        "MOSS_INTERNAL_API_TOKEN") or ""
    if not secret:
        raise RuntimeError("MOSS_JWT_SECRET or MOSS_INTERNAL_API_TOKEN required")
    nonce = secrets.token_hex(8)
    exp = int(time.time()) + ttl_sec
    payload = f"{household_id}.{exp}.{nonce}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}.{sig}"


def verify_bind_token(token: str) -> str | None:
    """Return household_id if token valid, else None."""
    secret = os.environ.get("MOSS_JWT_SECRET") or os.environ.get(
        "MOSS_INTERNAL_API_TOKEN") or ""
    if not secret or not token:
        return None
    parts = token.split(".")
    if len(parts) != 4:
        return None
    household_id, exp_s, nonce, sig = parts
    payload = f"{household_id}.{exp_s}.{nonce}"
    expect = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        if int(exp_s) < int(time.time()):
            return None
    except ValueError:
        return None
    return household_id


def parse_start_payload(text: str) -> str | None:
    """Extract bind token from ``/start bind_<token>`` or ``bind_<token>``."""
    t = (text or "").strip()
    if t.startswith("/start "):
        t = t[len("/start "):].strip()
    if t.startswith("bind_"):
        return t[len("bind_"):]
    return None
