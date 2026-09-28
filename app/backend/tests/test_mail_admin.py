import unittest
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.admin import service


class MailAdminSettingsTests(unittest.TestCase):
    @patch.object(service, "_load_effective_mail_settings")
    def test_get_masks_environment_password_and_reports_managed_fields(self, load_settings):
        load_settings.return_value = (
            {
                "mail_enabled": "yes",
                "mail_host": "127.0.0.1",
                "mail_port": "25",
                "mail_username": "knitting-library",
                "mail_password": "super-secret",
                "mail_from": "knitting@example.com",
                "mail_security": "NONE",
                "mail_announcements_enabled": "no",
            },
            {"mail_password", "mail_security"},
        )

        result = service.get_mail_settings({"is_admin": True})

        self.assertEqual(result["mail_password"], "••••••••")
        self.assertNotIn("super-secret", repr(result))
        self.assertEqual(result["mail_enabled"], "true")
        self.assertEqual(result["mail_security"], "none")
        self.assertEqual(result["environment_managed"], ["mail_password", "mail_security"])

    @patch.object(service, "resolve_mail_settings")
    @patch.object(service, "_load_stored_mail_settings", return_value={})
    @patch.object(service, "get_db")
    def test_save_rejects_environment_managed_fields(self, get_db, _load_stored, resolve):
        get_db.return_value = MagicMock()
        resolve.return_value = ({}, {"mail_host"})

        with self.assertRaises(HTTPException) as raised:
            service.save_mail_settings({"mail_host": "other.example.com"}, {"is_admin": True})

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("mail_host", raised.exception.detail)
        get_db.return_value.execute.assert_not_called()
        get_db.return_value.close.assert_called_once_with()

    @patch.object(service, "validate_mail_settings")
    @patch.object(service, "resolve_mail_settings", return_value=({}, set()))
    @patch.object(service, "_load_stored_mail_settings", return_value={})
    @patch.object(service, "get_db")
    def test_template_only_save_does_not_validate_transport(
        self,
        get_db,
        _load_stored,
        _resolve,
        validate,
    ):
        connection = get_db.return_value

        service.save_mail_settings(
            {"mail_tmpl_welcome_subject": "Welcome"},
            {"is_admin": True},
        )

        validate.assert_not_called()
        connection.execute.assert_called_once()
        connection.commit.assert_called_once_with()
        connection.close.assert_called_once_with()


class MailSettingsPersistenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "mail.db")
        with self.connect() as conn:
            conn.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.enterContext(patch.object(service, "get_db", self.connect))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def seed(self, settings):
        conn = self.connect()
        try:
            conn.executemany("INSERT INTO app_settings VALUES (?,?)", settings.items())
            conn.commit()
        finally:
            conn.close()

    def test_disable_persists_despite_invalid_transport_and_announcement_settings(self):
        self.seed({"mail_enabled": "true", "mail_port": "invalid", "mail_username": "incomplete", "mail_announcements_enabled": "typo"})
        service.save_mail_settings({"mail_enabled": "false"}, {})
        self.assertEqual(service._load_stored_mail_settings()["mail_enabled"], "false")

    def test_legacy_tls_update_changes_explicit_security_mode(self):
        self.seed({"mail_security": "starttls", "mail_tls": "true"})
        service.save_mail_settings({"mail_tls": "false"}, {})
        self.assertEqual(service.get_mail_settings({})["mail_security"], "ssl")
        service.save_mail_settings({"mail_tls": "true"}, {})
        self.assertEqual(service.get_mail_settings({})["mail_security"], "starttls")

    def test_explicit_security_wins_over_legacy_field_in_same_request(self):
        service.save_mail_settings({"mail_tls": "true", "mail_security": "none"}, {})
        self.assertEqual(service.get_mail_settings({})["mail_security"], "none")

    def test_legacy_tls_cannot_bypass_environment_lock(self):
        with patch.dict(os.environ, {"KNITTING_MAIL_SECURITY": "none"}):
            with self.assertRaises(HTTPException) as raised:
                service.save_mail_settings({"mail_tls": "false"}, {})
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(service._load_stored_mail_settings(), {})

    def test_enabling_invalid_transport_is_rejected_without_writing(self):
        self.seed({"mail_enabled": "false", "mail_port": "invalid"})
        with self.assertRaises(HTTPException) as raised:
            service.save_mail_settings({"mail_enabled": "true"}, {})
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(service._load_stored_mail_settings()["mail_enabled"], "false")


if __name__ == "__main__":
    unittest.main()
