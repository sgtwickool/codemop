"""
Security configuration and constants for the application.
"""

# Rate limit configurations
# The GitHub webhook and the health check aren't rate limited (see
# app/api/v1/endpoints/webhooks.py); the health check is polled by orchestrators
RATE_LIMITS = {
    "suggestions": "60/minute",
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

# The interactive API docs (Swagger UI, ReDoc) load their assets from CDNs and use
# inline scripts, so they get a looser policy than the JSON API
DOCS_PATHS = ("/api/v1/docs", "/api/v1/redoc")
DOCS_CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly",
    "worker-src 'self' blob:",
])

# CORS, for browser origins listed in CORS_ORIGINS. The API authenticates with the
# Authorization header, not cookies, so credentials (cookies) are never needed
def cors_settings(origins):
    return {
        "allow_origins": origins,
        "allow_credentials": False,
        "allow_methods": ["GET"],
        "allow_headers": ["Authorization", "Content-Type"],
    }
