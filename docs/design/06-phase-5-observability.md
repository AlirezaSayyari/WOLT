# WOLT — Phase 5 observability delivery

Status: Implemented and locally verified on the web foundation feature branch.

## Delivered scope

- Authenticated wake-event API with outcome, mapping, device, text, and time filters.
- Stable server-side pagination and a CSV export capped at 10,000 matching records.
- CSV formula-injection protection for user-controlled spreadsheet cells.
- Searchable administrative audit trail with actor, action, object, and client metadata.
- Real 24-hour dashboard totals, outcome series, success rate, device health, and recent events.
- Web pages for Events, Audit Trail, and runtime data-policy Settings in dark and light themes.
- Configurable wake-event retention, audit retention, and per-MAC rate-limit duration.
- Hourly retention worker and an on-demand cleanup action protected by a PostgreSQL advisory lock.
- Query indexes for event correlation/source/relationships and common audit dimensions.

## API surface

- `GET /api/v1/dashboard`
- `GET /api/v1/events`
- `GET /api/v1/events/export.csv`
- `GET /api/v1/audit`
- `GET /api/v1/settings`
- `PUT /api/v1/settings/retention`
- `POST /api/v1/settings/retention/run`

All endpoints require an authenticated server-side session. API responses never include device
credentials, encrypted payloads, password hashes, recovery-code hashes, session tokens, or
bootstrap/master secrets.

## Retention behavior

- Wake events default to 90 days and accept a range of 1–3650 days.
- Audit records default to 365 days and accept a range of 30–3650 days.
- Expired login sessions are removed during the same cleanup transaction.
- Each application process wakes hourly, but `pg_try_advisory_lock` permits only one cleanup
  transaction across multiple processes sharing the same PostgreSQL database.
- The Settings page provides a confirmed on-demand run and reports deletion counts.

## Verification completed

- Vue TypeScript production build.
- 65 Python unit/security tests.
- Full Alembic upgrade from an empty PostgreSQL 18 database through `20260718_04`.
- Alembic model/migration drift check.
- PostgreSQL integration flow covering Owner authentication, encrypted device credentials,
  listener creation, real UDP ingestion, persisted failure outcome, dashboard/event/audit APIs,
  CSV export, policy update, retention deletion, and referential deletion behavior.

## Deferred scope

- SMTP delivery and email-based recovery notifications.
- External SQL Server compatibility and deployment profile.
- Multi-instance UDP listener ownership; the Engine Runtime remains single-active-instance.
- Long-term metrics aggregation beyond the operational event-retention window.
