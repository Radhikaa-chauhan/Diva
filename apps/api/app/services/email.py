"""Email delivery — stdlib smtplib, any SMTP provider (Gmail app password,
Brevo, SES SMTP, ...). Unconfigured (dev): logs the message instead of sending.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email. Logs instead of sending when SMTP is unconfigured.

    Raises nothing — delivery failure is logged, not fatal, so auth flows
    keep their don't-reveal-account-existence responses.
    """
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("SMTP not configured — email to %s NOT sent. Subject: %s | Body: %s",
                       to, subject, body)
        return

    msg = EmailMessage()
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    # ponytail: inline blocking send (runs in FastAPI's threadpool for sync
    # routes). Queue it when signup volume makes SMTP latency hurt.
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        logger.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        logger.error("Email delivery to %s failed: %s", to, exc)
