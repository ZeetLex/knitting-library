import asyncio
import io
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks, UploadFile
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_real_sqlite_connect = sqlite3.connect
with tempfile.TemporaryDirectory() as startup_db, patch.object(Path, "mkdir"), patch.object(
    sqlite3,
    "connect",
    side_effect=lambda *_args, **_kwargs: _real_sqlite_connect(str(Path(startup_db) / "startup.db")),
):
    from app.core import foundation
    from app.recipes import files as recipe_files, repository


class RecipeTagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.data_dir = root / "recipes"
        self.data_dir.mkdir()
        for target, name, value in (
            (foundation, "DB_PATH", root / "recipes.db"),
            (repository, "DATA_DIR", self.data_dir),
        ):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        foundation.init_db()
        self.user = {"id": "tag-tester", "username": "tag-tester", "is_admin": True}
        with closing(foundation.get_db()) as conn, conn:
            conn.executemany(
                "INSERT INTO recipes (id,title,file_type,created_date) VALUES (?,?,?,?)",
                [(name, name.title(), "pdf", "2026-11-13") for name in ("socks", "hat")],
            )
            conn.execute("INSERT INTO tags (name) VALUES ('existing')")

    def assert_saved_tags(self, recipe_id, expected):
        # Each read opens a new database connection, as a refresh would.
        recipe = repository.get_recipe(recipe_id, self.user)
        self.assertEqual(set(recipe["tags"]), set(expected))
        for tag in expected:
            result = repository.list_recipes(tags=tag, current_user=self.user)
            matches = {r["id"]: r for r in result["recipes"]}
            self.assertIn(recipe_id, matches)
            self.assertEqual(set(matches[recipe_id]["tags"]), set(expected))

    def test_edit_persists_existing_and_new_tags_after_refresh_and_filter(self):
        updated = asyncio.run(repository.update_recipe(
            "socks", title="Socks", description="", categories="Knitting",
            tags=" existing, new tag, new tag, , ", current_user=self.user,
        ))
        self.assertEqual(set(updated["tags"]), {"existing", "new tag"})
        self.assertEqual(updated["categories"], ["Knitting"])
        self.assert_saved_tags("socks", {"existing", "new tag"})
        self.assert_saved_tags("hat", set())

    def test_edit_replaces_and_clears_tags_without_deleting_taxonomy(self):
        with closing(foundation.get_db()) as conn, conn:
            conn.execute(
                "INSERT INTO recipe_tags (recipe_id,tag_id) SELECT 'socks',id FROM tags"
            )
        for tags, expected in (("replacement", {"replacement"}), ("", set())):
            asyncio.run(repository.update_recipe(
                "socks", title="Socks", description="", categories="",
                tags=tags, current_user=self.user,
            ))
            self.assert_saved_tags("socks", expected)
            self.assertEqual(repository.list_recipes(tags="existing", current_user=self.user)["total"], 0)
        with closing(foundation.get_db()) as conn, conn:
            self.assertEqual({r["name"] for r in conn.execute("SELECT name FROM tags")},
                             {"existing", "replacement"})

    def test_bulk_add_preserves_existing_tags_and_ignores_duplicate_links(self):
        with closing(foundation.get_db()) as conn, conn:
            conn.execute(
                "INSERT INTO recipe_tags (recipe_id,tag_id) SELECT 'socks',id FROM tags"
            )
        for _ in range(2):
            repository.bulk_update_recipes(
                {"ids": ["socks", "hat"], "tags": ["shared", "shared"]}, self.user,
            )
        self.assert_saved_tags("socks", {"existing", "shared"})
        self.assert_saved_tags("hat", {"shared"})
        with closing(foundation.get_db()) as conn, conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM recipe_tags").fetchone()[0], 3)

    def test_upload_persists_tags(self):
        image = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(image, format="PNG")
        image.seek(0)
        # The application service registry supplies this cross-module helper.
        with patch.object(repository, "_generate_thumbnail", recipe_files._generate_thumbnail, create=True):
            recipe = asyncio.run(repository.create_recipe(
                BackgroundTasks(), title="Mittens", description="", categories="",
                tags="existing,uploaded", files=[UploadFile(filename="page.png", file=image)],
                current_user=self.user,
            ))
        self.assert_saved_tags(recipe["id"], {"existing", "uploaded"})

    def test_import_confirmation_persists_tags_after_recipe_rename(self):
        (self.data_dir / "socks").mkdir()
        with closing(foundation.get_db()) as conn, conn:
            conn.execute("INSERT INTO import_queue (recipe_id,group_name,status) VALUES ('socks','Socks','staged')")
        result = repository.import_confirm(
            "socks", {"title": "Imported socks", "tags": "existing,imported"}, self.user,
        )
        self.assertEqual(result["recipe_id"], "imported-socks")
        self.assert_saved_tags(result["recipe_id"], {"existing", "imported"})


if __name__ == "__main__":
    unittest.main()
