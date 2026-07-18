# WOLT — Phase 6 identity and email

Status: Implemented for acceptance on the web foundation Draft PR.

## Delivered scope

- Owner-only user and session administration.
- Administrator and Operator roles with enforced API authorization.
- Email invitations with 24-hour, single-use, hashed tokens.
- Invite acceptance page where recipients choose their own Argon2id password.
- SMTP configuration and real delivery test from the WOLT container.
- STARTTLS, implicit TLS, and explicitly labelled non-TLS transport modes.
- SMTP credentials encrypted with the external `WOLT_MASTER_KEY` and never returned.
- Neutral email password-reset requests, 30-minute single-use tokens, password change,
  and revocation of all existing sessions.
- Owner offline recovery remains available when SMTP is unavailable.
- Protection against disabling or demoting the last enabled Owner.
- Per-IP throttling for public password-reset requests.
- Secret-safe audit records for SMTP changes, invitations, account changes, reset events,
  and session revocation.

## Role boundary

| Capability | Owner | Administrator | Operator |
|---|---:|---:|---:|
| Users, sessions, SMTP | Yes | No | No |
| Devices and listeners write operations | Yes | Yes | No |
| Settings and audit trail | Yes | Yes | No |
| Dashboard, events, device test, engine control | Yes | Yes | Yes |

The backend enforces these rules. Navigation filtering is only a usability layer.

## Security boundary

- Passwords use Argon2id and are never decryptable.
- Invitation/reset tokens contain 256 bits of randomness; only SHA-256 hashes are stored.
- Tokens are single-use and expire server-side.
- Password reset invalidates every active session for that user.
- SMTP passwords use AES-256-GCM authenticated encryption through the external master key.
- Public reset requests always return the same accepted response to prevent account discovery.
- WOLT sends links using the Owner-configured public base URL; production installations should
  use an HTTPS reverse proxy and set that URL to the externally reachable HTTPS origin.

## API changes

```text
GET    /api/v1/users
POST   /api/v1/users/invitations
PUT    /api/v1/users/{id}
POST   /api/v1/users/{id}/revoke-sessions
GET    /api/v1/smtp
PUT    /api/v1/smtp
POST   /api/v1/smtp/test
POST   /api/v1/auth/accept-invitation
POST   /api/v1/auth/password-reset/request
POST   /api/v1/auth/password-reset/complete
```

## Operational flow

1. Owner opens **SMTP**, enters the server and public WOLT URL, and sends a test email.
2. Owner saves and enables the encrypted SMTP configuration.
3. Owner opens **Users & sessions** and sends an Administrator or Operator invitation.
4. The recipient follows the one-time link and sets a password.
5. Owner can later change the role, disable the identity, or revoke every active session.

## Verification

- Vue TypeScript and Vite production build.
- Unit tests for SMTP TLS/login behavior and header sanitation.
- Empty PostgreSQL 18 migration through `20260718_06` with zero Alembic drift.
- PostgreSQL integration coverage for encrypted SMTP storage, invitation secrecy and replay
  rejection, role authorization, last-Owner protection, email reset, password rotation,
  and session revocation.

## Deferred

- Notification rules for wake/device events.
- Enterprise identity federation (OIDC/SAML/LDAP).
- Per-Operator engine-control grants beyond the current role policy.
- Email delivery queue/retry telemetry.
