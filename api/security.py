"""CSRF tokens, cookie helpers and origin checks."""

from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import Request

SESSION_COOKIE = "sentinel_session"
CSRF_COOKIE = "sentinel_csrf"
CSRF_HEADER = "X-CSRF-Token"


def csrf_token(session_id: str) -> str:
    key = os.environ.get("SENTINEL_SESSION_KEY", "").encode("utf-8")
    return hmac.new(key, session_id.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def valid_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    host = request.headers.get("host", "")
    return origin in {f"http://{host}", f"https://{host}"}


def csrf_matches(request: Request) -> bool:
    session_id = request.cookies.get(SESSION_COOKIE, "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not hmac.compare_digest(cookie, header):
        return False
    return bool(session_id) and hmac.compare_digest(cookie, csrf_token(session_id))
