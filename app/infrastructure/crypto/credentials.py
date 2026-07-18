import base64
import hashlib
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


AAD = b"wolt-device-credential-v1"


class CredentialCryptoError(ValueError):
    """Raised when the external credential key or encrypted payload is invalid."""


class CredentialCipher:
    def __init__(self, hex_key: str) -> None:
        try:
            key = bytes.fromhex(hex_key)
        except ValueError as exc:
            raise CredentialCryptoError("WOLT_MASTER_KEY must be hexadecimal") from exc
        if len(key) != 32:
            raise CredentialCryptoError("WOLT_MASTER_KEY must contain 32 random bytes")
        self._cipher = AESGCM(key)
        self.key_id = hashlib.sha256(key).hexdigest()[:16]

    def encrypt(self, values: dict[str, Any]) -> str:
        nonce = os.urandom(12)
        plaintext = json.dumps(
            values, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        encrypted = self._cipher.encrypt(nonce, plaintext, AAD)
        return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")

    def decrypt(self, payload: str) -> dict[str, Any]:
        try:
            raw = base64.urlsafe_b64decode(payload.encode("ascii"))
            result = json.loads(self._cipher.decrypt(raw[:12], raw[12:], AAD))
        except (ValueError, InvalidTag, json.JSONDecodeError) as exc:
            raise CredentialCryptoError("credential_decryption_failed") from exc
        if not isinstance(result, dict):
            raise CredentialCryptoError("credential_payload_invalid")
        return result
