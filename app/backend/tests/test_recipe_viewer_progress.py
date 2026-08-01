import sqlite3
import sys
import unittest
import math
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_real_sqlite_connect = sqlite3.connect
with patch.object(Path, "mkdir"), patch.object(
    sqlite3,
    "connect",
    side_effect=lambda *_args, **_kwargs: _real_sqlite_connect(":memory:"),
):
    from app.recipes import repository


class ViewerProgressTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE recipes (id TEXT PRIMARY KEY);
            CREATE TABLE recipe_viewer_progress (
                recipe_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                view_mode TEXT NOT NULL DEFAULT 'original',
                source_mode TEXT NOT NULL DEFAULT '',
                image_index INTEGER NOT NULL DEFAULT 0,
                zoom REAL NOT NULL DEFAULT 1,
                scroll_y INTEGER NOT NULL DEFAULT 0,
                pdf_scroll_y INTEGER NOT NULL DEFAULT 0,
                text_scroll_y INTEGER NOT NULL DEFAULT 0,
                mobile_images_visible INTEGER NOT NULL DEFAULT 0,
                revision INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (recipe_id, user_id)
            );
            INSERT INTO recipes (id) VALUES ('rabbit');
            """
        )
        class ConnectionProxy:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def close(self):
                return None

        self.db_patch = patch.object(repository, "get_db", side_effect=lambda: ConnectionProxy(self.conn))
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.conn.close()

    def test_progress_round_trips_pdf_source_and_scroll_per_user(self):
        saved = repository.save_recipe_viewer_progress(
            "rabbit",
            {
                "viewMode": "original",
                "sourceMode": "pdf",
                "imageIndex": 4,
                "zoom": 1.5,
                "scrollY": 20,
                "pdfScrollY": 1840,
                "textScrollY": 60,
                "revision": 100,
            },
            {"id": "user-a"},
        )

        self.assertEqual(saved["sourceMode"], "pdf")
        self.assertEqual(saved["pdfScrollY"], 1840)
        self.assertEqual(saved["revision"], 100)

        other_user = repository.get_recipe_viewer_progress("rabbit", {"id": "user-b"})
        self.assertEqual(other_user, {"exists": False})

    def test_progress_clamps_invalid_source_and_negative_pdf_scroll(self):
        saved = repository.save_recipe_viewer_progress(
            "rabbit",
            {"sourceMode": "invalid", "pdfScrollY": -25},
            {"id": "user-a"},
        )

        self.assertEqual(saved["sourceMode"], "")
        self.assertEqual(saved["pdfScrollY"], 0)

    def test_older_progress_revision_cannot_overwrite_newer_state(self):
        newest = repository.save_recipe_viewer_progress(
            "rabbit",
            {"sourceMode": "pdf", "pdfScrollY": 2400, "revision": 200},
            {"id": "user-a"},
        )
        stale = repository.save_recipe_viewer_progress(
            "rabbit",
            {"sourceMode": "images", "pdfScrollY": 0, "revision": 150},
            {"id": "user-a"},
        )

        self.assertEqual(newest["revision"], 200)
        self.assertEqual(stale["revision"], 200)
        self.assertEqual(stale["sourceMode"], "pdf")
        self.assertEqual(stale["pdfScrollY"], 2400)

    def test_non_finite_and_oversized_progress_values_are_safely_bounded(self):
        saved = repository.save_recipe_viewer_progress(
            "rabbit",
            {
                "imageIndex": 10 ** 1000,
                "zoom": float("nan"),
                "scrollY": float("inf"),
                "pdfScrollY": "-Infinity",
                "textScrollY": 10 ** 1000,
                "revision": 10 ** 1000,
            },
            {"id": "user-a"},
        )

        self.assertEqual(saved["imageIndex"], repository.MAX_VIEWER_PROGRESS_INTEGER)
        self.assertEqual(saved["zoom"], 1)
        self.assertTrue(math.isfinite(saved["zoom"]))
        self.assertEqual(saved["scrollY"], 0)
        self.assertEqual(saved["pdfScrollY"], 0)
        self.assertEqual(saved["textScrollY"], repository.MAX_VIEWER_PROGRESS_INTEGER)
        self.assertLess(saved["revision"], repository.MAX_VIEWER_PROGRESS_INTEGER)

    def test_saturated_revision_is_rebased_and_does_not_block_future_saves(self):
        self.conn.execute(
            "INSERT INTO recipe_viewer_progress "
            "(recipe_id,user_id,source_mode,revision,updated_at) VALUES (?,?,?,?,?)",
            ("rabbit", "user-a", "pdf", repository.MAX_VIEWER_PROGRESS_INTEGER, "old"),
        )
        self.conn.commit()

        with patch.object(repository.time, "time", return_value=1.0):
            rebased = repository.save_recipe_viewer_progress(
                "rabbit", {"sourceMode": "images", "revision": 1001}, {"id": "user-a"}
            )
            newer = repository.save_recipe_viewer_progress(
                "rabbit", {"sourceMode": "pdf", "revision": 1002}, {"id": "user-a"}
            )

        self.assertEqual(rebased["revision"], 1001)
        self.assertEqual(rebased["sourceMode"], "images")
        self.assertEqual(newer["revision"], 1002)
        self.assertEqual(newer["sourceMode"], "pdf")


if __name__ == "__main__":
    unittest.main()
