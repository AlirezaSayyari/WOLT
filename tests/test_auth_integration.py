import os
import re
import socket
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import paramiko
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database import Database
from app.infrastructure.database.models import DeviceCredential, SmtpSettings, WakeEvent
from app.infrastructure.email import SmtpMailer
from app.drivers.base import HostKeyDiscoveryResult
from app.drivers.fortigate_ssh import FortiGateSSHDriver
from app.parser import build_magic_packet
from app.web.application import create_app
from app.web.config import WebSettings


DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration"
)


def test_owner_session_login_logout_and_offline_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    delivered: list[dict[str, str]] = []

    def capture_mail(
        _self: SmtpMailer, _configuration: object, *, recipient: str,
        subject: str, text: str,
    ) -> None:
        delivered.append({"recipient": recipient, "subject": subject, "text": text})

    monkeypatch.setattr(SmtpMailer, "send", capture_mail)

    with TestClient(create_app(settings, database)) as client:
        assert client.post(
            "/api/v1/devices/discover-host-key",
            json={"configuration": {}, "credentials": {}},
        ).status_code == 401
        assert client.get("/api/v1/host/status").status_code == 401
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
        owner_session = client.cookies.get("wolt_session")
        unavailable_agent = client.get("/api/v1/host/status")
        assert unavailable_agent.status_code == 503
        assert unavailable_agent.json()["detail"] == "host_agent_not_configured"

        smtp_secret = "integration-smtp-secret"
        saved_smtp = client.put(
            "/api/v1/smtp",
            json={
                "host": "smtp.example.com", "port": 587, "security": "starttls",
                "from_email": "wolt@example.com", "from_name": "WOLT",
                "public_base_url": "https://wolt.example.com", "username": "mailer",
                "password": smtp_secret, "enabled": True,
            },
        )
        assert saved_smtp.status_code == 200
        assert saved_smtp.json()["password_configured"] is True
        assert smtp_secret not in saved_smtp.text
        with database.session() as db_session:
            encrypted_smtp = db_session.get(SmtpSettings, 1)
            assert encrypted_smtp is not None
            assert smtp_secret not in encrypted_smtp.encrypted_credentials

        invitation = client.post(
            "/api/v1/users/invitations",
            json={"username": "phase6admin", "email": "admin@example.com", "role": "administrator"},
        )
        assert invitation.status_code == 201
        invite_token = re.search(r"token=([^\s]+)", delivered[-1]["text"])
        assert invite_token is not None
        pending_users = client.get("/api/v1/users")
        assert pending_users.status_code == 200
        assert next(item for item in pending_users.json() if item["username"] == "phase6admin")["status"] == "pending"
        assert client.post(
            "/api/v1/auth/accept-invitation",
            json={"token": invite_token.group(1), "password": "admin-integration-password"},
        ).status_code == 204
        assert client.post(
            "/api/v1/auth/accept-invitation",
            json={"token": invite_token.group(1), "password": "admin-integration-password"},
        ).status_code == 400

        client.cookies.clear()
        assert client.post(
            "/api/v1/auth/login",
            json={"identifier": "phase6admin", "password": "admin-integration-password"},
        ).status_code == 200
        assert client.get("/api/v1/users").status_code == 403
        assert client.get("/api/v1/host/status").status_code == 403
        assert client.get("/api/v1/settings").status_code == 200
        reset_request = client.post(
            "/api/v1/auth/password-reset/request", json={"email": "admin@example.com"}
        )
        assert reset_request.status_code == 202
        reset_token = re.search(r"token=([^\s]+)", delivered[-1]["text"])
        assert reset_token is not None
        assert client.post(
            "/api/v1/auth/password-reset/complete",
            json={"token": reset_token.group(1), "password": "new-admin-integration-password"},
        ).status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.post(
            "/api/v1/auth/login",
            json={"identifier": "admin@example.com", "password": "new-admin-integration-password"},
        ).status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 204
        client.cookies.set("wolt_session", owner_session)
        assert client.get("/api/v1/auth/me").json()["role"] == "owner"
        owner_record = next(item for item in client.get("/api/v1/users").json() if item["role"] == "owner")
        assert client.put(
            f"/api/v1/users/{owner_record['id']}",
            json={"role": "owner", "enabled": False},
        ).status_code == 409

        operator_invitation = client.post(
            "/api/v1/users/invitations",
            json={"username": "phase6operator", "email": "operator@example.com", "role": "operator"},
        )
        assert operator_invitation.status_code == 201
        operator_token = re.search(r"token=([^\s]+)", delivered[-1]["text"])
        assert operator_token is not None
        assert client.post(
            "/api/v1/auth/accept-invitation",
            json={"token": operator_token.group(1), "password": "operator-integration-password"},
        ).status_code == 204
        client.cookies.clear()
        assert client.post(
            "/api/v1/auth/login",
            json={"identifier": "phase6operator", "password": "operator-integration-password"},
        ).status_code == 200
        assert client.get("/api/v1/events").status_code == 200
        assert client.get("/api/v1/engine").status_code == 200
        assert client.get("/api/v1/audit").status_code == 403
        assert client.get("/api/v1/settings").status_code == 403
        assert client.post("/api/v1/devices", json={}).status_code == 403
        client.cookies.clear()
        client.cookies.set("wolt_session", owner_session)

        initial_settings = client.get("/api/v1/settings")
        assert initial_settings.status_code == 200
        assert initial_settings.json()["udp_published_start"] == 40000
        assert initial_settings.json()["udp_published_end"] == 40099
        assert client.put(
            "/api/v1/settings/udp-range",
            json={"udp_port_start": 39999, "udp_port_end": 40020},
        ).status_code == 422
        changed_range = client.put(
            "/api/v1/settings/udp-range",
            json={"udp_port_start": 40010, "udp_port_end": 40020},
        )
        assert changed_range.status_code == 200
        assert changed_range.json()["udp_port_capacity"] == 11

        discovered_key = paramiko.RSAKey.generate(1024)
        discovered_line = (
            f"127.0.0.1 {discovered_key.get_name()} {discovered_key.get_base64()}"
        )
        monkeypatch.setattr(
            FortiGateSSHDriver,
            "discover_host_key",
            lambda *_args, **_kwargs: HostKeyDiscoveryResult(
                status="healthy",
                latency_ms=12,
                reason=None,
                host_key=discovered_line,
                fingerprint="SHA256:test-fingerprint",
                algorithm=discovered_key.get_name(),
                bits=1024,
            ),
        )
        discovery = client.post(
            "/api/v1/devices/discover-host-key",
            json={
                "driver_type": "fortigate_ssh",
                "configuration": {"host": "127.0.0.1", "port": 22},
                "credentials": {"username": "wol-service", "password": "transient-secret"},
            },
        )
        assert discovery.status_code == 200
        assert discovery.json()["host_key"] == discovered_line
        assert discovery.json()["fingerprint"] == "SHA256:test-fingerprint"
        assert "transient-secret" not in discovery.text
        discovery_audit = client.get(
            "/api/v1/audit",
            params={"query": "device.host_key_discovery_tested"},
        )
        assert discovery_audit.status_code == 200
        assert discovery_audit.json()["total"] == 1
        assert "transient-secret" not in discovery_audit.text

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
        assert listener["udp_port"] == 40010
        assert client.put(
            "/api/v1/settings/udp-range",
            json={"udp_port_start": 40011, "udp_port_end": 40020},
        ).status_code == 409

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
