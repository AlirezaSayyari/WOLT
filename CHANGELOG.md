# Changelog

All notable changes follow Keep a Changelog and semantic versioning.

## [Unreleased]

### Added

- Phase 2 web foundation with a FastAPI management API and responsive Vue 3 shell.
- PostgreSQL 18 reference deployment, SQLAlchemy persistence models, and Alembic migrations.
- Liveness, readiness, setup-status, and system-information endpoints.
- Dark/light theme support and an operational dashboard foundation based on the approved design.
- First-run Owner setup with a one-time offline recovery code.
- Argon2id password hashing, opaque server-side sessions, login/logout, and recovery APIs.
- Vue Router navigation, bundled Lucide icons, functional account controls, and an architecture guide.
- Secure web-environment initializer that generates database and first-run secrets without manual editing.
- Phase 4 FortiGate SSH driver registry and encrypted edge-device credential storage.
- Device and listener CRUD, automatic UDP port allocation, pinned host-key validation, and connection tests.
- In-process engine reconciliation with pause/resume controls and database-backed wake outcomes.
- Phase 5 wake-event explorer with filters, pagination, correlation details, and CSV export.
- Real 24-hour dashboard metrics, outcome series, device health, and recent event activity.
- Searchable administrative audit trail containing secret-safe change records.
- Configurable event/audit retention with PostgreSQL-locked hourly and on-demand cleanup.

### Changed

- The unified image now contains web assets and database tooling while retaining headless mode as its default command.
- CI validates the Vue production build, Python tests, production image, and PostgreSQL migration drift.
- CI exercises the complete authentication lifecycle against PostgreSQL.

### Fixed

- Database passwords containing URL-reserved characters such as `@`, `:`, `/`, or `?` are encoded safely.

## [0.1.0] - 2026-07-17

### Added

- Validated headless MVP for Guacamole-to-FortiGate Wake-on-LAN translation.
- Strict magic-packet parsing, source allow-listing, rate limiting, and host-key checking.
- Non-root container, Docker Compose deployment, tests, CI, and tagged Docker Hub release workflow.
