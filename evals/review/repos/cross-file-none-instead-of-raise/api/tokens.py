import secrets


def issue_token(user):
    return f"{user.id}.{secrets.token_urlsafe(32)}"
