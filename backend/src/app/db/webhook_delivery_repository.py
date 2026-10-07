from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.webhook_delivery import WebhookDelivery
from app.db.base import BaseRepository, on_conflict_insert

# GitHub only redelivers recent deliveries, so older IDs can't come back
RETENTION = timedelta(days=7)

class WebhookDeliveryRepository(BaseRepository[WebhookDelivery]):
    """Webhook delivery repository"""
    
    def __init__(self):
        super().__init__(WebhookDelivery)
    
    def record(self, db: Session, delivery_id: str, event: str) -> bool:
        """
        Record a delivery. Returns False if it was already recorded (a redelivery).
        
        Doesn't commit, so a delivery whose processing fails is rolled back with it
        and gets processed again when GitHub redelivers it.
        """
        statement = (
            on_conflict_insert(db, WebhookDelivery)
            .values(delivery_id=delivery_id, event=event)
            .on_conflict_do_nothing(index_elements=["delivery_id"])
            .returning(WebhookDelivery.id)
        )
        return db.execute(statement).scalar_one_or_none() is not None
    
    def prune(self, db: Session) -> int:
        """Delete deliveries older than RETENTION; returns how many. Doesn't commit."""
        # created_at is stored as naive UTC
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - RETENTION
        return (
            db.query(WebhookDelivery)
            .filter(WebhookDelivery.created_at < cutoff)
            .delete(synchronize_session=False)
        )

webhook_delivery_repository = WebhookDeliveryRepository()
