from fastapi import APIRouter
from app.api.v1.endpoints import health, webhooks, suggestions

api_router = APIRouter()

# Include all endpoints
api_router.include_router(health.router, prefix="", tags=["health"])
api_router.include_router(webhooks.router, prefix="", tags=["webhooks"])
api_router.include_router(suggestions.router, prefix="", tags=["suggestions"])