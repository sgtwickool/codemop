# Import every model so they're all registered on Base.metadata (used by migrations)
from app.models import pr, suggestion, webhook_delivery  # noqa: F401
