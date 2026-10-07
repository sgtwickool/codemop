"""
CORS is off unless CORS_ORIGINS lists browser origins, and never allows credentials.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.security_config import cors_settings


def test_no_cross_origin_access_by_default(client):
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_origins_are_parsed_from_a_comma_separated_list():
    settings = Settings(_env_file=None, CORS_ORIGINS=" https://a.example, https://b.example ,")

    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_configured_origins_are_allowed_without_credentials():
    app = FastAPI()
    app.add_middleware(CORSMiddleware, **cors_settings(["https://dashboard.example"]))
    app.get("/ping")(lambda: {"ok": True})
    client = TestClient(app)

    allowed = client.get("/ping", headers={"Origin": "https://dashboard.example"})
    other = client.get("/ping", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "https://dashboard.example"
    assert "access-control-allow-credentials" not in allowed.headers
    assert "access-control-allow-origin" not in other.headers
