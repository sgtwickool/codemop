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
        if ERROR_COUNT:
            ERROR_COUNT.labels(
                error_type=type(exc).__name__,
                endpoint=request.url.path
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
    if ACTIVE_REQUESTS:
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
        if REQUEST_COUNT:
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=status_code
            ).inc()
        
        if REQUEST_LATENCY:
            REQUEST_LATENCY.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(duration)
        
        if ACTIVE_REQUESTS:
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