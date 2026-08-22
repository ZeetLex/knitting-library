import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import bcrypt

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.cli import PasswordResetError, reset_password


class PasswordResetTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "recipes.db"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                );
                CREATE TABLE sessions (token TEXT PRIMARY KEY, user_id TEXT NOT NULL);
                CREATE TABLE user_action_log (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    recipe_id TEXT,
                    recipe_title TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO users VALUES ('user-1', 'admin', 'old-hash');
                INSERT INTO sessions VALUES ('session-1', 'user-1');
                """
            )
        finally:
            conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reset_updates_hash_revokes_sessions_and_writes_audit_event(self):
        reset_password(self.db_path, "admin", "new-password")

        conn = sqlite3.connect(self.db_path)
        try:
            password_hash = conn.execute(
                "SELECT password_hash FROM users WHERE username = 'admin'"
            ).fetchone()[0]
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            audit = conn.execute(
                "SELECT action, metadata_json FROM user_action_log"
            ).fetchone()
        finally:
            conn.close()

        self.assertTrue(bcrypt.checkpw(b"new-password", password_hash.encode()))
        self.assertEqual(session_count, 0)
        self.assertEqual(audit, ("password_updated", '{"method": "container_cli"}'))

    def test_unknown_user_does_not_change_database(self):
        with self.assertRaisesRegex(PasswordResetError, "was not found"):
            reset_password(self.db_path, "missing", "new-password")

        conn = sqlite3.connect(self.db_path)
        try:
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(session_count, 1)

    def test_short_password_is_rejected(self):
        with self.assertRaisesRegex(PasswordResetError, "at least 8"):
            reset_password(self.db_path, "admin", "short")


if __name__ == "__main__":
    unittest.main()
