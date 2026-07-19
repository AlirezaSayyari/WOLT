from email.message import EmailMessage
import logging
import ssl

import pytest

from app.infrastructure.email import EmailDeliveryError, SmtpConfiguration, SmtpMailer


def test_smtp_mailer_uses_starttls_login_and_safe_message(monkeypatch) -> None:
    actions: list[object] = []

    class FakeClient:
        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            actions.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def starttls(self, *, context: object) -> None:
            actions.append(("starttls", context is not None))

        def login(self, username: str, password: str) -> None:
            actions.append(("login", username, password))

        def send_message(self, message: EmailMessage) -> None:
            actions.append(("send", message["To"], message["Subject"], message.get_content()))

    monkeypatch.setattr("smtplib.SMTP", FakeClient)
    SmtpMailer(timeout=4).send(
        SmtpConfiguration(
            host="smtp.example.com", port=587, security="starttls",
            username="mailer", password="secret", from_email="wolt@example.com",
            from_name="WOLT",
        ),
        recipient="owner@example.com", subject="Test\r\nInjected: no", text="hello",
    )

    assert actions[0] == ("connect", "smtp.example.com", 587, 4)
    assert actions[1][0] == "starttls"
    assert actions[2] == ("login", "mailer", "secret")
    assert actions[3][1:3] == ("owner@example.com", "Test  Injected: no")


def test_smtp_mailer_loads_custom_ca_file(monkeypatch, tmp_path) -> None:
    ca_file = tmp_path / "internal-ca.pem"
    ca_file.write_text("test CA", encoding="utf-8")
    loaded: list[object] = []

    class FakeContext:
        def load_verify_locations(self, *, cafile: object) -> None:
            loaded.append(cafile)

    monkeypatch.setattr("ssl.create_default_context", FakeContext)
    mailer = SmtpMailer(ca_file=ca_file)

    assert mailer._tls_context().__class__ is FakeContext
    assert loaded == [ca_file]


def test_smtp_mailer_none_on_port_587_skips_tls_and_uses_login(monkeypatch) -> None:
    actions: list[object] = []

    class FakeClient:
        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            actions.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def login(self, username: str, password: str) -> None:
            actions.append(("login", username, password))

        def send_message(self, message: EmailMessage) -> None:
            actions.append(("send", message["To"]))

    def fail_if_tls_context_is_created() -> None:
        raise AssertionError("plain SMTP must not create a TLS context")

    monkeypatch.setattr("smtplib.SMTP", FakeClient)
    monkeypatch.setattr("ssl.create_default_context", fail_if_tls_context_is_created)

    SmtpMailer(timeout=4, ca_file="/missing/internal-ca.pem").send(
        SmtpConfiguration(
            host="relay.internal.example", port=587, security="none",
            username="mailer", password="secret", from_email="wolt@example.com",
            from_name="WOLT",
        ),
        recipient="owner@example.com", subject="test", text="test",
    )

    assert actions == [
        ("connect", "relay.internal.example", 587, 4),
        ("login", "mailer", "secret"),
        ("send", "owner@example.com"),
    ]


def test_smtp_mailer_logs_safe_certificate_failure(monkeypatch, caplog) -> None:
    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def starttls(self, *, context: object) -> None:
            raise ssl.SSLCertVerificationError("unable to get local issuer certificate")

    monkeypatch.setattr("smtplib.SMTP", FakeClient)
    configuration = SmtpConfiguration(
        host="mail.internal.example", port=587, security="starttls",
        username="private-user", password="private-password",
        from_email="wolt@example.com", from_name="WOLT",
    )

    with caplog.at_level(logging.ERROR, logger="wolt.smtp"):
        with pytest.raises(EmailDeliveryError):
            SmtpMailer().send(
                configuration,
                recipient="private-recipient@example.com",
                subject="test",
                text="test",
            )

    assert "reason=certificate_verification_failed" in caplog.text
    assert "stage=starttls" in caplog.text
    assert "private-password" not in caplog.text
    assert "private-user" not in caplog.text
    assert "private-recipient" not in caplog.text
