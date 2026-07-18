from pathlib import Path

from fastapi.testclient import TestClient

from app.web.application import create_app
from app.web.config import WebSettings


class FakeDatabase:
    def __init__(self, *, ready: bool = True, schema: bool = True, owner: bool = False) -> None:
        self.ready = ready
        self.schema = schema
        self.owner = owner
        self.disposed = False

    def is_ready(self) -> bool:
        return self.ready

    def schema_is_ready(self) -> bool:
        return self.schema

    def schema_revision(self) -> str | None:
        return "20260718_05" if self.schema else None

    def owner_exists(self) -> bool:
        return self.owner

    def dispose(self) -> None:
        self.disposed = True


def settings(static_dir: Path) -> WebSettings:
    return WebSettings(
        database_url="postgresql+psycopg://wolt:secret@postgres/wolt",
        environment="test",
        static_dir=static_dir,
    )


def test_liveness_does_not_depend_on_database(tmp_path: Path) -> None:
    database = FakeDatabase(ready=False, schema=False)
    app = create_app(settings(tmp_path), database)

    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert database.disposed is True


def test_readiness_reports_migration_required(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path), FakeDatabase(ready=True, schema=False))

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "migration_required"}


def test_system_info_reports_build_and_schema_metadata(tmp_path: Path) -> None:
    configured = settings(tmp_path)
    app = create_app(configured, FakeDatabase())

    with TestClient(app) as client:
        response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    assert response.json()["version"] == "v1.0.0-dev"
    assert response.json()["commit_sha"] == "local"
    assert response.json()["schema_revision"] == "20260718_05"


def test_setup_status_requires_first_owner(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path), FakeDatabase(owner=False))

    with TestClient(app) as client:
        response = client.get("/api/v1/setup/status")

    assert response.status_code == 200
    assert response.json() == {
        "database_ready": True,
        "schema_ready": True,
        "setup_required": True,
        "bootstrap_configured": False,
        "master_key_configured": False,
    }


def test_spa_fallback_serves_index(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<main>WOLT</main>", encoding="utf-8")
    app = create_app(settings(tmp_path), FakeDatabase())

    with TestClient(app) as client:
        response = client.get("/listeners")

    assert response.status_code == 200
    assert "WOLT" in response.text


def test_missing_web_assets_return_safe_error(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path), FakeDatabase())

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 503
    assert response.json() == {"detail": "Web assets are not installed"}


def test_unknown_api_route_does_not_fall_back_to_spa(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<main>WOLT</main>", encoding="utf-8")
    app = create_app(settings(tmp_path), FakeDatabase())

    with TestClient(app) as client:
        response = client.get("/api/v1/not-a-route")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}
