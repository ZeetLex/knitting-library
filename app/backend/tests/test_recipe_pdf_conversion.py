import hashlib
import asyncio
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import shutil
import threading
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_real_sqlite_connect = sqlite3.connect
with patch.object(Path, "mkdir"), patch.object(
    sqlite3,
    "connect",
    side_effect=lambda *_args, **_kwargs: _real_sqlite_connect(":memory:"),
):
    from app.recipes import files as recipe_files
    from app.recipes import repository as recipe_repository
    from app.ai import jobs as ai_jobs


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RecipePdfConversionTests(unittest.TestCase):
    def _image(self, path: Path, colour: tuple[int, int, int], size=(80, 120)) -> None:
        Image.new("RGB", size, colour).save(path)

    def _bind_pdf_pages(self, recipe_dir: Path) -> None:
        identity = recipe_files._pdf_identity(recipe_dir / "recipe.pdf")
        (recipe_dir / "pdf-pages" / recipe_files.PDF_PAGES_MANIFEST).write_text(
            json.dumps(identity), encoding="utf-8"
        )

    def test_source_images_follow_saved_order_and_ignore_derived_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            self._image(recipe_dir / "first.jpg", (255, 0, 0))
            self._image(recipe_dir / "second.png", (0, 255, 0))
            self._image(recipe_dir / "thumbnail.jpg", (0, 0, 255))
            pages_dir = recipe_dir / "pdf-pages"
            pages_dir.mkdir()
            self._image(pages_dir / "page-001.jpg", (20, 20, 20))

            names = recipe_files._source_image_names(
                recipe_dir,
                json.dumps(["second.png", "first.jpg"]),
            )

            self.assertEqual(names, ["second.png", "first.jpg"])

    def test_conversion_creates_ordered_pdf_without_modifying_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            first = recipe_dir / "first.jpg"
            second = recipe_dir / "second.png"
            self._image(first, (255, 0, 0))
            self._image(second, (0, 255, 0))
            before = {path.name: _sha256(path) for path in (first, second)}

            pdf_path = recipe_files._convert_images_to_pdf(
                recipe_dir,
                ["second.png", "first.jpg"],
            )

            self.assertEqual(pdf_path, recipe_dir / "recipe.pdf")
            self.assertTrue(pdf_path.exists())
            info = subprocess.run(
                ["pdfinfo", str(pdf_path)],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("Pages:           2", info)
            self.assertEqual(before, {path.name: _sha256(path) for path in (first, second)})

            rendered_prefix = recipe_dir / "rendered"
            subprocess.run(
                ["pdftoppm", "-f", "1", "-singlefile", "-png", str(pdf_path), str(rendered_prefix)],
                check=True,
                capture_output=True,
            )
            with Image.open(recipe_dir / "rendered.png") as page:
                r, g, b = page.convert("RGB").resize((1, 1)).getpixel((0, 0))
            self.assertGreater(g, r)
            self.assertGreater(g, b)

    def test_conversion_snapshots_image_order_only_after_acquiring_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            recipe_dir = data_dir / "recipe-1"
            recipe_dir.mkdir()
            self._image(recipe_dir / "first.jpg", (255, 0, 0))
            self._image(recipe_dir / "second.jpg", (0, 255, 0))
            row = {
                "id": "recipe-1",
                "file_type": "images",
                "image_order": json.dumps(["first.jpg", "second.jpg"]),
            }

            class Result:
                def fetchone(self):
                    return row

            class Connection:
                def execute(self, *_args, **_kwargs):
                    return Result()

                def close(self):
                    return None

            class Lock:
                def acquire(self, blocking=False):
                    row["image_order"] = json.dumps(["second.jpg", "first.jpg"])
                    return True

                def release(self):
                    return None

            converted_order = []

            def convert(_recipe_dir, image_names):
                converted_order.extend(image_names)
                (_recipe_dir / "recipe.pdf").write_bytes(b"%PDF-generated")

            with (
                patch.object(recipe_files, "DATA_DIR", data_dir),
                patch.object(recipe_files, "get_db", return_value=Connection()),
                patch.object(recipe_files, "IMAGE_PDF_CONVERSION_LOCK", Lock()),
                patch.object(recipe_files, "_convert_images_to_pdf", side_effect=convert),
                patch.object(recipe_files, "_convert_pdf_to_pages", return_value=[Path("page-1"), Path("page-2")]),
                patch.object(recipe_files, "_write_generated_pdf_manifest"),
                patch.object(recipe_files, "_create_generated_pdf_backup", return_value=None),
                patch("app.recipes.repository._get_recipe_full", return_value={"id": "recipe-1"}),
            ):
                recipe_files.convert_images_to_pdf("recipe-1", {"id": "user-1"})

            self.assertEqual(converted_order, ["second.jpg", "first.jpg"])

    def test_image_order_update_is_serialized_with_pdf_conversion(self):
        state = {"locked": False}

        class Lock:
            def __enter__(self):
                state["locked"] = True
                return self

            def __exit__(self, *_args):
                state["locked"] = False

        class Result:
            def fetchone(self):
                return {"id": "recipe-1"}

        class Connection:
            def execute(self, sql, *_args):
                if sql.startswith("UPDATE recipes SET image_order"):
                    self.assert_locked()
                return Result()

            def assert_locked(self):
                if not state["locked"]:
                    raise AssertionError("image order changed outside the PDF conversion lock")

            def commit(self):
                return None

            def close(self):
                return None

        with (
            patch.object(recipe_files, "IMAGE_PDF_CONVERSION_LOCK", Lock()),
            patch.object(recipe_files, "get_db", return_value=Connection()),
            patch.object(recipe_files, "_remove_generated_pdf_unlocked", return_value=False),
        ):
            result = recipe_files.set_image_order(
                "recipe-1",
                {"order": ["second.jpg", "first.jpg"]},
                {"id": "user-1"},
            )

        self.assertEqual(result["order"], ["second.jpg", "first.jpg"])

    def test_added_images_are_committed_under_pdf_conversion_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            recipe_dir = data_dir / "recipe-1"
            recipe_dir.mkdir()
            state = {"locked": False}

            class Lock:
                def __enter__(self):
                    state["locked"] = True
                    return self

                def __exit__(self, *_args):
                    state["locked"] = False

            class Result:
                def fetchone(self):
                    return {
                        "id": "recipe-1",
                        "file_type": "images",
                        "image_order": "[]",
                        "thumbnail_version": 0,
                    }

            class Connection:
                def execute(self, sql, *_args):
                    if sql.startswith("UPDATE recipes SET image_order") and not state["locked"]:
                        raise AssertionError("added images changed outside the PDF conversion lock")
                    return Result()

                def commit(self):
                    return None

                def close(self):
                    return None

            class Upload:
                filename = "new.jpg"

                async def read(self):
                    buffer = io.BytesIO()
                    Image.new("RGB", (10, 10), (255, 0, 0)).save(buffer, "JPEG")
                    return buffer.getvalue()

            with (
                patch.object(recipe_files, "DATA_DIR", data_dir),
                patch.object(recipe_files, "get_db", return_value=Connection()),
                patch.object(recipe_files, "IMAGE_PDF_CONVERSION_LOCK", Lock()),
                patch.object(recipe_files, "_generate_thumbnail", return_value="thumbnail.jpg"),
                patch.object(recipe_files, "_remove_generated_pdf_unlocked", return_value=False),
                patch("app.recipes.repository._get_recipe_full", return_value={"id": "recipe-1"}),
            ):
                result = asyncio.run(
                    recipe_files.add_images_to_recipe("recipe-1", [Upload()], {"id": "user-1"})
                )

            self.assertEqual(result, {"id": "recipe-1"})

    def test_add_images_rejects_excess_file_count_before_reading_uploads(self):
        class Upload:
            filename = "new.jpg"
            read_calls = 0

            async def read(self):
                self.read_calls += 1
                return b"unused"

        uploads = [Upload(), Upload(), Upload()]
        with patch.object(recipe_files, "MAX_ADD_IMAGE_FILES", 2):
            with self.assertRaisesRegex(recipe_files.HTTPException, "Too many image files") as raised:
                asyncio.run(recipe_files.add_images_to_recipe("recipe-1", uploads, {"id": "user-1"}))

        self.assertEqual(raised.exception.status_code, 413)
        self.assertEqual([upload.read_calls for upload in uploads], [0, 0, 0])

    def test_add_images_rejects_aggregate_bytes_without_reading_later_uploads(self):
        class Upload:
            filename = "new.jpg"

            def __init__(self, data):
                self.data = data
                self.read_calls = 0

            async def read(self):
                self.read_calls += 1
                return self.data

        uploads = [Upload(b"1234"), Upload(b"5678"), Upload(b"later")]
        with (
            patch.object(recipe_files, "MAX_ADD_IMAGE_TOTAL_BYTES", 7),
            patch.object(recipe_files, "MAX_IMAGE_BYTES", 10),
            patch.object(recipe_files, "_validate_file_magic", return_value=True),
        ):
            with self.assertRaisesRegex(recipe_files.HTTPException, "total upload size") as raised:
                asyncio.run(recipe_files.add_images_to_recipe("recipe-1", uploads, {"id": "user-1"}))

        self.assertEqual(raised.exception.status_code, 413)
        self.assertEqual([upload.read_calls for upload in uploads], [1, 1, 0])

    def test_add_images_waiting_for_conversion_lock_does_not_block_event_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            recipe_dir = data_dir / "recipe-1"
            recipe_dir.mkdir()
            lock = threading.RLock()
            acquired = threading.Event()
            release = threading.Event()

            def hold_lock():
                with lock:
                    acquired.set()
                    release.wait(timeout=1)

            holder = threading.Thread(target=hold_lock)
            holder.start()
            self.assertTrue(acquired.wait(timeout=1))

            class Result:
                def fetchone(self):
                    return {
                        "id": "recipe-1", "file_type": "images", "image_order": "[]",
                        "thumbnail_version": 0,
                    }

            class Connection:
                def execute(self, *_args, **_kwargs):
                    return Result()
                def commit(self):
                    return None
                def close(self):
                    return None

            class Upload:
                filename = "new.jpg"
                async def read(self):
                    return b"valid"

            async def exercise():
                started = time.monotonic()
                task = asyncio.create_task(
                    recipe_files.add_images_to_recipe("recipe-1", [Upload()], {"id": "user-1"})
                )
                await asyncio.sleep(0.03)
                elapsed = time.monotonic() - started
                release.set()
                await task
                return elapsed

            try:
                with (
                    patch.object(recipe_files, "DATA_DIR", data_dir),
                    patch.object(recipe_files, "IMAGE_PDF_CONVERSION_LOCK", lock),
                    patch.object(recipe_files, "get_db", return_value=Connection()),
                    patch.object(recipe_files, "_validate_file_magic", return_value=True),
                    patch.object(recipe_files, "_generate_thumbnail", return_value="thumbnail.jpg"),
                    patch.object(recipe_files, "_remove_generated_pdf_unlocked", return_value=False),
                    patch("app.recipes.repository._get_recipe_full", return_value={"id": "recipe-1"}),
                ):
                    elapsed = asyncio.run(exercise())
            finally:
                release.set()
                holder.join(timeout=1)

            self.assertLess(elapsed, 0.1)

    def test_failed_conversion_leaves_no_partial_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            (recipe_dir / "broken.jpg").write_bytes(b"not an image")

            with self.assertRaises(ValueError):
                recipe_files._convert_images_to_pdf(recipe_dir, ["broken.jpg"])

            self.assertFalse((recipe_dir / "recipe.pdf").exists())
            self.assertFalse((recipe_dir / "recipe.pdf.tmp").exists())

    def test_conversion_rejects_page_and_decoded_pixel_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            self._image(recipe_dir / "first.jpg", (255, 0, 0), size=(120, 160))
            self._image(recipe_dir / "second.jpg", (0, 0, 255), size=(120, 160))

            with patch.object(recipe_files, "MAX_IMAGE_PDF_PAGES", 1):
                with self.assertRaisesRegex(ValueError, "at most 1 pages"):
                    recipe_files._convert_images_to_pdf(recipe_dir, ["first.jpg", "second.jpg"])

            with patch.object(recipe_files, "MAX_IMAGE_PDF_PIXELS", 10_000):
                with self.assertRaisesRegex(ValueError, "too large"):
                    recipe_files._convert_images_to_pdf(recipe_dir, ["first.jpg"])

            with patch.object(recipe_files, "MAX_IMAGE_PDF_SOURCE_PIXELS", 10_000):
                with self.assertRaisesRegex(ValueError, "source image is too large"):
                    recipe_files._convert_images_to_pdf(recipe_dir, ["first.jpg"])

            self.assertFalse((recipe_dir / "recipe.pdf").exists())

    def test_uploaded_pdf_page_limit_is_checked_before_rendering_and_preserves_published_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-many-pages")
            pages_dir = recipe_dir / recipe_files.PDF_PAGES_DIR
            pages_dir.mkdir()
            (pages_dir / "sentinel").write_bytes(b"old")

            with (
                patch.object(recipe_files, "MAX_PDF_RENDER_PAGES", 2),
                patch("pdf2image.pdfinfo_from_path", return_value={"Pages": 3}),
                patch("pdf2image.convert_from_path") as render,
            ):
                self.assertEqual(recipe_files._convert_pdf_to_pages_unlocked(recipe_dir), [])

            render.assert_not_called()
            self.assertEqual((pages_dir / "sentinel").read_bytes(), b"old")
            self.assertEqual(list(recipe_dir.glob(".pdf-pages-*.tmp")), [])

    def test_uploaded_pdf_render_limits_never_publish_partial_pages(self):
        limit_cases = [
            ("MAX_PDF_RENDER_OUTPUT_BYTES", 100, 10),
            ("MAX_PDF_RENDER_DECODED_PIXELS", 100, 10_000),
            ("MAX_PDF_RENDER_TEMP_BYTES", 100, 10),
        ]
        for limited_name, limited_value, generous_value in limit_cases:
            with self.subTest(limit=limited_name), tempfile.TemporaryDirectory() as tmp:
                recipe_dir = Path(tmp)
                (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-bounded")
                pages_dir = recipe_dir / recipe_files.PDF_PAGES_DIR
                pages_dir.mkdir()
                (pages_dir / "sentinel").write_bytes(b"old")

                def render(*_args, **kwargs):
                    rendered = Path(kwargs["output_folder"]) / "rendered-1.jpg"
                    Image.new("RGB", (20, 20), (255, 0, 0)).save(rendered, quality=95)
                    if limited_name == "MAX_PDF_RENDER_TEMP_BYTES":
                        (Path(kwargs["output_folder"]) / "poppler-extra.tmp").write_bytes(b"x" * 200)
                    return [rendered]

                limits = {
                    "MAX_PDF_RENDER_OUTPUT_BYTES": generous_value,
                    "MAX_PDF_RENDER_DECODED_PIXELS": generous_value,
                    "MAX_PDF_RENDER_TEMP_BYTES": generous_value,
                }
                limits[limited_name] = limited_value
                with (
                    patch("pdf2image.pdfinfo_from_path", return_value={"Pages": 1}),
                    patch("pdf2image.convert_from_path", side_effect=render),
                    patch.object(recipe_files, "MAX_PDF_RENDER_OUTPUT_BYTES", limits["MAX_PDF_RENDER_OUTPUT_BYTES"]),
                    patch.object(recipe_files, "MAX_PDF_RENDER_DECODED_PIXELS", limits["MAX_PDF_RENDER_DECODED_PIXELS"]),
                    patch.object(recipe_files, "MAX_PDF_RENDER_TEMP_BYTES", limits["MAX_PDF_RENDER_TEMP_BYTES"]),
                ):
                    self.assertEqual(recipe_files._convert_pdf_to_pages_unlocked(recipe_dir), [])

                self.assertEqual((pages_dir / "sentinel").read_bytes(), b"old")
                self.assertEqual(list(recipe_dir.glob(".pdf-pages-*.tmp")), [])

    def test_uploaded_pdf_render_has_a_finite_cpu_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-timeout")
            seen = []

            def timeout_render(*_args, **kwargs):
                seen.append(kwargs.get("timeout"))
                raise TimeoutError("injected poppler timeout")

            with (
                patch.object(recipe_files, "MAX_PDF_RENDER_SECONDS", 7),
                patch("pdf2image.pdfinfo_from_path", return_value={"Pages": 1}),
                patch("pdf2image.convert_from_path", side_effect=timeout_render),
            ):
                self.assertEqual(recipe_files._convert_pdf_to_pages_unlocked(recipe_dir), [])

            self.assertEqual(len(seen), 1)
            self.assertGreater(seen[0], 0)
            self.assertLessEqual(seen[0], 7)
            self.assertFalse((recipe_dir / recipe_files.PDF_PAGES_DIR).exists())

    def test_manual_pdf_is_not_treated_as_generated_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-manual")
            self._image(recipe_dir / "first.jpg", (255, 0, 0))
            self.assertFalse(recipe_files._pdf_is_app_generated(recipe_dir))

            recipe_files._convert_images_to_pdf(recipe_dir, ["first.jpg"])
            recipe_files._write_generated_pdf_manifest(recipe_dir, ["first.jpg"])
            self.assertTrue(recipe_files._pdf_is_app_generated(recipe_dir))

            (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-manual-replacement")
            self.assertFalse(recipe_files._pdf_is_app_generated(recipe_dir))

    def test_pdf_page_discovery_requires_identity_for_legacy_root_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            self._image(recipe_dir / "page-001.jpg", (255, 0, 0))
            (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-legacy-current")
            self.assertEqual(recipe_files._discover_pdf_pages(recipe_dir), [])

            (recipe_dir / recipe_files.PDF_PAGES_MANIFEST).write_text(
                json.dumps(recipe_files._pdf_identity(recipe_dir / "recipe.pdf")), encoding="utf-8"
            )
            self.assertEqual(
                [path.name for path in recipe_files._discover_pdf_pages(recipe_dir)],
                ["page-001.jpg"],
            )

            (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-legacy-replaced")
            self.assertEqual(recipe_files._discover_pdf_pages(recipe_dir), [])

            pages_dir = recipe_dir / "pdf-pages"
            pages_dir.mkdir()
            self._image(pages_dir / "page-002.jpg", (0, 255, 0))
            (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-current")
            self._bind_pdf_pages(recipe_dir)
            self.assertEqual(
                [path.name for path in recipe_files._discover_pdf_pages(recipe_dir)],
                ["page-002.jpg"],
            )
            self.assertIsNotNone(recipe_files._read_pdf_page_bytes(recipe_dir, "page-002.jpg"))

            (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-replaced")
            self.assertEqual(recipe_files._discover_pdf_pages(recipe_dir), [])
            self.assertIsNone(recipe_files._read_pdf_page_bytes(recipe_dir, "page-002.jpg"))

    def test_identity_sensitive_discovery_fingerprinting_and_ai_reads_take_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            recipe_dir = data_dir / "recipe-1"
            recipe_dir.mkdir()
            image = recipe_dir / "first.jpg"
            self._image(image, (255, 0, 0))
            state = {"depth": 0, "entries": 0}

            class Lock:
                def __enter__(self):
                    state["depth"] += 1
                    state["entries"] += 1
                    return self
                def __exit__(self, *_args):
                    state["depth"] -= 1

            def locked_recipe(*_args, **_kwargs):
                if not state["depth"]:
                    raise AssertionError("artifact identity inspected outside conversion lock")
                return {"id": "recipe-1", "file_type": "images", "images": ["first.jpg"]}

            real_open = open
            def locked_open(*args, **kwargs):
                if not state["depth"]:
                    raise AssertionError("AI image read outside conversion lock")
                return real_open(*args, **kwargs)

            lock = Lock()
            with (
                patch.object(recipe_repository, "DATA_DIR", data_dir),
                patch.object(recipe_repository, "IMAGE_PDF_CONVERSION_LOCK", lock),
                patch.object(recipe_repository, "_get_recipe_full", side_effect=locked_recipe),
            ):
                fingerprint = recipe_repository._source_fingerprint("recipe-1", object())
            self.assertTrue(fingerprint)

            with (
                patch.object(ai_jobs, "DATA_DIR", data_dir),
                patch.object(ai_jobs, "IMAGE_PDF_CONVERSION_LOCK", lock),
                patch.object(ai_jobs, "_get_recipe_full", side_effect=locked_recipe),
            ):
                self.assertEqual(ai_jobs._collect_recipe_image_paths("recipe-1", object(), 5), [image])

            with (
                patch.object(ai_jobs, "IMAGE_PDF_CONVERSION_LOCK", lock),
                patch("builtins.open", side_effect=locked_open),
            ):
                self.assertIn("data:image/jpeg;base64,", ai_jobs._image_payload_for_path(image)["image_url"]["url"])

            (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-current")
            self._image(recipe_dir / "page-001.jpg", (0, 255, 0))
            (recipe_dir / recipe_files.PDF_PAGES_MANIFEST).write_text(
                json.dumps(recipe_files._pdf_identity(recipe_dir / "recipe.pdf")), encoding="utf-8"
            )
            with (
                patch.object(recipe_files, "DATA_DIR", data_dir),
                patch.object(recipe_files, "IMAGE_PDF_CONVERSION_LOCK", lock),
            ):
                self.assertEqual(recipe_files.get_pdf_pages("recipe-1"), {"pages": ["page-001.jpg"]})
            self.assertGreaterEqual(state["entries"], 4)

    def test_lazy_pdf_responses_use_immutable_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            recipe_dir = data_dir / "recipe-1"
            recipe_dir.mkdir()
            pdf = recipe_dir / "recipe.pdf"
            pdf.write_bytes(b"%PDF-original")

            class Result:
                def fetchone(self):
                    return {"title": "Snapshot", "file_type": "pdf"}
            class Connection:
                def execute(self, *_args, **_kwargs):
                    return Result()
                def close(self):
                    return None

            with (
                patch.object(recipe_files, "DATA_DIR", data_dir),
                patch.object(recipe_files, "_verify_token_param"),
                patch.object(recipe_files, "get_db", return_value=Connection()),
            ):
                inline = recipe_files.get_pdf("recipe-1", object())
                download = recipe_files.download_recipe("recipe-1", object())

            pdf.write_bytes(b"%PDF-replaced")
            self.assertNotEqual(Path(inline.path), pdf)
            self.assertNotEqual(Path(download.path), pdf)
            self.assertEqual(Path(inline.path).read_bytes(), b"%PDF-original")
            self.assertEqual(Path(download.path).read_bytes(), b"%PDF-original")
            asyncio.run(inline.background())
            asyncio.run(download.background())

    def test_generated_pdf_invalidation_does_not_remove_manual_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            pdf = recipe_dir / "recipe.pdf"
            pdf.write_bytes(b"manual")

            self.assertFalse(recipe_files._invalidate_generated_pdf(recipe_dir))
            self.assertTrue(pdf.exists())

            (recipe_dir / ".generated-pdf.json").write_text("{}", encoding="utf-8")
            pages_dir = recipe_dir / "pdf-pages"
            pages_dir.mkdir()
            self._image(pages_dir / "page-001.jpg", (0, 0, 0))

            self.assertFalse(recipe_files._invalidate_generated_pdf(recipe_dir))
            self.assertTrue(pdf.exists())
            self.assertTrue(pages_dir.exists())

    def test_partial_backup_failure_leaves_existing_generated_artifacts_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            self._image(recipe_dir / "first.jpg", (255, 0, 0))
            recipe_files._convert_images_to_pdf(recipe_dir, ["first.jpg"])
            recipe_files._write_generated_pdf_manifest(recipe_dir, ["first.jpg"])
            pages_dir = recipe_dir / "pdf-pages"
            pages_dir.mkdir()
            self._image(pages_dir / "page-001.jpg", (0, 0, 0))
            self._bind_pdf_pages(recipe_dir)
            before = {
                "pdf": _sha256(recipe_dir / "recipe.pdf"),
                "manifest": _sha256(recipe_dir / ".generated-pdf.json"),
                "page": _sha256(pages_dir / "page-001.jpg"),
            }
            real_copy2 = shutil.copy2
            calls = 0

            def fail_second_copy(src, dst, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected backup failure")
                return real_copy2(src, dst, *args, **kwargs)

            with patch.object(recipe_files.shutil, "copy2", side_effect=fail_second_copy):
                with self.assertRaisesRegex(OSError, "injected backup failure"):
                    recipe_files._create_generated_pdf_backup(recipe_dir)

            self.assertEqual(before["pdf"], _sha256(recipe_dir / "recipe.pdf"))
            self.assertEqual(before["manifest"], _sha256(recipe_dir / ".generated-pdf.json"))
            self.assertEqual(before["page"], _sha256(pages_dir / "page-001.jpg"))
            self.assertEqual(list(recipe_dir.glob(".pdf-conversion-backup-*")), [])

    def test_failed_restore_retains_complete_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            self._image(recipe_dir / "first.jpg", (255, 0, 0))
            recipe_files._convert_images_to_pdf(recipe_dir, ["first.jpg"])
            recipe_files._write_generated_pdf_manifest(recipe_dir, ["first.jpg"])
            backup = recipe_files._create_generated_pdf_backup(recipe_dir)
            if backup is None:
                self.fail("Expected a generated PDF backup")

            with patch.object(recipe_files.os, "replace", side_effect=OSError("injected restore failure")):
                self.assertFalse(recipe_files._restore_generated_pdf_backup(recipe_dir, backup))

            self.assertTrue(backup.is_dir())
            self.assertTrue(recipe_files._generated_manifest_matches_pdf(backup))

    def test_partial_restore_failure_removes_mixed_live_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_dir = Path(tmp)
            self._image(recipe_dir / "first.jpg", (255, 0, 0))
            recipe_files._convert_images_to_pdf(recipe_dir, ["first.jpg"])
            recipe_files._write_generated_pdf_manifest(recipe_dir, ["first.jpg"])
            pages_dir = recipe_dir / "pdf-pages"
            pages_dir.mkdir()
            self._image(pages_dir / "page-001.jpg", (0, 0, 0))
            self._bind_pdf_pages(recipe_dir)
            backup = recipe_files._create_generated_pdf_backup(recipe_dir)
            if backup is None:
                self.fail("Expected a generated PDF backup")

            (recipe_dir / "recipe.pdf").write_bytes(b"%PDF-new-partial")
            (recipe_dir / recipe_files.GENERATED_PDF_MANIFEST).write_text("{}", encoding="utf-8")
            self._image(pages_dir / "page-001.jpg", (0, 255, 0))
            real_replace = recipe_files.os.replace

            def fail_manifest_publish(src, dst):
                if Path(dst) == recipe_dir / recipe_files.GENERATED_PDF_MANIFEST:
                    raise OSError("injected partial restore failure")
                return real_replace(src, dst)

            with patch.object(recipe_files.os, "replace", side_effect=fail_manifest_publish):
                self.assertFalse(recipe_files._restore_generated_pdf_backup(recipe_dir, backup))

            self.assertFalse((recipe_dir / "recipe.pdf").exists())
            self.assertFalse((recipe_dir / recipe_files.GENERATED_PDF_MANIFEST).exists())
            self.assertFalse((recipe_dir / recipe_files.PDF_PAGES_DIR).exists())
            self.assertTrue(recipe_files._generated_manifest_matches_pdf(backup))


if __name__ == "__main__":
    unittest.main()
