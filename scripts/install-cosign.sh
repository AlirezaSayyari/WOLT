#!/usr/bin/env bash
set -Eeuo pipefail

readonly COSIGN_VERSION="v3.1.2"
readonly COSIGN_AMD64_SHA256="f7622ed3cf22e55e1ae6377c080979ff77a22da9981c11df222a2e444991e7cf"
readonly COSIGN_ARM64_SHA256="90e7ae0b5dfd60f20816b52c012addf7fc055ebcc7bea4ce81c428ca8518c302"

fail() { printf '[WOLT] ERROR: %s\n' "$*" >&2; exit 1; }
[[ "${EUID}" -eq 0 ]] || fail "Run this installer as root."

for command in curl sha256sum install; do
    command -v "$command" >/dev/null 2>&1 || fail "Required command not found: $command"
done

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
    *) fail "Unsupported architecture: $architecture" ;;
esac

temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
curl --fail --location --silent --show-error \
    "https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/${asset}" \
    --output "$temporary"
printf '%s  %s\n' "$checksum" "$temporary" | sha256sum --check --status \
    || fail "Cosign checksum verification failed"
install -m 0755 "$temporary" /usr/local/bin/cosign
/usr/local/bin/cosign version
