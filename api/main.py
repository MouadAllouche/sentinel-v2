"""FastAPI application factory."""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.deps import ApiError
from api.routers import auth, config_router, events, incidents, rules, stream, system
from api.security import csrf_matches, valid_origin
from core.config import Settings, load_settings
from core.rules.models import RuleValidationError
from storage.database import init_db

__all__ = ["app", "create_app"]

RATE_LIMITED = {
    "/api/rules/preview",
    "/api/rules/import",
    "/api/events/export",
    "/api/events/reapply-severity",
    "/api/engine/run",
}
_requests: dict[str, list[float]] = defaultdict(list)


def _assert_runtime_guard(config: Settings) -> None:
    """Fail closed at startup, not at import (tests import the module without a key)."""
    key = os.environ.get("SENTINEL_SESSION_KEY", "")
    if not key:
        raise RuntimeError("SENTINEL_SESSION_KEY must be set before starting the API")
    if len(key) < 32:
        raise RuntimeError("SENTINEL_SESSION_KEY must be at least 32 characters")
    if config.api.host not in {"127.0.0.1", "localhost", "::1"}:
        if not (config.api.allow_remote and config.api.trusted_proxy):
            raise RuntimeError(
                "non-loopback binds require allow_remote and a trusted_proxy/TLS note"
            )
        # valid_origin() trusts X-Forwarded-* so the browser-facing origin can be
        # reconstructed behind the proxy. That is only safe when the API is
        # reachable exclusively through that proxy: strip client-supplied
        # forwarded headers at the proxy edge and bind to loopback where possible.
        logging.getLogger(__name__).warning(
            "API bound to non-loopback host %s with forwarded-header trust enabled "
            "(trusted_proxy=%s); ensure the proxy overwrites X-Forwarded-* headers "
            "and blocks direct access to the backend",
            config.api.host,
            config.api.trusted_proxy,
        )


def create_app(settings: Settings | None = None, db_path: str | None = None) -> FastAPI:
    config = settings or load_settings()
    target = db_path or str(config.paths.database)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _assert_runtime_guard(config)
        init_db(target)
        yield

    app = FastAPI(
        title="Sentinel API",
        version="2.0.0",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs" if config.api.docs_enabled else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.db_path = target

    @app.middleware("http")
    async def security(request: Request, call_next: Any) -> Any:
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/api/auth/login"
            and request.cookies.get("sentinel_session")
        ):
            if not valid_origin(request):
                return JSONResponse(
                    status_code=403,
                    content={"error": {"code": "csrf_failed", "message": "origin mismatch"}},
                )
            if not csrf_matches(request):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {"code": "csrf_failed", "message": "missing or invalid CSRF token"}
                    },
                )
        length = request.headers.get("content-length")
        limit = 2 * 1024 * 1024 if "/rules/import" in request.url.path else 1024 * 1024
        if length and length.isdigit() and int(length) > limit:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {"code": "payload_too_large", "message": "request body too large"}
                },
            )
        if request.url.path in RATE_LIMITED and request.method == "POST":
            identity = request.client.host if request.client else "unknown"
            now = time.monotonic()
            recent = [stamp for stamp in _requests[identity] if now - stamp < 3600]
            _requests[identity] = recent
            if len(recent) >= 10:
                return JSONResponse(
                    status_code=429,
                    content={"error": {"code": "rate_limited", "message": "too many requests"}},
                )
            recent.append(now)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

    @app.exception_handler(ApiError)
    async def api_error(_request: Request, exc: ApiError) -> JSONResponse:
        body: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.details:
            body["details"] = exc.details
        return JSONResponse(status_code=exc.status, content={"error": body})

    @app.exception_handler(RuleValidationError)
    async def rule_error(_request: Request, exc: RuleValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "invalid rule",
                    "details": exc.errors,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"path": ".".join(str(part) for part in error["loc"]), "message": str(error["msg"])}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "invalid request",
                    "details": details,
                }
            },
        )

    for module in (auth, events, incidents, rules, config_router, system, stream):
        app.include_router(module.router)
    return app


# Module-level ASGI app for `uvicorn api.main:app` (make api, deploy units).
# The session key is enforced at request/startup time by create_app's guard.
app = create_app()
