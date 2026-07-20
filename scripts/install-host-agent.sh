#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer as root: sudo ${BASH_SOURCE[0]} /path/to/WOLT" >&2
  exit 1
fi

PROJECT_DIR="${1:-$(pwd)}"
PROJECT_DIR="$(realpath "$PROJECT_DIR")"
ENV_FILE="$PROJECT_DIR/.env.web"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(realpath "$SCRIPT_DIR/..")"

if [[ "$PROJECT_DIR" =~ [[:space:]] ]]; then
  echo "The WOLT project path must not contain whitespace because systemd EnvironmentFile values are unquoted." >&2
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/compose.web.yml" || ! -f "$PROJECT_DIR/compose.host-agent.yml" || ! -f "$ENV_FILE" || ! -f "$RUNTIME_DIR/host_agent/server.py" ]]; then
  echo "Project directory must contain compose.web.yml, compose.host-agent.yml, and .env.web" >&2
  exit 1
fi

if [[ ! -x /usr/local/bin/cosign ]]; then
  "$SCRIPT_DIR/install-cosign.sh"
fi

getent group wolt-agent >/dev/null || groupadd --system wolt-agent
AGENT_GID="$(getent group wolt-agent | cut -d: -f3)"
TOKEN="$(awk -F= '$1=="WOLT_HOST_AGENT_TOKEN" {print $2}' "$ENV_FILE" | tail -1 | tr -d "'\"[:space:]")"
if [[ ${#TOKEN} -lt 32 ]]; then
  TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
fi
WEB_PORT="$(awk -F= '$1=="WOLT_WEB_PORT" {print $2}' "$ENV_FILE" | tail -1)"
WEB_PORT="${WEB_PORT:-8080}"

install -d -m 0755 /opt/wolt-host-agent/host_agent
install -m 0644 "$RUNTIME_DIR/host_agent/__init__.py" /opt/wolt-host-agent/host_agent/__init__.py
install -m 0644 "$RUNTIME_DIR/host_agent/server.py" /opt/wolt-host-agent/host_agent/server.py
install -d -m 0700 /var/lib/wolt-agent /var/lib/wolt-agent/home
install -d -m 0750 -o root -g wolt-agent /run/wolt-agent

# UFW serializes all host changes through this shared lock. ProtectSystem=strict
# keeps the rest of /run read-only, so create and expose only the exact lock file.
cat > /etc/tmpfiles.d/wolt-host-agent.conf <<'EOF'
f /run/ufw.lock 0600 root root -
EOF
systemd-tmpfiles --create /etc/tmpfiles.d/wolt-host-agent.conf

cat > /etc/wolt-host-agent.env <<EOF
PYTHONPATH=/opt/wolt-host-agent
HOME=/var/lib/wolt-agent/home
WOLT_HOST_AGENT_TOKEN=$TOKEN
WOLT_HOST_AGENT_GID=$AGENT_GID
WOLT_PROJECT_DIR=$PROJECT_DIR
WOLT_COMPOSE_FILE=$PROJECT_DIR/compose.web.yml
WOLT_HOST_AGENT_COMPOSE_FILE=$PROJECT_DIR/compose.host-agent.yml
WOLT_ENV_FILE=$ENV_FILE
WOLT_RUNTIME_DIR=$PROJECT_DIR/runtime
WOLT_IMAGE_REPOSITORY=alirezasayyari/wolt
WOLT_HEALTH_URL=http://127.0.0.1:$WEB_PORT/api/v1/health/ready
EOF
chmod 0600 /etc/wolt-host-agent.env

cat > /etc/systemd/system/wolt-host-agent.service <<EOF
[Unit]
Description=WOLT restricted host operations agent
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=root
Group=root
EnvironmentFile=/etc/wolt-host-agent.env
ExecStart=/usr/bin/python3 -m host_agent.server
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=$PROJECT_DIR /opt/wolt-host-agent /run/wolt-agent /run/ufw.lock /var/lib/wolt-agent -/etc/ufw -/var/lib/ufw
ProtectHome=yes

[Install]
WantedBy=multi-user.target
EOF

upsert_env() {
  local key="$1" value="$2" temporary
  temporary="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { found=0 }
    $0 ~ "^" key "=" { print key "=" value; found=1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$ENV_FILE" > "$temporary"
  install -m 0600 "$temporary" "$ENV_FILE"
  rm -f "$temporary"
}

upsert_env WOLT_HOST_AGENT_TOKEN "$TOKEN"
upsert_env WOLT_HOST_AGENT_GID "$AGENT_GID"

systemctl daemon-reload
systemctl enable wolt-host-agent.service
systemctl restart wolt-host-agent.service
docker compose --project-directory "$PROJECT_DIR" --env-file "$ENV_FILE" \
  -f "$PROJECT_DIR/compose.web.yml" -f "$PROJECT_DIR/compose.host-agent.yml" \
  up -d --no-build app

echo "WOLT Host Agent installed. Socket: /run/wolt-agent/agent.sock"
echo "The token was written to .env.web and /etc/wolt-host-agent.env; keep both files private."
echo "Cosign verification is ready: $(/usr/local/bin/cosign version 2>/dev/null | head -1)"
