"""
Rate-limiting middleware using Redis sliding-window counters.
Blocks requests that exceed RATE_LIMIT_REQUESTS per RATE_LIMIT_WINDOW_SECONDS.
"""

from __future__ import annotations

import time

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter backed by Redis.
    Key: rate:<ip>  — expires after the window.
    Falls back gracefully if Redis is unavailable.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ("/api/health",):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        redis_key = f"rate:{client_ip}"

        try:
            from app.dependencies import get_redis
            redis = await get_redis()
            current = await redis.incr(redis_key)
            if current == 1:
                await redis.expire(redis_key, settings.RATE_LIMIT_WINDOW_SECONDS)

            if current > settings.RATE_LIMIT_REQUESTS:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests. Please slow down.",
                        "retry_after": settings.RATE_LIMIT_WINDOW_SECONDS,
                    },
                    headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)},
                )
        except Exception:
            # Redis unavailable — allow the request through (fail open)
            pass

        return await call_next(request)
