# Changelog

All notable changes follow Keep a Changelog and semantic versioning.

## [Unreleased]

### Added

- Phase 2 web foundation with a FastAPI management API and responsive Vue 3 shell.
- PostgreSQL 18 reference deployment, SQLAlchemy persistence models, and Alembic migrations.
- Liveness, readiness, setup-status, and system-information endpoints.
- Dark/light theme support and an operational dashboard foundation based on the approved design.

### Changed

- The unified image now contains web assets and database tooling while retaining headless mode as its default command.
- CI validates the Vue production build, Python tests, production image, and PostgreSQL migration drift.

## [0.1.0] - 2026-07-17

### Added

- Validated headless MVP for Guacamole-to-FortiGate Wake-on-LAN translation.
- Strict magic-packet parsing, source allow-listing, rate limiting, and host-key checking.
- Non-root container, Docker Compose deployment, tests, CI, and tagged Docker Hub release workflow.
