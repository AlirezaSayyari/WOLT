import os
from dataclasses import dataclass
from pathlib import Path


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


@dataclass(frozen=True)
class WebSettings:
    database_url: str
    host: str = "0.0.0.0"
    port: int = 8080
    environment: str = "production"
    auto_migrate: bool = False
    static_dir: Path = Path("/app/app/web/static")

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "WebSettings":
        env = dict(os.environ if environ is None else environ)
        database_url = env.get("DATABASE_URL", "").strip()
        if not database_url:
            raise WebConfigError("DATABASE_URL is required in web mode")
        if not database_url.startswith("postgresql+psycopg://"):
            raise WebConfigError("DATABASE_URL must use postgresql+psycopg in this phase")
        return cls(
            database_url=database_url,
            host=env.get("WOLT_WEB_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_port(env.get("WOLT_WEB_PORT", "8080")),
            environment=env.get("WOLT_ENVIRONMENT", "production").strip() or "production",
            auto_migrate=_boolean(env.get("WOLT_AUTO_MIGRATE", "false"), "WOLT_AUTO_MIGRATE"),
            static_dir=Path(env.get("WOLT_STATIC_DIR", "/app/app/web/static")),
        )
