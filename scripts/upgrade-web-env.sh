#!/usr/bin/env bash
set -Eeuo pipefail

readonly ENV_FILE="${WOLT_WEB_ENV_FILE:-.env.web}"

fail() {
    printf '[WOLT] ERROR: %s\n' "$*" >&2
    exit 1
}

[[ -f "$ENV_FILE" ]] || fail "${ENV_FILE} does not exist; run ./scripts/init-web-env.sh instead."

needs_master_key=false
grep -q '^WOLT_MASTER_KEY=' "$ENV_FILE" || needs_master_key=true
needs_udp_start=false
grep -q '^WOLT_UDP_PUBLISHED_START=' "$ENV_FILE" || needs_udp_start=true
needs_udp_end=false
grep -q '^WOLT_UDP_PUBLISHED_END=' "$ENV_FILE" || needs_udp_end=true

if [[ "$needs_master_key" == false && "$needs_udp_start" == false && "$needs_udp_end" == false ]]; then
    fail "Web environment is already up to date; no changes were made."
fi

if [[ "$needs_master_key" == true ]]; then
    command -v openssl >/dev/null 2>&1 || fail "openssl is required to generate secure secrets."
fi

umask 077
temporary_file=$(mktemp "${ENV_FILE}.tmp.XXXXXX")
trap 'rm -f "$temporary_file"' EXIT
cp "$ENV_FILE" "$temporary_file"
if [[ "$needs_master_key" == true ]]; then
    master_key=$(openssl rand -hex 32)
    printf '\n# External encryption key for device credentials. Back up this file securely.\n' >> "$temporary_file"
    printf "WOLT_MASTER_KEY='%s'\n" "$master_key" >> "$temporary_file"
fi
if [[ "$needs_udp_start" == true || "$needs_udp_end" == true ]]; then
    printf '\n# UDP ports published by Docker; the active range is managed in the UI.\n' >> "$temporary_file"
    [[ "$needs_udp_start" == false ]] || printf 'WOLT_UDP_PUBLISHED_START=40000\n' >> "$temporary_file"
    [[ "$needs_udp_end" == false ]] || printf 'WOLT_UDP_PUBLISHED_END=40099\n' >> "$temporary_file"
fi
chmod 600 "$temporary_file"
mv "$temporary_file" "$ENV_FILE"
trap - EXIT

printf '[WOLT] Added missing Phase 5.1 environment settings to %s.\n' "$ENV_FILE"
printf '[WOLT] Existing settings were preserved and the file mode is now 600.\n'
if [[ "$needs_master_key" == true ]]; then
    printf '[WOLT] Back up this file securely; losing WOLT_MASTER_KEY makes stored device credentials unrecoverable.\n'
fi
