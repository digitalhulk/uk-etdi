"""Email notification stub via SMTP (optional). Configure SMTP_HOST/SMTP_USER/SMTP_PASSWORD/EMAIL_TO env vars."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_email(subject: str, body: str) -> tuple[bool, str]:
    host, user, pwd, to = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"), os.getenv("EMAIL_TO")
    if not all([host, user, pwd, to]):
        return False, "not_configured"
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as s:
            s.starttls(); s.login(user, pwd); s.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, str(exc)[:200]
