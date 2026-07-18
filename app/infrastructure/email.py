import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage


class EmailDeliveryError(RuntimeError):
    """A safe SMTP failure category suitable for an API response."""


@dataclass(frozen=True)
class SmtpConfiguration:
    host: str
    port: int
    security: str
    username: str
    password: str
    from_email: str
    from_name: str


class SmtpMailer:
    def __init__(self, timeout: float = 10) -> None:
        self.timeout = timeout

    def send(
        self,
        configuration: SmtpConfiguration,
        *,
        recipient: str,
        subject: str,
        text: str,
    ) -> None:
        message = EmailMessage()
        message["Subject"] = subject.replace("\r", " ").replace("\n", " ")
        safe_name = configuration.from_name.replace("\r", " ").replace("\n", " ")
        message["From"] = f"{safe_name} <{configuration.from_email}>"
        message["To"] = recipient
        message.set_content(text)
        context = ssl.create_default_context()
        client: smtplib.SMTP
        try:
            if configuration.security == "tls":
                client = smtplib.SMTP_SSL(
                    configuration.host,
                    configuration.port,
                    timeout=self.timeout,
                    context=context,
                )
            else:
                client = smtplib.SMTP(
                    configuration.host,
                    configuration.port,
                    timeout=self.timeout,
                )
            with client:
                if configuration.security == "starttls":
                    client.starttls(context=context)
                if configuration.username:
                    client.login(configuration.username, configuration.password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("smtp_delivery_failed") from exc
