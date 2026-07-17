#!/usr/bin/env bash
set -Eeuo pipefail

readonly REPOSITORY_URL="https://github.com/AlirezaSayyari/WOLT.git"
readonly INSTALL_DIR="${WOLT_INSTALL_DIR:-/opt/wolt}"
readonly VERSION="${WOLT_VERSION:-0.1.0}"
readonly IMAGE="alirezasayyari/wolt:${VERSION}"

log() {
    printf '[WOLT] %s\n' "$*"
}

fail() {
    printf '[WOLT] ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

prompt() {
    local variable_name="$1"
    local label="$2"
    local default_value="${3:-}"
    local value

    if [[ -n "$default_value" ]]; then
        printf '%s [%s]: ' "$label" "$default_value" > /dev/tty
    else
        printf '%s: ' "$label" > /dev/tty
    fi
    IFS= read -r value < /dev/tty
    printf -v "$variable_name" '%s' "${value:-$default_value}"
}

quote_env() {
    local value="$1"
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//\$/\$\$}
    printf '"%s"' "$value"
}

[[ "${EUID}" -eq 0 ]] || fail "Run this installer as root (for example: curl ... | sudo bash)."
[[ -r /dev/tty ]] || fail "An interactive terminal is required."

require_command git
require_command docker
require_command ssh-keyscan
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."

log "Installing WOLT ${VERSION} into ${INSTALL_DIR}"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    git -C "$INSTALL_DIR" fetch --tags --force
    git -C "$INSTALL_DIR" checkout --force "v${VERSION}"
elif [[ -e "$INSTALL_DIR" ]]; then
    fail "${INSTALL_DIR} already exists but is not a WOLT Git checkout."
else
    git clone --depth 1 --branch "v${VERSION}" "$REPOSITORY_URL" "$INSTALL_DIR"
fi

prompt FORTIGATE_HOST "FortiGate host or IP"
prompt FORTIGATE_SSH_PORT "FortiGate SSH port" "22"
prompt FORTIGATE_USERNAME "FortiGate username" "wol-service"
printf 'FortiGate password: ' > /dev/tty
IFS= read -r -s FORTIGATE_PASSWORD < /dev/tty
printf '\n' > /dev/tty
prompt GUACAMOLE_ALLOWED_IP "Allowed Guacamole/guacd source IP"
prompt LISTENER_PORT "First WOLT UDP listener port" "40016"
prompt FORTIGATE_INTERFACE "FortiGate interface for this listener" "demo-vlan-16"
prompt GATEWAY_IP "Gateway or broadcast IP for the destination LAN" "198.51.100.94"

[[ "$FORTIGATE_HOST" =~ ^[A-Za-z0-9._:-]+$ ]] || fail "FortiGate host contains unsupported characters."
[[ "$FORTIGATE_SSH_PORT" =~ ^[0-9]+$ ]] || fail "SSH port must be numeric."
(( FORTIGATE_SSH_PORT >= 1 && FORTIGATE_SSH_PORT <= 65535 )) || fail "SSH port is out of range."
[[ -n "$FORTIGATE_USERNAME" ]] || fail "FortiGate username is required."
[[ -n "$FORTIGATE_PASSWORD" ]] || fail "FortiGate password is required."
[[ "$GUACAMOLE_ALLOWED_IP" =~ ^[A-Za-z0-9:.]+$ ]] || fail "Allowed source IP is invalid."
[[ "$LISTENER_PORT" =~ ^[0-9]+$ ]] || fail "Listener port must be numeric."
(( LISTENER_PORT >= 1024 && LISTENER_PORT <= 65535 )) || fail "Listener port must be between 1024 and 65535."
[[ "$FORTIGATE_INTERFACE" =~ ^[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}$ ]] || fail "Interface name is invalid."
[[ "$GATEWAY_IP" =~ ^[A-Za-z0-9:.]+$ ]] || fail "Gateway IP is invalid."

umask 077
mkdir -p "${INSTALL_DIR}/config" "${INSTALL_DIR}/ssh"

cat > "${INSTALL_DIR}/.env" <<EOF
WOLT_IMAGE=${IMAGE}
FORTIGATE_HOST=$(quote_env "$FORTIGATE_HOST")
FORTIGATE_SSH_PORT=${FORTIGATE_SSH_PORT}
FORTIGATE_USERNAME=$(quote_env "$FORTIGATE_USERNAME")
FORTIGATE_PASSWORD=$(quote_env "$FORTIGATE_PASSWORD")
GUACAMOLE_ALLOWED_IP=$(quote_env "$GUACAMOLE_ALLOWED_IP")
SSH_CONNECT_TIMEOUT=5
SSH_COMMAND_TIMEOUT=10
WOL_RATE_LIMIT_SECONDS=30
LOG_LEVEL=INFO
MAPPING_FILE=/app/config/interfaces.yaml
KNOWN_HOSTS_FILE=/home/wolt/.ssh/known_hosts
EOF

cat > "${INSTALL_DIR}/config/interfaces.yaml" <<EOF
listeners:
  "${LISTENER_PORT}":
    interface: "${FORTIGATE_INTERFACE}"
    gateway_ip: "${GATEWAY_IP}"
EOF

known_hosts_tmp=$(mktemp)
trap 'rm -f "$known_hosts_tmp"' EXIT
log "Scanning and pinning the FortiGate SSH host key"
ssh-keyscan -T 5 -p "$FORTIGATE_SSH_PORT" "$FORTIGATE_HOST" > "$known_hosts_tmp" 2>/dev/null \
    || fail "Could not retrieve the FortiGate SSH host key."
[[ -s "$known_hosts_tmp" ]] || fail "FortiGate returned no SSH host key."
install -m 600 "$known_hosts_tmp" "${INSTALL_DIR}/ssh/known_hosts"
chmod 600 "${INSTALL_DIR}/.env"
chmod 644 "${INSTALL_DIR}/config/interfaces.yaml"

log "Pulling ${IMAGE} and starting WOLT"
docker compose \
    --project-directory "$INSTALL_DIR" \
    -f "${INSTALL_DIR}/docker-compose.yml" \
    -f "${INSTALL_DIR}/compose.release.yml" \
    pull
docker compose \
    --project-directory "$INSTALL_DIR" \
    -f "${INSTALL_DIR}/docker-compose.yml" \
    -f "${INSTALL_DIR}/compose.release.yml" \
    up -d

log "Installation complete."
log "View logs: cd ${INSTALL_DIR} && docker compose logs -f wolt"
