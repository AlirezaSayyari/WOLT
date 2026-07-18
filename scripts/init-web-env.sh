#!/usr/bin/env bash
set -Eeuo pipefail

readonly ENV_FILE="${WOLT_WEB_ENV_FILE:-.env.web}"

fail() {
    printf '[WOLT] ERROR: %s\n' "$*" >&2
    exit 1
}

command -v openssl >/dev/null 2>&1 || fail "openssl is required to generate secure secrets."
[[ ! -e "$ENV_FILE" ]] || fail "${ENV_FILE} already exists; refusing to overwrite secrets."

env_directory=$(dirname "$ENV_FILE")
[[ -d "$env_directory" ]] || fail "Target directory does not exist: ${env_directory}"

umask 077
database_password=$(openssl rand -hex 32)
bootstrap_token=$(openssl rand -hex 32)
master_key=$(openssl rand -hex 32)
temporary_file=$(mktemp "${ENV_FILE}.tmp.XXXXXX")
trap 'rm -f "$temporary_file"' EXIT

cat > "$temporary_file" <<EOF
POSTGRES_PASSWORD='${database_password}'
WOLT_BOOTSTRAP_TOKEN='${bootstrap_token}'
WOLT_MASTER_KEY='${master_key}'
WOLT_WEB_PORT=8080
WOLT_ENVIRONMENT=production
WOLT_AUTO_MIGRATE=true
WOLT_SESSION_SECURE=false
WOLT_SESSION_HOURS=12
EOF

chmod 600 "$temporary_file"
mv "$temporary_file" "$ENV_FILE"
trap - EXIT

printf '\n'
printf '[WOLT] Secure web configuration created: %s (mode 600)\n' "$ENV_FILE"
printf '\n'
printf '==================== FIRST-RUN TOKEN ====================\n'
printf '%s\n' "$bootstrap_token"
printf '=========================================================\n'
printf '\n'
printf '[WOLT] Enter this token on the first-run Setup page.\n'
printf '[WOLT] Keep it private until the Owner account is created.\n'
printf '[WOLT] After setup, store the Recovery Code shown by the UI; that is the long-term recovery secret.\n'
printf '[WOLT] For HTTPS deployments, set WOLT_SESSION_SECURE=true before startup.\n'
