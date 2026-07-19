# Changelog

All notable changes follow Keep a Changelog and semantic versioning.

## [1.1.0] - 2026-07-20

### Added

- Clone-free one-line installation from the signed Docker image; Git and a source checkout are no longer required on the server.
- A minimal image-embedded host runtime containing Compose definitions, Host Agent code, installers, and an explicit `VERSION` contract.
- Automatic checksum-verified Cosign installation for `linux/amd64` and `linux/arm64` hosts.
- Runtime-aware UI upgrades and rollback, including persistent job results across Host Agent restarts.
- GitHub release assets for the version-matched installer and its SHA-256 checksum.

### Changed

- Production Compose now requires an explicit published image or immutable digest and can no longer fall back to `wolt:dev`.
- Fresh installations pin `WOLT_IMAGE` to the digest verified through the official GitHub release workflow.
- UI upgrades refresh the server-side Compose and Host Agent runtime while preserving `.env.web`, certificates, PostgreSQL data, and backups.
- Docker Hub release discovery now lists canonical semantic-version tags only.

### Fixed

- Upgrades can no longer leave server-side deployment files behind while only replacing the application container.
- Host Agent jobs retain their final result when a successful upgrade restarts the agent service.

## [1.0.1] - 2026-07-19

### Added

- Optional private CA bundle support for SMTP STARTTLS and implicit TLS deployments.

### Fixed

- SMTP failures now emit a credential-safe reason and delivery stage in application logs.
- Plain SMTP now bypasses TLS context and custom-CA loading completely, including on port 587.

## [1.0.0] - 2026-07-18

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
- Phase 5.1 active UDP allocation controls constrained by the Docker-published envelope.
- Image build metadata, database revision visibility, route-aware page titles, and a WOLT favicon.
- FortiGate least-privilege permission guidance in device management.
- Authenticated server-side SSH host-key discovery with fingerprint confirmation and pre-create credential testing.
- Owner-controlled users and sessions with Administrator/Operator role enforcement.
- Encrypted SMTP configuration, delivery testing, email invitations, and email password recovery.
- Restricted Host Agent with Owner-only UFW, published-port, upgrade, and rollback operations.
- Keyless Cosign release signing and digest-pinned upgrade verification.
- Explicit one-Device and one-restricted-service-account-per-VDOM guidance for multi-VDOM
  FortiGate deployments.
- Clear port-to-interface setup contract across PAM, WOLT, SSH, and native UDP/9 delivery.
- FortiOS 7.2, 7.4, and 7.6 compatibility boundary with a safe-shaped account verification command.

### Changed

- The unified image now contains web assets and database tooling while retaining headless mode as its default command.
- CI validates the Vue production build, Python tests, production image, and PostgreSQL migration drift.
- CI exercises the complete authentication lifecycle against PostgreSQL.
- Increased table, form, navigation, and helper-text sizing and spacing for operational readability.
- Invitation and password-reset tokens are hashed, single-use, expiring, and secret-safe in audit history.
- The authenticated web stack replaces the legacy file-based headless deployment as the supported installation path.

### Fixed

- Database passwords containing URL-reserved characters such as `@`, `:`, `/`, or `?` are encoded safely.

## [0.1.0] - 2026-07-17

### Added

- Validated headless MVP for Guacamole-to-FortiGate Wake-on-LAN translation.
- Strict magic-packet parsing, source allow-listing, rate limiting, and host-key checking.
- Non-root container, Docker Compose deployment, tests, CI, and tagged Docker Hub release workflow.
