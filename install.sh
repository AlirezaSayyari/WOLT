#!/usr/bin/env bash
set -Eeuo pipefail

readonly WOLT_RELEASE_VERSION="${WOLT_VERSION:-1.1.2}"
readonly WOLT_IMAGE_REPOSITORY="${WOLT_IMAGE_REPOSITORY:-alirezasayyari/wolt}"
readonly WOLT_INSTALL_DIR_DEFAULT="${WOLT_INSTALL_DIR:-/data/WOLT}"
readonly COSIGN_VERSION="v3.1.2"
readonly COSIGN_AMD64_SHA256="f7622ed3cf22e55e1ae6377c080979ff77a22da9981c11df222a2e444991e7cf"
readonly COSIGN_ARM64_SHA256="90e7ae0b5dfd60f20816b52c012addf7fc055ebcc7bea4ce81c428ca8518c302"
readonly SIGNING_IDENTITY='^https://github.com/AlirezaSayyari/WOLT/.github/workflows/release.yml@refs/tags/v[0-9]+\.[0-9]+\.[0-9]+.*$'
readonly SIGNING_ISSUER='https://token.actions.githubusercontent.com'

INSTALL_DIR="$WOLT_INSTALL_DIR_DEFAULT"
UPGRADE_EXISTING=false
STAGING_DIR=""
VERIFY_OUTPUT=""
SOURCE_CONTAINER=""

log() { printf '[WOLT] %s\n' "$*"; }
fail() { printf '[WOLT] ERROR: %s\n' "$*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"; }

cleanup() {
    if [[ -n "$SOURCE_CONTAINER" ]]; then
        docker rm -f "$SOURCE_CONTAINER" >/dev/null 2>&1 || true
    fi
    [[ -z "$STAGING_DIR" ]] || rm -rf "$STAGING_DIR"
    [[ -z "$VERIFY_OUTPUT" ]] || rm -f "$VERIFY_OUTPUT"
}
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-dir)
            [[ $# -ge 2 ]] || fail "--install-dir requires a path"
            INSTALL_DIR="$2"
            shift 2
            ;;
        --version)
            printf '%s\n' "$WOLT_RELEASE_VERSION"
            exit 0
            ;;
        --upgrade-existing)
            UPGRADE_EXISTING=true
            shift
            ;;
        *) fail "Unknown argument: $1" ;;
    esac
done

