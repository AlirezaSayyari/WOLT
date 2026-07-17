import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import URL


class WebConfigError(ValueError):
    """Raised when web-mode configuration is invalid."""


def _boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise WebConfigError(f"{name} must be true or false")


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise WebConfigError("WOLT_WEB_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise WebConfigError("WOLT_WEB_PORT must be between 1 and 65535")
    return port


def _database_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise WebConfigError("WOLT_DB_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise WebConfigError("WOLT_DB_PORT must be between 1 and 65535")
    return port


def _session_hours(value: str) -> int:
    try:
        hours = int(value)
    except ValueError as exc:
        raise WebConfigError("WOLT_SESSION_HOURS must be an integer") from exc
    if not 1 <= hours <= 168:
        raise WebConfigError("WOLT_SESSION_HOURS must be between 1 and 168")
    return hours


@dataclass(frozen=True)
class WebSettings:
    database_url: str
    host: str = "0.0.0.0"
    port: int = 8080
    environment: str = "production"
    auto_migrate: bool = False
    static_dir: Path = Path("/app/app/web/static")
    bootstrap_token: str = ""
    session_secure: bool = False
    session_hours: int = 12

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "WebSettings":
        env = dict(os.environ if environ is None else environ)
        database_url = env.get("DATABASE_URL", "").strip()
        if database_url and not database_url.startswith("postgresql+psycopg://"):
            raise WebConfigError("DATABASE_URL must use postgresql+psycopg in this phase")
        if not database_url:
            password = env.get("WOLT_DB_PASSWORD", "")
            if not password:
                raise WebConfigError(
                    "DATABASE_URL or WOLT_DB_PASSWORD is required in web mode"
                )
            database_url = URL.create(
                drivername="postgresql+psycopg",
                username=env.get("WOLT_DB_USER", "wolt"),
                password=password,
                host=env.get("WOLT_DB_HOST", "postgres"),
                port=_database_port(env.get("WOLT_DB_PORT", "5432")),
                database=env.get("WOLT_DB_NAME", "wolt"),
            ).render_as_string(hide_password=False)
        return cls(
            database_url=database_url,
            host=env.get("WOLT_WEB_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_port(env.get("WOLT_WEB_PORT", "8080")),
            environment=env.get("WOLT_ENVIRONMENT", "production").strip() or "production",
            auto_migrate=_boolean(env.get("WOLT_AUTO_MIGRATE", "false"), "WOLT_AUTO_MIGRATE"),
            static_dir=Path(env.get("WOLT_STATIC_DIR", "/app/app/web/static")),
            bootstrap_token=env.get("WOLT_BOOTSTRAP_TOKEN", ""),
            session_secure=_boolean(
                env.get("WOLT_SESSION_SECURE", "false"), "WOLT_SESSION_SECURE"
            ),
            session_hours=_session_hours(env.get("WOLT_SESSION_HOURS", "12")),
        )
