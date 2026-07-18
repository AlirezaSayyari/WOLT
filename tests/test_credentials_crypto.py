import base64

import pytest

from app.infrastructure.crypto import CredentialCipher, CredentialCryptoError


def test_credentials_use_authenticated_encryption() -> None:
    cipher = CredentialCipher("11" * 32)
    encrypted = cipher.encrypt({"username": "wol-service", "password": "top-secret"})

    assert "wol-service" not in encrypted
    assert "top-secret" not in encrypted
    assert cipher.decrypt(encrypted) == {
        "username": "wol-service",
        "password": "top-secret",
    }


def test_credentials_reject_tampered_ciphertext() -> None:
    cipher = CredentialCipher("22" * 32)
    encrypted = cipher.encrypt({"password": "secret"})
    raw = bytearray(base64.urlsafe_b64decode(encrypted))
    raw[-1] ^= 1

    with pytest.raises(CredentialCryptoError, match="credential_decryption_failed"):
        cipher.decrypt(base64.urlsafe_b64encode(raw).decode())


@pytest.mark.parametrize("key", ["", "not-hex", "ab" * 16])
def test_credentials_require_a_32_byte_hex_key(key: str) -> None:
    with pytest.raises(CredentialCryptoError, match="WOLT_MASTER_KEY"):
        CredentialCipher(key)
