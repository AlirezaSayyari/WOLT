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


def _udp_port(value: str, name: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise WebConfigError(f"{name} must be an integer") from exc
    if not 1024 <= port <= 65535:
        raise WebConfigError(f"{name} must be between 1024 and 65535")
    return port


def _session_hours(value: str) -> int:
    try:
        hours = int(value)
    except ValueError as exc:
        raise WebConfigError("WOLT_SESSION_HOURS must be an integer") from exc
    if not 1 <= hours <= 168:
        raise WebConfigError("WOLT_SESSION_HOURS must be between 1 and 168")
    return hours


def _master_key(value: str) -> str:
    if not value:
        return ""
    try:
        decoded = bytes.fromhex(value)
    except ValueError as exc:
        raise WebConfigError("WOLT_MASTER_KEY must be hexadecimal") from exc
    if len(decoded) != 32:
        raise WebConfigError("WOLT_MASTER_KEY must contain 32 random bytes")
    return value


def _host_agent_token(value: str) -> str:
    if value and len(value) < 32:
        raise WebConfigError("WOLT_HOST_AGENT_TOKEN must contain at least 32 characters")
    return value


@dataclass(frozen=True)
class WebSettings:
    database_url: str
    host: str = "0.0.0.0"
    port: int = 8080
    environment: str = "production"
    auto_migrate: bool = False
    static_dir: Path = Path("/app/app/web/static")
    bootstrap_token: str = ""
    master_key: str = ""
    session_secure: bool = False
    session_hours: int = 12
    udp_published_start: int = 40000
    udp_published_end: int = 40099
    version: str = "v1.1.2-dev"
    commit_sha: str = "local"
    build_date: str = "unknown"
    host_agent_socket: Path = Path("/run/wolt-agent/agent.sock")
    host_agent_token: str = ""
    smtp_ca_file: Path | None = None

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
        udp_start = _udp_port(
            env.get("WOLT_UDP_PUBLISHED_START", "40000"),
            "WOLT_UDP_PUBLISHED_START",
        )
        udp_end = _udp_port(
            env.get("WOLT_UDP_PUBLISHED_END", "40099"),
            "WOLT_UDP_PUBLISHED_END",
        )
        if udp_start > udp_end:
            raise WebConfigError(
                "WOLT_UDP_PUBLISHED_START must not exceed WOLT_UDP_PUBLISHED_END"
            )
        if udp_end - udp_start + 1 > 100:
            raise WebConfigError("The published UDP range cannot exceed 100 ports")
        smtp_ca_file = env.get("WOLT_SMTP_CA_FILE", "").strip()
        return cls(
            database_url=database_url,
            host=env.get("WOLT_WEB_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_port(env.get("WOLT_WEB_PORT", "8080")),
            environment=env.get("WOLT_ENVIRONMENT", "production").strip() or "production",
            auto_migrate=_boolean(env.get("WOLT_AUTO_MIGRATE", "false"), "WOLT_AUTO_MIGRATE"),
            static_dir=Path(env.get("WOLT_STATIC_DIR", "/app/app/web/static")),
            bootstrap_token=env.get("WOLT_BOOTSTRAP_TOKEN", ""),
            master_key=_master_key(env.get("WOLT_MASTER_KEY", "")),
            session_secure=_boolean(
                env.get("WOLT_SESSION_SECURE", "false"), "WOLT_SESSION_SECURE"
            ),
            session_hours=_session_hours(env.get("WOLT_SESSION_HOURS", "12")),
            udp_published_start=udp_start,
            udp_published_end=udp_end,
            version=env.get("WOLT_VERSION", "v1.1.2-dev").strip() or "v1.1.2-dev",
            commit_sha=env.get("WOLT_COMMIT_SHA", "local").strip() or "local",
            build_date=env.get("WOLT_BUILD_DATE", "unknown").strip() or "unknown",
            host_agent_socket=Path(env.get("WOLT_HOST_AGENT_SOCKET", "/run/wolt-agent/agent.sock")),
            host_agent_token=_host_agent_token(env.get("WOLT_HOST_AGENT_TOKEN", "")),
            smtp_ca_file=Path(smtp_ca_file) if smtp_ca_file else None,
        )
