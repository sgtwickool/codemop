"""
Security configuration and constants for the application.
"""

# Rate limit configurations
RATE_LIMITS = {
    "webhook": "10/minute",
    "suggestions": "60/minute",
    "health": "120/minute"
}

# Request size limits
MAX_REQUEST_SIZE = 1024 * 1024  # 1MB

# Security headers configuration
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'self'"
}

# CORS configuration
CORS_SETTINGS = {
    "allow_origins": ["*"],
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

# API security settings
API_SECURITY = {
    "default_rate_limit": "60/minute",
    "max_request_size": MAX_REQUEST_SIZE,
    "require_https": True,
    "strict_transport_security": "max-age=31536000; includeSubDomains; preload"
}