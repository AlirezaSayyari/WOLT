from argon2 import PasswordHasher

from app.application.auth_service import AuthService
from app.web.auth_routes import LoginAttemptLimiter


def test_password_hash_is_argon2id_and_not_plaintext() -> None:
    password = "correct horse battery staple"
    password_hash = PasswordHasher().hash(password)

    assert password not in password_hash
    assert password_hash.startswith("$argon2id$")
    assert PasswordHasher().verify(password_hash, password)


def test_session_token_hash_is_deterministic_and_one_way() -> None:
    token = "private-session-token"

    digest = AuthService._token_hash(token)

    assert digest == AuthService._token_hash(token)
    assert token not in digest
    assert len(digest) == 64


def test_login_attempt_limiter_blocks_after_limit_and_can_clear() -> None:
    limiter = LoginAttemptLimiter(limit=2, window_seconds=300)

    assert limiter.allow("192.0.2.1") is True
    assert limiter.allow("192.0.2.1") is True
    assert limiter.allow("192.0.2.1") is False

    limiter.clear("192.0.2.1")
    assert limiter.allow("192.0.2.1") is True
