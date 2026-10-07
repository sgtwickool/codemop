from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Index, String, UniqueConstraint
from app.models.base import BaseModel

class WebhookDelivery(BaseModel):
    """A processed GitHub webhook delivery, so redeliveries of it can be ignored"""
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("delivery_id", name="uq_webhook_deliveries_delivery_id"),
        Index("ix_webhook_deliveries_created_at", "created_at"),  # for pruning old rows
    )

    delivery_id: Mapped[str] = mapped_column(String(64))  # X-GitHub-Delivery
    event: Mapped[str] = mapped_column(String(64))
