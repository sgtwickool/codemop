from accounts.users import UserNotFound, find_user
from api.tokens import issue_token


def login(db, hasher, email, password):
    """POST /login: a session token for the right email and password"""
    try:
        user = find_user(db, email)
    except UserNotFound:
        return {"error": "Wrong email or password"}, 401
    if not user.check_password(password, hasher):
        return {"error": "Wrong email or password"}, 401
    return {"token": issue_token(user)}, 200
