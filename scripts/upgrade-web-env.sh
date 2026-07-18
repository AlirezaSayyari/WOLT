#!/usr/bin/env bash
set -Eeuo pipefail

readonly ENV_FILE="${WOLT_WEB_ENV_FILE:-.env.web}"

fail() {
    printf '[WOLT] ERROR: %s\n' "$*" >&2
    exit 1
}

command -v openssl >/dev/null 2>&1 || fail "openssl is required to generate secure secrets."
[[ -f "$ENV_FILE" ]] || fail "${ENV_FILE} does not exist; run ./scripts/init-web-env.sh instead."
if grep -q '^WOLT_MASTER_KEY=' "$ENV_FILE"; then
    fail "WOLT_MASTER_KEY is already configured; no changes were made."
fi

umask 077
master_key=$(openssl rand -hex 32)
temporary_file=$(mktemp "${ENV_FILE}.tmp.XXXXXX")
trap 'rm -f "$temporary_file"' EXIT
cp "$ENV_FILE" "$temporary_file"
printf '\n# External encryption key for device credentials. Back up this file securely.\n' >> "$temporary_file"
printf "WOLT_MASTER_KEY='%s'\n" "$master_key" >> "$temporary_file"
chmod 600 "$temporary_file"
mv "$temporary_file" "$ENV_FILE"
trap - EXIT

printf '[WOLT] Added a new encryption master key to %s.\n' "$ENV_FILE"
printf '[WOLT] Existing settings were preserved and the file mode is now 600.\n'
printf '[WOLT] Back up this file securely; losing WOLT_MASTER_KEY makes stored device credentials unrecoverable.\n'
