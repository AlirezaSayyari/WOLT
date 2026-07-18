# WOLT — Phase 2 web foundation

Status: Implemented for review on the `feature/phase-2-web-foundation` branch.

## Scope

Phase 2 establishes the deployable foundation for the `v0.2` management product.
It intentionally does not expose incomplete authentication or configuration write
operations.

Delivered:

- a FastAPI API with liveness, readiness, setup-status and system-information routes;
- a responsive Vue 3 and TypeScript application shell matching the approved visual direction;
- light and dark themes with a stored local preference and reduced-motion support;
- SQLAlchemy models for users, devices, credentials, listeners, wake events, audit events,
  application settings and engine state;
- an initial Alembic migration with default UDP range and retention settings;
- a PostgreSQL 18 Compose deployment with persistent storage and health checks;
- a single production image that serves compiled Vue assets from FastAPI;
- CI coverage for frontend compilation, Python tests, production build and migration drift;
- compatibility with the existing headless command and `v0.1.x` configuration.

## Recorded architecture decisions

1. The production Vue bundle is served by the Python application container.
2. PostgreSQL is the only bundled database in this phase.
3. SQL Server remains an external-only target and is enabled only after a compatibility suite exists.
4. Wake-event retention defaults to 90 days; audit retention defaults to 365 days.
5. Processing remains single-instance until listener reconciliation and leader semantics are designed.
6. The web preview starts with the engine paused and no write-capable setup endpoint.

## Deployment boundary

The existing `docker-compose.yml` remains the headless MVP deployment. The web stack
uses `compose.web.yml`; this prevents an in-progress web feature from changing a stable
WOL installation.

```text
Browser :8080 ──> WOLT app ──> PostgreSQL
                      │
               UDP 40000–40099
               (published, engine integration pending)
```

PostgreSQL is not published to the host. TLS termination is intentionally delegated
to an existing reverse proxy in production.

## API boundary

Available endpoints:

```text
GET /api/v1/health/live
GET /api/v1/health/ready
GET /api/v1/setup/status
GET /api/v1/system/info
```

All API responses set `Cache-Control: no-store`. The application adds clickjacking,
content-sniffing and referrer protections. API documentation is available only when
`WOLT_ENVIRONMENT` is not `production`.

## Exit criteria

- Existing headless tests continue to pass.
- Vue type checking and production bundling succeed.
- PostgreSQL starts from an empty volume and Alembic reaches the latest revision.
- Alembic reports no model/migration drift.
- The app container is healthy, non-root, read-only and has no Docker socket.
- The SPA and readiness endpoint are reachable through the published web port.

## Next phase

Phase 3 implements the guarded first-run flow: bootstrap token, initial Owner,
Argon2id password hashing, offline recovery code, sessions, login/logout, and the
corresponding setup/login screens.
