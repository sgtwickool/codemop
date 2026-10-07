"""
Monitoring Middleware for CodeMop

This module contains middleware for request monitoring and error tracking.
"""

from fastapi import Request
from typing import Callable, Awaitable
import time
import logging
from app.core.monitoring import REQUEST_COUNT, REQUEST_LATENCY, ACTIVE_REQUESTS, ERROR_COUNT

logger = logging.getLogger(__name__)

def endpoint_label(request: Request) -> str:
    """
    The route template (e.g. /api/v1/pr/{pr_id}/suggestions) rather than the raw path, so
    each PR doesn't become a separate metric series. Unmatched paths share one label.
    """
    path_format = getattr(request.scope.get("route"), "path_format", None)
    if not path_format:
        return "unmatched"
    
    # Routes from an included router don't carry its prefix (/api/v1), so take the prefix
    # from the request path: whatever comes before the route's own part
    path = request.scope.get("path", "")
    try:
        own_part = path_format.format(**request.scope.get("path_params", {}))
    except (KeyError, IndexError, ValueError):
        return path_format
    prefix = path[:-len(own_part)] if own_part and path.endswith(own_part) else ""
    return prefix + path_format

async def error_tracking_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable]
) -> Awaitable:
    """
    Middleware to track errors and exceptions with context.
    
    Captures exceptions and logs them with request context,
    updates error metrics, and re-raises the exception.
    """
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        # Log error with context
        logger.error("Request failed", extra={
            "error": str(exc),
            "error_type": type(exc).__name__,
            "method": request.method,
            "path": request.url.path,
            "user_agent": request.headers.get("user-agent", ""),
            "remote_addr": request.client.host if request.client else ""
        })
        
        # Update error metrics
        ERROR_COUNT.labels(
            error_type=type(exc).__name__,
            endpoint=endpoint_label(request)
        ).inc()
        
        # Re-raise the exception
        raise

async def request_monitoring_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable]
) -> Awaitable:
    """
    Middleware to track request metrics and performance.
    
    Tracks request duration, updates Prometheus metrics,
    and logs request completion with performance data.
    """
    start_time = time.time()
    
    # Increment active requests counter
    ACTIVE_REQUESTS.inc()
    
    response = None
    status_code = 500
    try:
        response = await call_next(request)
        status_code = getattr(response, "status_code", 500)
        return response
    finally:
        # Calculate request duration
        duration = time.time() - start_time
        
        # Update metrics
        endpoint = endpoint_label(request)
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=status_code
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(duration)
        ACTIVE_REQUESTS.dec()
        
        # Log request completion
        logger.info("Request completed", extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": duration * 1000,
            "user_agent": request.headers.get("user-agent", ""),
            "remote_addr": request.client.host if request.client else ""
        })

__all__ = ["error_tracking_middleware", "request_monitoring_middleware"]