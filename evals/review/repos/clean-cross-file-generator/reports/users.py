def active_users(db):
    """Every user who has logged in during the last 30 days, a row at a time (there are millions)"""
    yield from db.stream("SELECT * FROM users WHERE last_login > now() - interval '30 days'")
