import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")
# Timeouts, all in seconds
SESSION_TIMEOUT = 30 * 60
REQUEST_TIMEOUT = 10
