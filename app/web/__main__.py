import logging

import uvicorn
from alembic import command
from alembic.config import Config

from app.web.config import WebConfigError, WebSettings


LOGGER = logging.getLogger("wolt.web")


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        settings = WebSettings.from_env()
    except WebConfigError as exc:
        LOGGER.error("event=web_startup_failed reason=config_error detail=%s", exc)
        return 1

    if settings.auto_migrate:
        alembic_config = Config("/app/alembic.ini")
        alembic_config.set_main_option(
            "sqlalchemy.url", settings.database_url.replace("%", "%%")
        )
        command.upgrade(alembic_config, "head")

    uvicorn.run(
        "app.web.application:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
