from email.message import EmailMessage

from app.infrastructure.email import SmtpConfiguration, SmtpMailer


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
