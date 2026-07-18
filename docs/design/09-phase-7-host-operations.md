# WOLT — Phase 7 restricted host operations

Status: Implemented; Host Agent installation is an explicit Owner/host-administrator action.

## Delivered scope

- A root-owned, stdlib-only Host Agent installed as a hardened systemd service.
- Authenticated HTTP over a group-restricted Unix socket; no TCP listener.
- No Docker socket, root user, `NET_ADMIN`, or host filesystem mount in the WOLT app.
- Owner-only API and UI for Host operations.
- UFW preview and application for one labelled WOLT UDP rule.
- Safe replacement of only the previously recorded WOLT-managed rule.
- Published UDP envelope updates through `.env.web` followed by controlled app recreation.
- Protection against excluding the database-backed active listener range.
- Docker Hub SemVer release discovery.
- Keyless Sigstore/Cosign verification of the official GitHub release workflow identity.
- Upgrade by immutable verified digest, health verification, automatic rollback, and manual rollback.
- Root-only PostgreSQL custom backup before upgrade and database restoration during rollback.
- Secret-safe database audit events when a host operation starts.
- Atomic `.env.web` edits with a root-only backup; unrelated secrets are preserved.

## Trust boundary

```text
Owner browser
    -> authenticated WOLT API (non-root container)
    -> Bearer token + Unix socket
    -> root-owned allowlisted Host Agent
       -> exact UFW argument list
       -> exact Docker Compose project/files
       -> exact Docker Hub repository
       -> official GitHub Actions signing identity
```

The Host Agent accepts no arbitrary command, path, repository, Compose file, environment
key, or shell string from the UI. Every network value and release tag is validated before
an argument list is passed to `subprocess` with `shell=False`.

## One-time installation

From the WOLT project directory on the Docker host:

```bash
sudo ./scripts/install-host-agent.sh /data/WOLT
```

The installer:

1. Creates the `wolt-agent` system group.
2. Installs the agent under `/opt/wolt-host-agent`.
3. Generates a 256-bit token and stores it in root-only configuration and `.env.web`.
4. Installs and starts `wolt-host-agent.service`.
5. Adds the Unix socket and numeric group through `compose.host-agent.yml`.
6. Recreates only the WOLT app container; PostgreSQL data is untouched.

Signed upgrades also require the official Cosign binary at `/usr/local/bin/cosign`.
Install it from the Sigstore Cosign release page and verify its published checksum before
enabling upgrades. UFW management remains available when Cosign is absent.

## Operations

### UFW only

`Apply UFW only` adds this semantic rule:

```text
allow UDP <published-start>:<published-end> from <PAM-source-IP>
```

Only the rule labelled `WOLT-managed` and recorded in the root-owned state file is replaced.

### Published UDP range

`Apply range & recreate` validates ports `1024–65535`, maximum width 100, containment of
the current active allocation, updates only the two published-range environment keys,
applies UFW, recreates the app with both Compose files, and waits for readiness. Failure
restores the environment and firewall rule before recreating the previous deployment.

### Upgrade

1. Discover SemVer tags from the configured Docker Hub repository.
2. Verify the selected tag with Cosign against:
   - issuer `https://token.actions.githubusercontent.com`;
   - the WOLT `release.yml` workflow identity on a version tag.
3. Extract the signed manifest digest.
4. Pull and deploy `repository@sha256:...`, never a mutable tag.
5. Create a mode-`600` PostgreSQL custom backup before changing the running image.
6. Poll `/api/v1/health/ready` for up to 120 seconds.
7. Restore both the previous database snapshot and image automatically on failure.

## Runbook

```bash
systemctl status wolt-host-agent
journalctl -u wolt-host-agent -n 100 --no-pager
sudo bash -c 'set -a; source /etc/wolt-host-agent.env; set +a; PYTHONPATH=/opt/wolt-host-agent python3 -m host_agent.server --check'
```

Do not print `/etc/wolt-host-agent.env` or `.env.web` into tickets or chat; both contain secrets.

## Verification

- Vue TypeScript and production Vite build.
- Unit tests for command-injection rejection, port bounds, exact UFW argument allowlist,
  root-only atomic environment edits, Unix-socket token authentication, SemVer rejection,
  Cosign identity verification, and immutable digest pinning.
- Existing authentication, operations, observability, SMTP, PostgreSQL migration, and
  integration tests remain green.

## Deferred

- High-availability coordination for multiple WOLT app replicas.
- OS firewall providers other than UFW.
- Approval quorum or scheduled maintenance windows.
- Automatic installation of Cosign; host administrators retain control of that trust binary.
