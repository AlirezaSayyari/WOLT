import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.database import Database
from app.web.application import create_app
from app.web.config import WebSettings


DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration"
)


def test_owner_session_login_logout_and_offline_recovery(tmp_path: Path) -> None:
    assert DATABASE_URL is not None
    database = Database(DATABASE_URL)
    settings = WebSettings(
        database_url=DATABASE_URL,
        environment="test",
        static_dir=tmp_path,
        bootstrap_token="integration-bootstrap-token",
        session_hours=12,
    )

    with TestClient(create_app(settings, database)) as client:
        setup = client.post(
            "/api/v1/setup/owner",
            json={
                "bootstrap_token": "integration-bootstrap-token",
                "username": "owner",
                "email": "owner@example.com",
                "password": "first-integration-password",
            },
        )
        assert setup.status_code == 201
        recovery_code = setup.json()["recovery_code"]
        assert recovery_code
        assert "HttpOnly" in setup.headers["set-cookie"]
        assert "SameSite=strict" in setup.headers["set-cookie"]
        assert client.get("/api/v1/auth/me").json()["username"] == "owner"

        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"identifier": "owner@example.com", "password": "first-integration-password"},
        )
        assert login.status_code == 200
        old_session = client.cookies.get("wolt_session")

        recovery = client.post(
            "/api/v1/auth/recover",
            json={
                "email": "owner@example.com",
                "recovery_code": recovery_code,
                "new_password": "replacement-integration-password",
            },
        )
        assert recovery.status_code == 200
        assert recovery.json()["recovery_code"] != recovery_code

        with TestClient(create_app(settings, Database(DATABASE_URL))) as old_client:
            old_client.cookies.set("wolt_session", old_session)
            assert old_client.get("/api/v1/auth/me").status_code == 401

        assert client.post(
            "/api/v1/auth/login",
            json={"identifier": "owner", "password": "first-integration-password"},
        ).status_code == 401
        assert client.post(
            "/api/v1/auth/login",
            json={"identifier": "owner", "password": "replacement-integration-password"},
        ).status_code == 200
