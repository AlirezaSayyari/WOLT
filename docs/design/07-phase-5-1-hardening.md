# WOLT — Phase 5.1 configuration and UI hardening

Status: Implemented for acceptance on the web foundation Draft PR.

## Delivered scope

- Separate Docker-published UDP envelope and database-backed active allocation range.
- Published envelope configuration through `WOLT_UDP_PUBLISHED_START` and
  `WOLT_UDP_PUBLISHED_END`, defaulting to `40000–40099`.
- Authenticated Settings workflow for changing the active range without editing YAML.
- Range validation across Pydantic, application rules, and PostgreSQL constraints:
  ports `1024–65535`, ordered bounds, at most 100 ports, containment in the published
  envelope, and protection for existing listener mappings.
- Engine reconciliation and secret-safe audit recording after a successful range change.
- Active-range use in automatic allocation, manual listener validation, Listener UI,
  and Dashboard UI.
- Runtime image version, commit SHA, build date, environment, and actual Alembic revision.
- Release workflow build arguments for immutable build metadata.
- WOLT SVG favicon and route-aware browser titles.
- FortiGate least-privilege guidance for CLI Execute, Custom Network Group, Packet Capture
  Read/Write, and VDOM-scoped accounts.
- Server-side SSH host-key discovery during FortiGate creation, including SHA-256
  fingerprint confirmation, credential testing, automatic pinning, and secret-safe audit.
- Readability pass increasing operational table, form, navigation, status, and helper text
  sizes and correcting panel/table padding in desktop and responsive layouts.

## Security boundary

- The application cannot publish new host ports at runtime. The active range must remain
  within the container-created deployment envelope.
- The application container retains no Docker socket, host firewall capability, or root access.
- Expanding the published envelope requires an explicit Compose recreation until the restricted
  Host Agent planned for Phase 7 exists.
- FortiGate guidance recommends a working-VDOM scope and explicitly rejects `super_admin`.

## API changes

- `PUT /api/v1/settings/udp-range` updates the active allocation range.
- `POST /api/v1/devices/discover-host-key` discovers, fingerprints, and authentication-tests
  a candidate SSH device without storing its credential.
- `GET /api/v1/settings` now reports published bounds, active capacity, and used ports.
- `GET /api/v1/system/info` now reports version, commit, build date, environment, API version,
  and the live Alembic revision.

## Verification

- Vue TypeScript and Vite production build.
- 73 Python unit and security tests.
- Empty PostgreSQL 18 migration through `20260718_05` and zero Alembic drift.
- Integration test for published-envelope rejection, successful active-range change,
  automatic allocation from the new start, existing-listener protection, UDP ingestion,
  host-key discovery secrecy, audit history, CSV export, and retention cleanup.

## Deferred by design

- Host UFW reconciliation and expansion of published ports from the UI.
- Release discovery, signed image upgrade, health verification, and rollback from the UI.
- Removal of headless v0.1 installation artifacts before the replacement v0.2 installer exists.
