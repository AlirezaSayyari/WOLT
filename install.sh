#!/usr/bin/env bash
set -Eeuo pipefail

readonly REPOSITORY_URL="https://github.com/AlirezaSayyari/WOLT.git"
readonly INSTALL_DIR="${WOLT_INSTALL_DIR:-/opt/wolt}"
readonly VERSION="${WOLT_VERSION:-1.0.0}"
readonly IMAGE="${WOLT_IMAGE:-alirezasayyari/wolt:v${VERSION}}"

log() { printf '[WOLT] %s\n' "$*"; }
fail() { printf '[WOLT] ERROR: %s\n' "$*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"; }

[[ "${EUID}" -eq 0 ]] || fail "Run this installer as root (for example: curl ... | sudo bash)."
require_command git
require_command docker
require_command openssl
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."

log "Installing WOLT v${VERSION} into ${INSTALL_DIR}"
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    [[ ! -e "${INSTALL_DIR}/.env.web" ]] || fail "${INSTALL_DIR}/.env.web already exists. Use the documented upgrade flow; the installer never overwrites secrets."
    git -C "$INSTALL_DIR" fetch --tags --force
    git -C "$INSTALL_DIR" checkout --force "v${VERSION}"
elif [[ -e "$INSTALL_DIR" ]]; then
    fail "${INSTALL_DIR} already exists. Choose an empty WOLT_INSTALL_DIR or use the upgrade flow."
else
    git clone --depth 1 --branch "v${VERSION}" "$REPOSITORY_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
WOLT_WEB_ENV_FILE="${INSTALL_DIR}/.env.web" ./scripts/init-web-env.sh
printf "WOLT_IMAGE='%s'\nWOLT_VERSION='v%s'\n" "$IMAGE" "$VERSION" >> .env.web
chmod 600 .env.web

log "Pulling signed release image ${IMAGE} and PostgreSQL"
docker compose --env-file .env.web -f compose.web.yml pull
docker compose --env-file .env.web -f compose.web.yml up -d --no-build

log "Installation complete. Open http://WOLT_HOST:8080 and enter the first-run token printed above."
log "Status: cd ${INSTALL_DIR} && docker compose --env-file .env.web -f compose.web.yml ps"
log "Back up ${INSTALL_DIR}/.env.web securely; WOLT_MASTER_KEY cannot be recovered from PostgreSQL."
