import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.mail import resolve_mail_settings, send_mail, validate_mail_settings


class MailConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.stored = {
            "mail_enabled": "true",
            "mail_host": "db.example.com",
            "mail_port": "587",
            "mail_username": "db-user",
            "mail_password": "db-password",
            "mail_from": "db@example.com",
            "mail_tls": "true",
            "mail_announcements_enabled": "false",
        }

    def test_database_settings_remain_the_default(self):
        settings, managed = resolve_mail_settings(self.stored, {})

        self.assertEqual(settings["mail_host"], "db.example.com")
        self.assertEqual(settings["mail_security"], "starttls")
        self.assertEqual(managed, set())

    def test_environment_overrides_only_non_blank_fields(self):
        settings, managed = resolve_mail_settings(
            self.stored,
            {
                "KNITTING_MAIL_HOST": " 127.0.0.1 ",
                "KNITTING_MAIL_PORT": "25",
                "KNITTING_MAIL_USERNAME": "",
                "KNITTING_MAIL_SECURITY": "none",
            },
        )

        self.assertEqual(settings["mail_host"], "127.0.0.1")
        self.assertEqual(settings["mail_port"], "25")
        self.assertEqual(settings["mail_username"], "db-user")
        self.assertEqual(settings["mail_security"], "none")
        self.assertEqual(managed, {"mail_host", "mail_port", "mail_security"})

    def test_legacy_false_tls_value_means_implicit_ssl(self):
        settings, _managed = resolve_mail_settings({**self.stored, "mail_tls": "false"}, {})
        self.assertEqual(settings["mail_security"], "ssl")

    def test_explicit_database_security_replaces_legacy_toggle(self):
        settings, _managed = resolve_mail_settings(
            {**self.stored, "mail_tls": "false", "mail_security": "none"},
            {},
        )
        self.assertEqual(settings["mail_security"], "none")

    def test_validation_allows_an_unauthenticated_local_relay(self):
        settings = {
            "mail_enabled": "true",
            "mail_host": "127.0.0.1",
            "mail_port": "25",
            "mail_username": "",
            "mail_password": "",
            "mail_from": "knitting@example.com",
            "mail_security": "none",
            "mail_announcements_enabled": "false",
        }
        validated = validate_mail_settings(settings)
        self.assertEqual(validated["security"], "none")
        self.assertEqual(validated["port"], 25)

    def test_validation_rejects_incomplete_credentials(self):
        settings, _managed = resolve_mail_settings(
            {**self.stored, "mail_password": ""},
            {},
        )
        with self.assertRaisesRegex(ValueError, "provided together"):
            validate_mail_settings(settings)

    def test_validation_rejects_unknown_security_and_invalid_port(self):
        settings, _managed = resolve_mail_settings(self.stored, {})
        with self.assertRaisesRegex(ValueError, "one of"):
            validate_mail_settings({**settings, "mail_security": "sometimes"})
        with self.assertRaisesRegex(ValueError, "between 1 and 65535"):
            validate_mail_settings({**settings, "mail_port": "70000"})


class MailDeliveryTests(unittest.TestCase):
    def settings(self, security="starttls", username="mailer", password="secret"):
        return {
            "mail_enabled": "true",
            "mail_host": "smtp.example.com",
            "mail_port": "587",
            "mail_username": username,
            "mail_password": password,
            "mail_from": "knitting@example.com",
            "mail_security": security,
            "mail_announcements_enabled": "false",
        }

    @patch("app.core.mail.smtplib.SMTP")
    def test_starttls_transport_authenticates(self, smtp):
        send_mail(self.settings(), "user@example.com", "Subject", "Body")

        smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)
        smtp.return_value.starttls.assert_called_once_with()
        smtp.return_value.login.assert_called_once_with("mailer", "secret")
        smtp.return_value.sendmail.assert_called_once()
        smtp.return_value.quit.assert_called_once_with()

    @patch("app.core.mail.smtplib.SMTP")
    def test_plain_transport_can_skip_authentication(self, smtp):
        send_mail(
            self.settings(security="none", username="", password=""),
            "user@example.com",
            "Subject",
            "Body",
        )

        smtp.return_value.starttls.assert_not_called()
        smtp.return_value.login.assert_not_called()
        smtp.return_value.sendmail.assert_called_once()

    @patch("app.core.mail.smtplib.SMTP_SSL")
    def test_implicit_ssl_uses_smtp_ssl(self, smtp_ssl):
        send_mail(self.settings(security="ssl"), "user@example.com", "Subject", "Body")

        smtp_ssl.assert_called_once_with("smtp.example.com", 587, timeout=10)
        smtp_ssl.return_value.login.assert_called_once_with("mailer", "secret")


if __name__ == "__main__":
    unittest.main()
