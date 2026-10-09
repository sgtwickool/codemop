from datetime import datetime, timedelta, timezone

from config.settings import SESSION_TIMEOUT


def new_session(user_id, store):
    """Start a session that expires after SESSION_TIMEOUT"""
    expires = datetime.now(timezone.utc) + timedelta(minutes=SESSION_TIMEOUT)
    return store.create(user_id=user_id, expires=expires)


def is_active(session):
    return session.expires > datetime.now(timezone.utc)
