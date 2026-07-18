import os
import socket
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import paramiko
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database import Database
from app.infrastructure.database.models import DeviceCredential, WakeEvent
from app.parser import build_magic_packet
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
        master_key="33" * 32,
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

        host_key = paramiko.RSAKey.generate(1024)
        host_key_line = (
            f"127.0.0.1 {host_key.get_name()} {host_key.get_base64()}"
        )
        created_device = client.post(
            "/api/v1/devices",
            json={
                "name": "Integration FortiGate",
                "driver_type": "fortigate_ssh",
                "configuration": {
                    "host": "127.0.0.1",
                    "port": 22,
                    "host_key": host_key_line,
                },
                "credentials": {
                    "username": "wol-service",
                    "password": "device-integration-secret",
                },
                "enabled": True,
            },
        )
        assert created_device.status_code == 201
        device = created_device.json()
        assert device["credential_configured"] is True
        assert "credentials" not in device
        assert "password" not in str(device)

        with database.session() as db_session:
            encrypted = db_session.scalar(select(DeviceCredential.encrypted_payload))
            assert encrypted is not None
            assert "device-integration-secret" not in encrypted

        created_listener = client.post(
            "/api/v1/listeners",
            json={
                "device_id": device["id"],
                "name": "Integration VLAN",
                "description": "Phase 4 acceptance mapping",
                "udp_port": None,
                "allowed_source_ip": "127.0.0.1",
                "driver_parameters": {
                    "interface": "demo-vlan-16",
                    "gateway_ip": "198.51.100.94",
                },
                "enabled": True,
            },
        )
        assert created_listener.status_code == 201
        listener = created_listener.json()
        assert listener["udp_port"] == 40000

        resumed = client.post("/api/v1/engine/resume")
        assert resumed.status_code == 200
        assert resumed.json()["observed_state"] == "active"
        assert resumed.json()["active_listeners"] == 1
        assert client.get("/api/v1/listeners").json()[0]["status"] == "active"

        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender.sendto(
            build_magic_packet(bytes.fromhex("02AABBCCDD16")),
            ("127.0.0.1", listener["udp_port"]),
        )
        sender.close()
        recorded_event = None
        for _attempt in range(30):
            with database.session() as db_session:
                recorded_event = db_session.scalar(select(WakeEvent))
            if recorded_event is not None:
                break
            time.sleep(0.1)
        assert recorded_event is not None
        assert recorded_event.mac_address == "02:AA:BB:CC:DD:16"
        assert recorded_event.result_code == "ssh_connection_failed"

        events = client.get(
            "/api/v1/events",
            params={"query": "02:AA:BB", "result_code": "ssh_connection_failed"},
        )
        assert events.status_code == 200
        assert events.json()["total"] == 1
        assert events.json()["items"][0]["mapping_name"] == "Integration VLAN"
        assert client.get(
            "/api/v1/events", params={"result_code": "failed"}
        ).json()["total"] == 1

        dashboard = client.get("/api/v1/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["total_requests"] == 1
        assert dashboard.json()["failed"] == 1
        assert len(dashboard.json()["series"]) == 24

        audit = client.get("/api/v1/audit", params={"query": "device.created"})
        assert audit.status_code == 200
        assert audit.json()["total"] == 1
        assert audit.json()["items"][0]["actor"] == "owner"

        exported = client.get("/api/v1/events/export.csv")
        assert exported.status_code == 200
        assert "text/csv" in exported.headers["content-type"]
        assert "02:AA:BB:CC:DD:16" in exported.text

        updated_settings = client.put(
            "/api/v1/settings/retention",
            json={
                "wake_event_retention_days": 1,
                "audit_event_retention_days": 30,
                "rate_limit_seconds": 15,
            },
        )
        assert updated_settings.status_code == 200
        assert updated_settings.json()["rate_limit_seconds"] == 15

        paused = client.post("/api/v1/engine/pause")
        assert paused.status_code == 200
        assert paused.json()["observed_state"] == "paused"
        assert client.get("/api/v1/listeners").json()[0]["status"] == "inactive"

        assert client.delete(f"/api/v1/listeners/{listener['id']}").status_code == 409
        with database.session() as db_session:
            stored_event = db_session.scalar(select(WakeEvent))
            assert stored_event is not None
            stored_event.occurred_at = datetime.now(UTC) - timedelta(days=2)
            db_session.commit()
        cleanup = client.post("/api/v1/settings/retention/run")
        assert cleanup.status_code == 200
        assert cleanup.json()["wake_events"] == 1
        assert client.delete(f"/api/v1/listeners/{listener['id']}").status_code == 204
        assert client.delete(f"/api/v1/devices/{device['id']}").status_code == 204
