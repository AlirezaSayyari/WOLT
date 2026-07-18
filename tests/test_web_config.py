from pathlib import Path

import pytest

from app.web.config import WebConfigError, WebSettings


def test_web_settings_require_database_url() -> None:
    with pytest.raises(WebConfigError, match="DATABASE_URL or WOLT_DB_PASSWORD"):
        WebSettings.from_env({})


def test_web_settings_parse_explicit_values() -> None:
    settings = WebSettings.from_env(
        {
            "DATABASE_URL": "postgresql+psycopg://wolt:secret@postgres/wolt",
            "WOLT_WEB_HOST": "127.0.0.1",
            "WOLT_WEB_PORT": "9090",
            "WOLT_ENVIRONMENT": "development",
            "WOLT_AUTO_MIGRATE": "yes",
            "WOLT_STATIC_DIR": "/srv/wolt/static",
            "WOLT_BOOTSTRAP_TOKEN": "bootstrap-test-token",
            "WOLT_MASTER_KEY": "ab" * 32,
            "WOLT_SESSION_SECURE": "true",
            "WOLT_SESSION_HOURS": "24",
            "WOLT_UDP_PUBLISHED_START": "41000",
            "WOLT_UDP_PUBLISHED_END": "41049",
            "WOLT_VERSION": "v0.2.0-test",
            "WOLT_COMMIT_SHA": "abc123",
            "WOLT_BUILD_DATE": "2026-07-18T12:00:00Z",
        }
    )

    assert settings.host == "127.0.0.1"
    assert settings.port == 9090
    assert settings.environment == "development"
    assert settings.auto_migrate is True
    assert settings.static_dir == Path("/srv/wolt/static")
    assert settings.bootstrap_token == "bootstrap-test-token"
    assert settings.master_key == "ab" * 32
    assert settings.session_secure is True
    assert settings.session_hours == 24
    assert settings.udp_published_start == 41000
    assert settings.udp_published_end == 41049
    assert settings.version == "v0.2.0-test"
    assert settings.commit_sha == "abc123"
    assert settings.build_date == "2026-07-18T12:00:00Z"


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_web_settings_reject_invalid_port(port: str) -> None:
    with pytest.raises(WebConfigError, match="WOLT_WEB_PORT"):
        WebSettings.from_env(
            {
                "DATABASE_URL": "postgresql+psycopg://wolt:secret@postgres/wolt",
                "WOLT_WEB_PORT": port,
            }
        )


def test_web_settings_reject_unsupported_database_driver() -> None:
    with pytest.raises(WebConfigError, match=r"postgresql\+psycopg"):
        WebSettings.from_env({"DATABASE_URL": "sqlite:///wolt.db"})


def test_web_settings_safely_encode_database_password_components() -> None:
    settings = WebSettings.from_env(
        {
            "WOLT_DB_PASSWORD": "P@ss:word/with?symbols",
            "WOLT_DB_HOST": "postgres",
        }
    )

    assert "P%40ss%3Aword%2Fwith%3Fsymbols" in settings.database_url
    assert settings.database_url.endswith("@postgres:5432/wolt")


@pytest.mark.parametrize("hours", ["0", "169", "not-a-number"])
def test_web_settings_reject_invalid_session_lifetime(hours: str) -> None:
    with pytest.raises(WebConfigError, match="WOLT_SESSION_HOURS"):
        WebSettings.from_env(
            {
                "DATABASE_URL": "postgresql+psycopg://wolt:secret@postgres/wolt",
                "WOLT_SESSION_HOURS": hours,
            }
        )


@pytest.mark.parametrize("key", ["not-hex", "ab" * 16, "ab" * 33])
def test_web_settings_reject_invalid_master_key(key: str) -> None:
    with pytest.raises(WebConfigError, match="WOLT_MASTER_KEY"):
        WebSettings.from_env(
            {
                "DATABASE_URL": "postgresql+psycopg://wolt:secret@postgres/wolt",
                "WOLT_MASTER_KEY": key,
            }
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [("1023", "1100"), ("65000", "65536"), ("41000", "40000"), ("40000", "40100")],
)
def test_web_settings_reject_invalid_published_udp_range(start: str, end: str) -> None:
    with pytest.raises(WebConfigError, match="UDP|published UDP"):
        WebSettings.from_env(
            {
                "DATABASE_URL": "postgresql+psycopg://wolt:secret@postgres/wolt",
                "WOLT_UDP_PUBLISHED_START": start,
                "WOLT_UDP_PUBLISHED_END": end,
            }
        )


def test_web_settings_rejects_short_host_agent_token() -> None:
    with pytest.raises(WebConfigError, match="WOLT_HOST_AGENT_TOKEN"):
        WebSettings.from_env(
            {
                "WOLT_DB_PASSWORD": "database-password",
                "WOLT_HOST_AGENT_TOKEN": "short",
            }
        )
