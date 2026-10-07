"""
Monitoring and Observability Setup for CodeMop

This module provides:
- Structured JSON logging
- Error tracking integration (Sentry)
- Request metrics (Prometheus)
- Health metrics
"""

import logging
from typing import Dict, Any
from datetime import datetime, timezone
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from pythonjsonlogger.json import JsonFormatter
import os
from app.config import settings


class CustomJsonFormatter(JsonFormatter):
    """
    Custom JSON formatter that adds additional context to logs
    """
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        
        # Add custom fields
        log_record["service"] = settings.SERVICE_NAME
        log_record["environment"] = settings.APP_ENV
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
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
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
        "log_level": settings.LOG_LEVEL,
        "service": settings.SERVICE_NAME,
        "environment": settings.APP_ENV,
        "sentry_enabled": bool(settings.SENTRY_DSN)
    })

def setup_error_tracking() -> None:
    """
    Set up error tracking with Sentry (if configured)
    """
    if not settings.SENTRY_DSN:
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
            dsn=settings.SENTRY_DSN,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=1.0 if settings.is_development else 0.1,
            environment=settings.APP_ENV,
            release=os.getenv("GIT_COMMIT", "dev"),
            server_name=os.getenv("HOSTNAME", "unknown")
        )
        
        # Set up Sentry context processors
        sentry_sdk.set_tag("service", settings.SERVICE_NAME)
        sentry_sdk.set_tag("environment", settings.APP_ENV)
        
        logging.getLogger(__name__).info("Sentry error tracking initialized")
        
    except ImportError:
        logging.getLogger(__name__).warning("Sentry SDK not installed, error tracking disabled")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to initialize Sentry: {e}")

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
    if not settings.ENABLE_METRICS:
        logging.getLogger(__name__).info("Metrics server disabled (set ENABLE_METRICS=true to enable)")
        return
    
    metrics_port = settings.METRICS_PORT
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
