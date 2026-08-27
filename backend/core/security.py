"""Security primitives: admin auth, rate limiting, headers, request ids."""

from __future__ import annotations

import hmac
import time
import uuid
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import Settings, get_settings
from .logging import request_id_ctx


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request and sets secure headers."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["x-request-id"] = rid
        response.headers["x-response-time-ms"] = \
            f"{(time.perf_counter() - started) * 1000:.2f}"
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "SAMEORIGIN"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["permissions-policy"] = "geolocation=(), microphone=()"
        response.headers["content-security-policy"] = (
            "default-src 'none'; frame-ancestors 'self'")
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-IP limiter with a stricter bucket for expensive routes.

    In-process only: a multi-worker deployment should place a shared limiter
    (Redis / gateway) in front. Documented in docs/SECURITY.md.
    """

    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def _limited(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.time()
        bucket = self._buckets[key]
        while bucket and bucket[0] < now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            return True
        bucket.append(now)
        return False

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        path = request.url.path
        expensive = path.startswith("/api/simulation") or path.startswith("/api/demo")
        limit = (self.settings.simulation_rate_limit_per_minute if expensive
                 else self.settings.rate_limit_per_minute)
        key = f"{ip}:{'sim' if expensive else 'std'}"
        if self._limited(key, limit):
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "rate limit exceeded", "limit_per_minute": limit})
        return await call_next(request)


def require_admin(x_admin_key: Optional[str] = Header(default=None),
                  settings: Settings = Depends(get_settings)) -> str:
    """Dependency guarding administrative/debug endpoints.

    If no ``ADMIN_API_KEY`` is configured, admin endpoints are available only
    outside production — never silently open in production.
    """
    if not settings.admin_api_key:
        if settings.is_production:
            raise HTTPException(status_code=503,
                                detail="admin endpoints disabled: ADMIN_API_KEY unset")
        return "dev-unauthenticated"
    if not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="invalid admin key")
    return "admin"
