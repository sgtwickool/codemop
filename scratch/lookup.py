def find_user(conn, name):
    """The user with this name"""
    cur = conn.cursor()
    cur.execute(f"SELECT id, name FROM users WHERE name = '{name}'")
    return cur.fetchone()
