"""
Monitoring and Observability Setup for CodeMop

This module provides:
- Structured JSON logging
- Error tracking integration (Sentry)
- Performance monitoring
- Health metrics
"""

import logging
import logging.config
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import time
from functools import wraps
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from pythonjsonlogger.json import JsonFormatter
import os

# Environment variables for monitoring configuration
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SERVICE_NAME = os.getenv("SERVICE_NAME", "codemop")
ENVIRONMENT = os.getenv("APP_ENV", "production")  # same default as app.config

class CustomJsonFormatter(JsonFormatter):
    """
    Custom JSON formatter that adds additional context to logs
    """
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        
        # Add custom fields
        log_record["service"] = SERVICE_NAME
        log_record["environment"] = ENVIRONMENT
        log_record["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Add request context if available
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            log_record["user_id"] = record.user_id
        if hasattr(record, "endpoint"):
            log_record["endpoint"] = record.endpoint

def setup_logging() -> None:
    """
    Set up structured JSON logging for the application
    """
    # Configure JSON logging
    log_handler = logging.StreamHandler()
    formatter = CustomJsonFormatter(
        fmt="%(timestamp)s %(levelname)s %(service)s %(environment)s %(message)s %(name)s",
        json_ensure_ascii=False,  # keep non-ASCII text (names, titles, emoji) readable
    )
    log_handler.setFormatter(formatter)
    
    # Get root logger and configure it
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    root_logger.handlers.clear()  # Remove any existing handlers
    root_logger.addHandler(log_handler)
    
    # Configure specific loggers
    logging.getLogger("uvicorn").handlers.clear()
    logging.getLogger("uvicorn").addHandler(log_handler)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    
    logging.getLogger("sqlalchemy").handlers.clear()
    logging.getLogger("sqlalchemy").addHandler(log_handler)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    
    logging.getLogger("httpx").handlers.clear()
    logging.getLogger("httpx").addHandler(log_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Log the configuration
    logger = logging.getLogger(__name__)
    logger.info("Logging configured", extra={
        "log_level": LOG_LEVEL,
        "service": SERVICE_NAME,
        "environment": ENVIRONMENT,
        "sentry_enabled": bool(SENTRY_DSN)
    })

def setup_error_tracking() -> None:
    """
    Set up error tracking with Sentry (if configured)
    """
    if not SENTRY_DSN:
        logging.getLogger(__name__).info("Sentry DSN not configured, error tracking disabled")
        return
    
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        
        sentry_logging = LoggingIntegration(
            level=logging.INFO,        # Capture info and above
            event_level=logging.ERROR  # Send errors as events
        )
        
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=1.0 if ENVIRONMENT == "development" else 0.1,
            environment=ENVIRONMENT,
            release=os.getenv("GIT_COMMIT", "dev"),
            server_name=os.getenv("HOSTNAME", "unknown")
        )
        
        # Set up Sentry context processors
        sentry_sdk.set_tag("service", SERVICE_NAME)
        sentry_sdk.set_tag("environment", ENVIRONMENT)
        
        logging.getLogger(__name__).info("Sentry error tracking initialized")
        
    except ImportError:
        logging.getLogger(__name__).warning("Sentry SDK not installed, error tracking disabled")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to initialize Sentry: {e}")

class PerformanceMonitor:
    """
    Context manager for monitoring function performance
    """
    def __init__(self, name: str, logger: Optional[logging.Logger] = None):
        self.name = name
        self.logger = logger or logging.getLogger(__name__)
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        
        log_data = {
            "operation": self.name,
            "duration_ms": duration * 1000,
            "success": exc_type is None
        }
        
        if exc_type:
            log_data["error"] = str(exc_val)
            self.logger.error(f"Performance: {self.name} failed", extra=log_data)
        else:
            self.logger.info(f"Performance: {self.name} completed", extra=log_data)

def monitor_endpoint(operation_name: str = None):
    """
    Decorator to monitor endpoint performance
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                logger = logging.getLogger(func.__module__)
                logger.info(f"Endpoint performance: {operation_name or func.__name__}", extra={
                    "duration_ms": duration * 1000,
                    "endpoint": operation_name or func.__name__
                })
        return wrapper
    return decorator

# Prometheus metrics. They're created on import, so they always exist (recording is cheap);
# the HTTP server that exposes them only starts if ENABLE_METRICS is true
REQUEST_COUNT = Counter(
    'codemop_requests_total',
    'Total HTTP Requests',
    ['method', 'endpoint', 'status_code']
)
REQUEST_LATENCY = Histogram(
    'codemop_request_latency_seconds',
    'Request latency in seconds',
    ['method', 'endpoint']
)
ACTIVE_REQUESTS = Gauge(
    'codemop_active_requests',
    'Number of active requests'
)
ERROR_COUNT = Counter(
    'codemop_errors_total',
    'Total Errors',
    ['error_type', 'endpoint']
)

def setup_metrics() -> None:
    """
    Start the Prometheus metrics server if ENABLE_METRICS is true (off by default)
    """
    if os.getenv("ENABLE_METRICS", "false").lower() != "true":
        logging.getLogger(__name__).info("Metrics server disabled (set ENABLE_METRICS=true to enable)")
        return
    
    metrics_port = int(os.getenv("METRICS_PORT", "8001"))
    try:
        start_http_server(metrics_port)
        logging.getLogger(__name__).info(f"Metrics server started on port {metrics_port}")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to start metrics server on port {metrics_port}: {e}")

def setup_monitoring() -> None:
    """
    Set up all monitoring components
    """
    setup_logging()
    setup_error_tracking()
    setup_metrics()
    
    logger = logging.getLogger(__name__)
    logger.info("Monitoring setup completed", extra={
        "components": ["logging", "error_tracking", "metrics"]
    })
