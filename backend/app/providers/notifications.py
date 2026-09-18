from __future__ import annotations

from typing import Any

from app.notifications import email as email_mod
from app.notifications import telegram as telegram_mod

from .base import NotificationProvider


class TelegramProvider(NotificationProvider):
    key = "telegram"

    def is_configured(self) -> bool:
        return telegram_mod.is_configured()

    def send(self, subject: str, body: str, **kwargs: Any) -> tuple[bool, str]:
        try:
            return telegram_mod.send_message(body, chat_id=kwargs.get("chat_id"))
        except Exception as exc:  # never propagate
            return False, f"{type(exc).__name__}: {exc}"


class EmailProvider(NotificationProvider):
    key = "email"

    def is_configured(self) -> bool:
        import os
        return all(os.getenv(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"))

    def send(self, subject: str, body: str, **kwargs: Any) -> tuple[bool, str]:
        try:
            fn = getattr(email_mod, "send_email", None)
            return fn(subject, body) if fn else (False, "email module has no send_email")
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"


class ConsoleProvider(NotificationProvider):
    """Always available; writes to the log. Keeps the pipeline observable with zero configuration."""
    key = "console"

    def is_configured(self) -> bool:
        return True

    def send(self, subject: str, body: str, **kwargs: Any) -> tuple[bool, str]:
        from app.core.logging import get_logger
        get_logger("notify.console").info("%s\n%s", subject, body[:2000])
        return True, "logged"
