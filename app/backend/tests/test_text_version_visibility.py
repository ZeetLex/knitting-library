import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_connect = sqlite3.connect
with patch.object(Path, "mkdir"), patch.object(sqlite3, "connect", side_effect=lambda *a, **k: _connect(":memory:")):
    from app.recipes import files, repository


class TextVersionVisibilityTests(unittest.TestCase):
    def test_setting_never_removes_existing_text_and_never_exposes_secrets(self):
        for enabled in (None, "false", "true"):
            for content in ("", "# Saved recipe"):
                with self.subTest(enabled=enabled, content=content):
                    conn = _connect(":memory:")
                    conn.row_factory = sqlite3.Row
                    conn.executescript("""
                        CREATE TABLE recipes (id TEXT);
                        CREATE TABLE recipe_text_versions (recipe_id TEXT, content_markdown TEXT);
                        CREATE TABLE recipe_text_generation_audits (recipe_id TEXT);
                        CREATE TABLE app_settings (key TEXT, value TEXT);
                        INSERT INTO recipes VALUES ('recipe');
                        INSERT INTO app_settings VALUES ('ai_api_key', 'never-return-this');
                    """)
                    if enabled is not None:
                        conn.execute("INSERT INTO app_settings VALUES ('ai_enabled', ?)", (enabled,))
                    if content:
                        conn.execute("INSERT INTO recipe_text_versions VALUES ('recipe', ?)", (content,))

                    class Database:
                        execute = conn.execute
                        def close(self):
                            pass

                    with patch.object(files, "get_db", return_value=Database()), \
                         patch.object(files, "_source_fingerprint", return_value="", create=True), \
                         patch.object(files, "_text_version_dict", repository._text_version_dict, create=True), \
                         patch.object(files, "_audit_dict", repository._audit_dict, create=True):
                        result = files.get_recipe_text_version("recipe", {"id": "ordinary-user"})
                    self.assertEqual(result["ai_enabled"], enabled == "true")
                    self.assertEqual(result["content_markdown"], content)
                    self.assertEqual(result["exists"], bool(content))
                    self.assertNotIn("never-return-this", str(result))
                    conn.close()
