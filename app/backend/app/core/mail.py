"""Mail configuration resolution and SMTP delivery.

Deployment environment variables override the matching database-backed admin
settings. Blank environment values are treated as unset so the variables can be
listed in example Compose files without disabling the existing admin settings.
"""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from typing import Mapping


MAIL_ENVIRONMENT_KEYS = {
    "mail_enabled": "KNITTING_MAIL_ENABLED",
    "mail_host": "KNITTING_MAIL_HOST",
    "mail_port": "KNITTING_MAIL_PORT",
    "mail_username": "KNITTING_MAIL_USERNAME",
    "mail_password": "KNITTING_MAIL_PASSWORD",
    "mail_from": "KNITTING_MAIL_FROM",
    "mail_security": "KNITTING_MAIL_SECURITY",
    "mail_announcements_enabled": "KNITTING_MAIL_ANNOUNCEMENTS_ENABLED",
}

MAIL_DEFAULTS = {
    "mail_enabled": "false",
    "mail_host": "",
    "mail_port": "587",
    "mail_username": "",
    "mail_password": "",
    "mail_from": "",
    "mail_security": "starttls",
    "mail_announcements_enabled": "false",
}

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_SECURITY_MODES = {"none", "starttls", "ssl"}


def parse_mail_boolean(value: object, setting_name: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{setting_name} must be true or false")


def resolve_mail_settings(
    stored: Mapping[str, object],
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], set[str]]:
    """Return effective settings and the fields managed by the environment."""
    environment = os.environ if environ is None else environ
    settings = {**MAIL_DEFAULTS, **{key: str(value) for key, value in stored.items()}}

    # Preserve the historical database meaning: true was STARTTLS and false was
    # implicit SSL. A saved explicit security mode takes precedence.
    if not stored.get("mail_security"):
        legacy_tls = str(stored.get("mail_tls", "true")).strip().lower()
        settings["mail_security"] = "starttls" if legacy_tls == "true" else "ssl"

    managed: set[str] = set()
    for setting_key, environment_key in MAIL_ENVIRONMENT_KEYS.items():
        raw_value = environment.get(environment_key)
        if raw_value is None or not str(raw_value).strip():
            continue
        settings[setting_key] = str(raw_value) if setting_key == "mail_password" else str(raw_value).strip()
        managed.add(setting_key)

    return settings, managed


def validate_mail_settings(settings: Mapping[str, object], require_enabled: bool = True) -> dict[str, object]:
    """Validate and normalize effective settings for SMTP use."""
    enabled = parse_mail_boolean(settings.get("mail_enabled", "false"), "Mail enabled")
    announcements_enabled = parse_mail_boolean(
        settings.get("mail_announcements_enabled", "false"),
        "Announcement email enabled",
    )

    try:
        port = int(str(settings.get("mail_port", "587")).strip())
    except (TypeError, ValueError):
        raise ValueError("Mail port must be an integer") from None
    if not 1 <= port <= 65535:
        raise ValueError("Mail port must be between 1 and 65535")

    security = str(settings.get("mail_security", "starttls")).strip().lower()
    if security not in _SECURITY_MODES:
        raise ValueError("Mail security must be one of: none, starttls, ssl")

    host = str(settings.get("mail_host", "")).strip()
    username = str(settings.get("mail_username", "")).strip()
    password = str(settings.get("mail_password", ""))
    from_address = str(settings.get("mail_from", "")).strip() or username

    if bool(username) != bool(password):
        raise ValueError("Mail username and password must be provided together")
    if enabled:
        if not host:
            raise ValueError("Mail host is required when mail is enabled")
        if not from_address:
            raise ValueError("Mail from address is required when mail is enabled")
    elif require_enabled:
        raise ValueError("Mail is not enabled")

    return {
        "enabled": enabled,
        "announcements_enabled": announcements_enabled,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "from_address": from_address,
        "security": security,
    }


def send_mail(settings: Mapping[str, object], to: str, subject: str, body: str) -> None:
    """Send one plain-text message using validated effective settings."""
    config = validate_mail_settings(settings)
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = str(config["from_address"])
    message["To"] = to

    server = None
    try:
        if config["security"] == "ssl":
            server = smtplib.SMTP_SSL(str(config["host"]), int(config["port"]), timeout=10)
        else:
            server = smtplib.SMTP(str(config["host"]), int(config["port"]), timeout=10)
            if config["security"] == "starttls":
                server.starttls()
        if config["username"]:
            server.login(str(config["username"]), str(config["password"]))
        server.sendmail(str(config["from_address"]), [to], message.as_string())
    finally:
        if server is not None:
            server.quit()
