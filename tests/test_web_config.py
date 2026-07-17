from pathlib import Path

import pytest

from app.web.config import WebConfigError, WebSettings


def test_web_settings_require_database_url() -> None:
    with pytest.raises(WebConfigError, match="DATABASE_URL"):
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
        }
    )

    assert settings.host == "127.0.0.1"
    assert settings.port == 9090
    assert settings.environment == "development"
    assert settings.auto_migrate is True
    assert settings.static_dir == Path("/srv/wolt/static")


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