[[ "${EUID}" -eq 0 ]] || fail "Run this installer as root (curl ... | sudo bash)."
[[ "$INSTALL_DIR" = /* ]] || fail "The installation directory must be absolute."
[[ ! "$INSTALL_DIR" =~ [[:space:]] ]] || fail "The installation directory must not contain whitespace."
require_command curl
require_command docker
require_command openssl
require_command python3
require_command sha256sum
require_command install
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."

install_cosign() {
    if [[ -x /usr/local/bin/cosign ]]; then
        log "Using existing Cosign at /usr/local/bin/cosign"
        return
    fi
    local architecture asset checksum temporary
    architecture="$(uname -m)"
    case "$architecture" in
        x86_64|amd64)
            asset="cosign-linux-amd64"
            checksum="$COSIGN_AMD64_SHA256"
            ;;
        aarch64|arm64)
            asset="cosign-linux-arm64"
            checksum="$COSIGN_ARM64_SHA256"
            ;;
        *) fail "Unsupported architecture for automatic Cosign installation: $architecture" ;;
    esac
    temporary="$(mktemp)"
    log "Downloading Cosign ${COSIGN_VERSION} for ${architecture}"
    curl --fail --location --silent --show-error \
        "https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/${asset}" \
        --output "$temporary"
    printf '%s  %s\n' "$checksum" "$temporary" | sha256sum --check --status \
        || fail "Cosign checksum verification failed"
    install -m 0755 "$temporary" /usr/local/bin/cosign
    rm -f "$temporary"
    /usr/local/bin/cosign version >/dev/null
}

if [[ -e "$INSTALL_DIR" ]]; then
    [[ -d "$INSTALL_DIR" ]] || fail "${INSTALL_DIR} exists and is not a directory."
    if [[ -e "$INSTALL_DIR/.env.web" ]]; then
        [[ "$UPGRADE_EXISTING" == true ]] \
            || fail "${INSTALL_DIR}/.env.web already exists; pass --upgrade-existing for the one-time v1.1 migration."
    else
        [[ -z "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]] \
            || fail "${INSTALL_DIR} is not empty; choose an empty directory."
    fi
else
    install -d -m 0750 "$INSTALL_DIR"
fi

install_cosign

TAGGED_IMAGE="${WOLT_IMAGE_REPOSITORY}:v${WOLT_RELEASE_VERSION}"
log "Pulling ${TAGGED_IMAGE}"
docker pull "$TAGGED_IMAGE"

VERIFY_OUTPUT="$(mktemp)"
log "Verifying the official WOLT release signature"
/usr/local/bin/cosign verify --output json \
    --certificate-identity-regexp "$SIGNING_IDENTITY" \
    --certificate-oidc-issuer "$SIGNING_ISSUER" \
    "$TAGGED_IMAGE" > "$VERIFY_OUTPUT"

DIGEST="$(python3 - "$VERIFY_OUTPUT" <<'PY'
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    entries = json.load(stream)
digest = entries[0]["critical"]["image"]["docker-manifest-digest"]
if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(digest)):
    raise SystemExit("invalid verified image digest")
print(digest)
PY
)"
PINNED_IMAGE="${WOLT_IMAGE_REPOSITORY}@${DIGEST}"

STAGING_DIR="$(mktemp -d)"
SOURCE_CONTAINER="$(docker create "$PINNED_IMAGE" /bin/true)"
docker cp "${SOURCE_CONTAINER}:/opt/wolt-runtime/." "$STAGING_DIR"
docker rm -f "$SOURCE_CONTAINER" >/dev/null
SOURCE_CONTAINER=""

[[ -f "$STAGING_DIR/VERSION" ]] || fail "The signed image does not contain WOLT runtime assets."
[[ "$(tr -d '\r\n' < "$STAGING_DIR/VERSION")" == "v${WOLT_RELEASE_VERSION}" ]] \
    || fail "Runtime bundle version does not match the requested release."

log "Installing the minimal runtime into ${INSTALL_DIR}"
if [[ "$UPGRADE_EXISTING" == true ]]; then
    bootstrap_backup="/var/lib/wolt-agent/runtime-backups/bootstrap-$(date +%s)"
    install -d -m 0700 "$bootstrap_backup"
    for existing in compose.web.yml compose.host-agent.yml VERSION; do
        [[ ! -f "$INSTALL_DIR/$existing" ]] || cp -p "$INSTALL_DIR/$existing" "$bootstrap_backup/$existing"
    done
    [[ ! -d "$INSTALL_DIR/runtime" ]] || cp -a "$INSTALL_DIR/runtime" "$bootstrap_backup/runtime"
    log "Existing managed runtime backed up to ${bootstrap_backup}"
fi
install -m 0644 "$STAGING_DIR/compose.web.yml" "$INSTALL_DIR/compose.web.yml"
install -m 0644 "$STAGING_DIR/compose.host-agent.yml" "$INSTALL_DIR/compose.host-agent.yml"
install -m 0644 "$STAGING_DIR/VERSION" "$INSTALL_DIR/VERSION"
install -d -m 0755 "$INSTALL_DIR/certs"
install -d -m 0750 "$INSTALL_DIR/runtime/scripts" "$INSTALL_DIR/runtime/host_agent"
install -m 0755 "$STAGING_DIR/scripts/init-web-env.sh" "$INSTALL_DIR/runtime/scripts/init-web-env.sh"
install -m 0755 "$STAGING_DIR/scripts/install-cosign.sh" "$INSTALL_DIR/runtime/scripts/install-cosign.sh"
install -m 0755 "$STAGING_DIR/scripts/install-host-agent.sh" "$INSTALL_DIR/runtime/scripts/install-host-agent.sh"
install -m 0644 "$STAGING_DIR/host_agent/__init__.py" "$INSTALL_DIR/runtime/host_agent/__init__.py"
install -m 0644 "$STAGING_DIR/host_agent/server.py" "$INSTALL_DIR/runtime/host_agent/server.py"

if [[ ! -f "$INSTALL_DIR/.env.web" ]]; then
    WOLT_WEB_ENV_FILE="$INSTALL_DIR/.env.web" \
        "$INSTALL_DIR/runtime/scripts/init-web-env.sh"
fi

upsert_env() {
    local key="$1" value="$2" temporary
    temporary="$(mktemp)"
    awk -v key="$key" -v value="$value" '
        BEGIN { found=0 }
        $0 ~ "^" key "=" { print key "='\''" value "'\''"; found=1; next }
        { print }
        END { if (!found) print key "='\''" value "'\''" }
    ' "$INSTALL_DIR/.env.web" > "$temporary"
    install -m 0600 "$temporary" "$INSTALL_DIR/.env.web"
    rm -f "$temporary"
}
upsert_env WOLT_IMAGE "$PINNED_IMAGE"
upsert_env WOLT_VERSION "v${WOLT_RELEASE_VERSION}"
chmod 0600 "$INSTALL_DIR/.env.web"

docker compose --project-directory "$INSTALL_DIR" \
    --env-file "$INSTALL_DIR/.env.web" \
    -f "$INSTALL_DIR/compose.web.yml" pull postgres

"$INSTALL_DIR/runtime/scripts/install-host-agent.sh" "$INSTALL_DIR"

log "Installation complete. Open http://WOLT_HOST:8080 and enter the first-run token printed above."
log "Runtime files: ${INSTALL_DIR}; persistent database: Docker volume; upgrade backups: /var/lib/wolt-agent/backups."
log "Back up ${INSTALL_DIR}/.env.web securely; WOLT_MASTER_KEY cannot be recovered from PostgreSQL."
