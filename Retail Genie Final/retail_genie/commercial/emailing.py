"""SMTP delivery for authorized commercial documents."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


class CommercialEmailError(RuntimeError):
    """An expected mail-delivery or configuration failure."""


def send_commercial_email(*, recipient: str, subject: str, html_body: str) -> None:
    """Send a commercial document summary using explicitly configured SMTP.

    The document is delivered as HTML email content, avoiding a dependency on a
    PDF renderer while remaining printable or savable as PDF from the recipient's
    mail client. No message is silently accepted when SMTP is not configured.
    """
    config = current_app.config
    host = str(config.get("SMTP_HOST") or "").strip()
    sender = str(config.get("SMTP_SENDER") or "").strip()
    if not host or not sender:
        raise CommercialEmailError("Commercial email is not configured. Set SMTP_HOST and SMTP_SENDER.")

    use_ssl = bool(config.get("SMTP_USE_SSL", False))
    use_starttls = bool(config.get("SMTP_USE_TLS", True))
    if use_ssl and use_starttls:
        raise CommercialEmailError("SMTP_USE_SSL and SMTP_USE_TLS cannot both be enabled.")

    message = EmailMessage()
    message["To"] = recipient
    message["From"] = sender
    message["Subject"] = subject
    message.set_content("This message contains a Retail Genie commercial document. View the HTML version to read and print it.")
    message.add_alternative(html_body, subtype="html")

    timeout = max(1, min(int(config.get("SMTP_TIMEOUT_SECONDS", 15)), 60))
    username = str(config.get("SMTP_USERNAME") or "").strip()
    password = str(config.get("SMTP_PASSWORD") or "")
    try:
        if use_ssl:
            client = smtplib.SMTP_SSL(
                host,
                int(config.get("SMTP_PORT", 465)),
                timeout=timeout,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(host, int(config.get("SMTP_PORT", 587)), timeout=timeout)
        with client:
            client.ehlo()
            if use_starttls:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if username:
                client.login(username, password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError) as error:
        raise CommercialEmailError("The mail server could not deliver this document.") from error
