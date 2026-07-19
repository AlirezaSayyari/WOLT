import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path


LOGGER = logging.getLogger("wolt.smtp")


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
    def __init__(
        self,
        timeout: float = 10,
        ca_file: str | Path | None = None,
    ) -> None:
        self.timeout = timeout
        self.ca_file = Path(ca_file) if ca_file else None

    def _tls_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context()
        if self.ca_file is not None:
            context.load_verify_locations(cafile=self.ca_file)
        return context

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
        client: smtplib.SMTP
        context: ssl.SSLContext | None = None
        stage = "connect"
        try:
            # Plain SMTP deliberately avoids TLS context creation and certificate
            # loading. This supports IP-restricted internal relays on ports such
            # as 25 or 587 without weakening verification for TLS modes.
            if configuration.security != "none":
                stage = "tls_context"
                context = self._tls_context()
                stage = "connect"
            if configuration.security == "tls":
                assert context is not None
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
                    assert context is not None
                    stage = "starttls"
                    client.starttls(context=context)
                if configuration.username:
                    stage = "authenticate"
                    client.login(configuration.username, configuration.password)
                stage = "send"
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            if isinstance(exc, ssl.SSLCertVerificationError):
                reason = "certificate_verification_failed"
            elif isinstance(exc, smtplib.SMTPAuthenticationError):
                reason = "authentication_failed"
            elif (
                isinstance(exc, smtplib.SMTPNotSupportedError)
                and stage == "authenticate"
            ):
                reason = "authentication_method_unsupported"
            elif isinstance(exc, smtplib.SMTPRecipientsRefused):
                reason = "recipient_refused"
            elif isinstance(exc, OSError):
                reason = "connection_failed"
            else:
                reason = "smtp_or_network_error"
            LOGGER.error(
                "event=smtp_delivery_failed reason=%s stage=%s "
                "exception_type=%s host=%s port=%s security=%s custom_ca=%s",
                reason,
                stage,
                type(exc).__name__,
                configuration.host.replace("\r", " ").replace("\n", " "),
                configuration.port,
                configuration.security,
                self.ca_file is not None,
            )
            raise EmailDeliveryError("smtp_delivery_failed") from exc
