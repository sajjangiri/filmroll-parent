"""Outbound email.

SMTP when a host is configured (Mailpit locally, SES/Postmark in production).
An empty host records the message in ``outbox`` instead, which is how tests
assert on magic links without standing up a mail server.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Outgoing:
    to: str
    subject: str
    body: str


outbox: list[Outgoing] = []


def send(to: str, subject: str, body: str) -> None:
    message = Outgoing(to=to, subject=subject, body=body)
    settings = get_settings()
    if not settings.smtp_host:
        outbox.append(message)
        log.info("mail.captured", to=to, subject=subject)
        return
    _deliver(message)
    log.info("mail.sent", to=to, subject=subject)


def _deliver(message: Outgoing) -> None:
    settings = get_settings()
    envelope = EmailMessage()
    envelope["From"] = settings.smtp_from
    envelope["To"] = message.to
    envelope["Subject"] = message.subject
    envelope.set_content(message.body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(envelope)
