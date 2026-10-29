"""Email helpers for self-service password reset.

Uses stdlib smtplib so no new dependency is required. If SMTP is not
configured, the reset link is logged to stdout in non-production
environments (so developers can still test the flow) and silently
dropped in production (admins keep the "Reset PW" button as fallback).
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from server.config import (
    app_base_url,
    app_environment,
    smtp_from,
    smtp_host,
    smtp_password,
    smtp_port,
    smtp_use_ssl,
    smtp_use_tls,
    smtp_username,
)
from server.services.security import RESET_TOKEN_MINUTES


def smtp_configured() -> bool:
    return bool(smtp_host())


def send_password_reset_email(to_email: str, username: str, token: str) -> bool:
    base = app_base_url()
    link = f"{base}/login.html?reset_token={token}"
    subject = "Reset your NOC Portal password"
    body = (
        f"Hello {username},\n\n"
        f"You requested a password reset for your NOC Portal account.\n\n"
        f"Reset your password using this link (expires in {RESET_TOKEN_MINUTES} minutes):\n"
        f"{link}\n\n"
        f"If you did not request this, you can safely ignore this email.\n\n"
        f"— NOC Portal\n"
    )

    if not smtp_configured():
        if app_environment() != "production":
            print(f"[DEV] Password reset link for {username} ({to_email}): {link}")
            return True
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_from()
    message["To"] = to_email
    message.set_content(body)

    try:
        if smtp_use_ssl():
            server = smtplib.SMTP_SSL(smtp_host(), smtp_port(), timeout=15)
        else:
            server = smtplib.SMTP(smtp_host(), smtp_port(), timeout=15)
            if smtp_use_tls():
                server.starttls()
        with server:
            if smtp_username():
                server.login(smtp_username(), smtp_password())
            server.send_message(message)
        return True
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"Failed to send password reset email to {to_email}: {exc}")
        return False