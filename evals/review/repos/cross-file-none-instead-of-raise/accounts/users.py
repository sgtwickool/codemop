from dataclasses import dataclass
from typing import Optional


class UserNotFound(Exception):
    pass


@dataclass
class User:
    id: int
    email: str
    password_hash: str

    def check_password(self, password, hasher):
        return hasher.verify(password, self.password_hash)


def find_user(db, email) -> Optional["User"]:
    """The user with this email address, or None if there isn't one"""
    row = db.fetch_one("SELECT id, email, password_hash FROM users WHERE email = ?", (email.lower(),))
    if row is None:
        return None
    return User(**row)
