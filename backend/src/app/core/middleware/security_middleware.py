"""
Security middleware for the application.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.security_config import MAX_REQUEST_SIZE, SECURITY_HEADERS
import logging

logger = logging.getLogger(__name__)


async def limit_request_size(request: Request, call_next):
    """Limit request body size to prevent DoS attacks."""
    if "content-length" in request.headers:
        try:
            size = int(request.headers["content-length"])
            if size > MAX_REQUEST_SIZE:
                logger.warning(f"Request too large: {size} bytes (max: {MAX_REQUEST_SIZE})")
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request too large. Maximum size is {MAX_REQUEST_SIZE // 1024 // 1024}MB."}
                )
        except ValueError:
            logger.warning("Invalid content-length header")
    return await call_next(request)


async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    
    # Add all security headers
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    
    return response


async def enforce_https(request: Request, call_next):
    """Enforce HTTPS for all requests."""
    if request.url.scheme != "https" and not request.headers.get("X-Forwarded-Proto"):
        logger.warning(f"Non-HTTPS request: {request.url}")
        # In production, you would redirect to HTTPS here
        # For now, just log and continue
    return await call_next(request)