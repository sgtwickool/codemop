"""
Shared rate limiter.

Every endpoint uses this one instance, so limits are tracked in one place and can be
disabled or reset as a whole (the tests rely on this).
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return 429 in the same {"detail": ...} shape as other errors, with Retry-After."""
    headers = {}
    if exc.limit is not None:
        headers["Retry-After"] = str(exc.limit.limit.get_expiry())
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
        headers=headers,
    )
