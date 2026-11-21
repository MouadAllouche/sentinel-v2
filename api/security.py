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


def _first(value: str | None) -> str:
    """Proxy headers may hold a comma-separated chain; the first hop wins."""
    return (value or "").split(",")[0].strip()


def valid_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    # A reverse proxy (the Next.js /api rewrite in production) changes the
    # backend's Host header to its internal bind address. The browser-facing
    # origin is carried in X-Forwarded-*; compare against that when present so
    # legitimate same-origin mutations are not rejected as cross-site.
    proto = _first(request.headers.get("x-forwarded-proto")) or request.url.scheme
    forwarded_host = _first(request.headers.get("x-forwarded-host"))
    if forwarded_host:
        host = forwarded_host
        port = _first(request.headers.get("x-forwarded-port"))
        if port and ":" not in host and (proto, port) not in {("http", "80"), ("https", "443")}:
            host = f"{host}:{port}"
    else:
        host = request.headers.get("host", "")
    return origin in {f"{proto}://{host}"}


def csrf_matches(request: Request) -> bool:
    session_id = request.cookies.get(SESSION_COOKIE, "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not hmac.compare_digest(cookie, header):
        return False
    return bool(session_id) and hmac.compare_digest(cookie, csrf_token(session_id))
