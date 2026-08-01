"""Recipe file, image, PDF, thumbnail, and text-version handlers."""
from app.core.foundation import *
from app.auth.service import get_current_user, require_admin, _verify_token_param
import threading
import hmac
import functools
import asyncio
from starlette.background import BackgroundTask

GENERATED_PDF_MANIFEST = ".generated-pdf.json"
PDF_PAGES_DIR = "pdf-pages"
PDF_PAGES_MANIFEST = ".pdf-identity.json"
MAX_IMAGE_PDF_PAGES = 80
MAX_IMAGE_PDF_SOURCE_PIXELS = 50_000_000
MAX_IMAGE_PDF_PIXELS = 80_000_000
MAX_ADD_IMAGE_FILES = 80
MAX_ADD_IMAGE_TOTAL_BYTES = 200 * 1024 * 1024
MAX_PDF_RENDER_PAGES = 200
MAX_PDF_RENDER_OUTPUT_BYTES = 500 * 1024 * 1024
MAX_PDF_RENDER_DECODED_PIXELS = 300_000_000
MAX_PDF_RENDER_TEMP_BYTES = 1024 * 1024 * 1024
MAX_PDF_RENDER_SECONDS = 120
IMAGE_PDF_CONVERSION_LOCK = threading.RLock()


def _serialized_recipe_source_mutation(func):
    """Serialize source mutations with generated-PDF conversion/publication."""
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        with IMAGE_PDF_CONVERSION_LOCK:
            return func(*args, **kwargs)
    return wrapped


def _source_image_names(recipe_dir: Path, image_order_json: str = "") -> list[str]:
    """Return editable source images in their saved display order."""
    if not recipe_dir.exists():
        return []
    image_names = sorted(
        path.name
        for path in recipe_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTS
        and path.name != "thumbnail.jpg"
    )
    if not image_order_json:
        return image_names
    try:
        saved_order = json.loads(image_order_json)
        if not isinstance(saved_order, list):
            return image_names
        existing = set(image_names)
        ordered = [name for name in saved_order if isinstance(name, str) and name in existing]
        ordered_set = set(ordered)
        ordered.extend(name for name in image_names if name not in ordered_set)
        return ordered
    except (TypeError, json.JSONDecodeError):
        return image_names


def _discover_pdf_pages(recipe_dir: Path) -> list[Path]:
    """Return only page artifacts bound to the current PDF identity."""
    with IMAGE_PDF_CONVERSION_LOCK:
        isolated_dir = recipe_dir / PDF_PAGES_DIR
        if isolated_dir.is_dir():
            if not _pdf_page_dir_matches_pdf(recipe_dir, isolated_dir):
                return []
            return sorted(isolated_dir.glob("page-*.jpg"))
        if not _pdf_page_dir_matches_pdf(recipe_dir, recipe_dir):
            return []
        return sorted(recipe_dir.glob("page-*.jpg"))


def _normalise_pdf_page(path: Path):
    from PIL import Image as PILImage, ImageOps

    try:
        with PILImage.open(path) as source:
            if source.width * source.height > MAX_IMAGE_PDF_SOURCE_PIXELS:
                raise ValueError(f"Could not read image {path.name}: source image is too large")
            source.draft("RGB", (2200, 3100))
            image = ImageOps.exif_transpose(source)
            if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                flattened = PILImage.new("RGB", rgba.size, "white")
                flattened.paste(rgba, mask=rgba.getchannel("A"))
                image = flattened
            else:
                image = image.convert("RGB")
            image.thumbnail((2200, 3100), PILImage.Resampling.LANCZOS)
            return image.copy()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not read image {path.name}: {exc}") from exc


def _convert_images_to_pdf(recipe_dir: Path, image_names: list[str]) -> Path:
    """Build recipe.pdf atomically from ordered source images."""
    if not image_names:
        raise ValueError("No source images found")
    if len(image_names) > MAX_IMAGE_PDF_PAGES:
        raise ValueError(f"A PDF can contain at most {MAX_IMAGE_PDF_PAGES} pages")
    temp_pdf = recipe_dir / "recipe.pdf.tmp"
    final_pdf = recipe_dir / "recipe.pdf"
    pages = []
    total_pixels = 0
    try:
        for name in image_names:
            safe_name = Path(name).name
            if safe_name != name or Path(name).suffix.lower() not in IMAGE_EXTS:
                raise ValueError(f"Invalid image filename: {name}")
            path = recipe_dir / safe_name
            if not path.is_file():
                raise ValueError(f"Image not found: {safe_name}")
            page = _normalise_pdf_page(path)
            total_pixels += page.width * page.height
            if total_pixels > MAX_IMAGE_PDF_PIXELS:
                page.close()
                raise ValueError("Recipe images are too large to convert safely")
            pages.append(page)
        pages[0].save(
            temp_pdf,
            format="PDF",
            save_all=True,
            append_images=pages[1:],
            resolution=150,
            quality=92,
        )
        with temp_pdf.open("rb") as handle:
            os.fsync(handle.fileno())
        from pdf2image import pdfinfo_from_path
        page_count = int(pdfinfo_from_path(str(temp_pdf)).get("Pages", 0))
        if page_count != len(pages):
            raise ValueError(f"Generated PDF has {page_count} pages; expected {len(pages)}")
        os.replace(temp_pdf, final_pdf)
        return final_pdf
    except Exception:
        temp_pdf.unlink(missing_ok=True)
        raise
    finally:
        for page in pages:
            page.close()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pdf_identity(pdf_path: Path) -> dict:
    stat = pdf_path.stat()
    return {"sha256": _file_sha256(pdf_path), "size": stat.st_size}


def _pdf_page_dir_matches_pdf(recipe_dir: Path, pages_dir: Path) -> bool:
    manifest = pages_dir / PDF_PAGES_MANIFEST
    pdf_path = recipe_dir / "recipe.pdf"
    if not manifest.is_file() or not pdf_path.is_file():
        return False
    try:
        expected = json.loads(manifest.read_text(encoding="utf-8"))
        return isinstance(expected, dict) and expected == _pdf_identity(pdf_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _generated_manifest_matches_pdf(recipe_dir: Path) -> bool:
    pdf_path = recipe_dir / "recipe.pdf"
    manifest_path = recipe_dir / GENERATED_PDF_MANIFEST
    if not pdf_path.is_file() or not manifest_path.is_file():
        return False
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        identity = payload.get("pdf_identity") if isinstance(payload, dict) else None
        if not isinstance(identity, dict):
            return False
        expected_hash = identity.get("sha256")
        expected_size = identity.get("size")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            return False
        if not isinstance(expected_size, int) or expected_size < 1:
            return False
        stat = pdf_path.stat()
        return stat.st_size == expected_size and hmac.compare_digest(_file_sha256(pdf_path), expected_hash)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _remove_generated_pdf_unlocked(recipe_dir: Path) -> bool:
    if not _generated_manifest_matches_pdf(recipe_dir):
        return False
    manifest = recipe_dir / GENERATED_PDF_MANIFEST
    (recipe_dir / "recipe.pdf").unlink(missing_ok=True)
    manifest.unlink(missing_ok=True)
    shutil.rmtree(recipe_dir / PDF_PAGES_DIR, ignore_errors=True)
    return True


def _invalidate_generated_pdf(recipe_dir: Path) -> bool:
    """Remove stale derived PDF assets, but never remove a manually supplied PDF."""
    with IMAGE_PDF_CONVERSION_LOCK:
        return _remove_generated_pdf_unlocked(recipe_dir)


def _write_generated_pdf_manifest(recipe_dir: Path, image_names: list[str]) -> None:
    fingerprint = hashlib.sha256()
    for name in image_names:
        path = recipe_dir / name
        stat = path.stat()
        fingerprint.update(f"{name}:{stat.st_size}:{stat.st_mtime_ns}|".encode())
    payload = {
        "source_fingerprint": fingerprint.hexdigest(),
        "pdf_identity": _pdf_identity(recipe_dir / "recipe.pdf"),
        "images": image_names,
        "generated_at": datetime.utcnow().isoformat(),
    }
    temp = recipe_dir / f"{GENERATED_PDF_MANIFEST}.tmp"
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp, recipe_dir / GENERATED_PDF_MANIFEST)


def _pdf_is_app_generated(recipe_dir: Path) -> bool:
    return _generated_manifest_matches_pdf(recipe_dir)


def _convert_pdf_to_pages(recipe_dir: Path):
    """Convert recipe.pdf to page-001.jpg, page-002.jpg, etc.
    Poppler writes directly into a staging directory so multi-page PDFs are not
    retained as a large list of decoded images in backend memory."""
    with IMAGE_PDF_CONVERSION_LOCK:
        return _convert_pdf_to_pages_unlocked(recipe_dir)


def _convert_pdf_to_pages_unlocked(recipe_dir: Path):
    pdf_path = recipe_dir / "recipe.pdf"
    if not pdf_path.exists():
        return []
    source_identity = _pdf_identity(pdf_path)
    temp_dir = None
    old_output = None
    try:
        from pdf2image import convert_from_path, pdfinfo_from_path
        output_dir = recipe_dir / PDF_PAGES_DIR
        page_count = int(pdfinfo_from_path(str(pdf_path)).get("Pages", 0))
        if page_count < 1 or page_count > MAX_PDF_RENDER_PAGES:
            return []
        temp_dir = recipe_dir / f".{PDF_PAGES_DIR}-{uuid.uuid4().hex}.tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        rendered_paths = convert_from_path(
            str(pdf_path),
            dpi=180,
            fmt="jpeg",
            jpegopt={"quality": 90},
            output_folder=str(temp_dir),
            output_file="rendered",
            paths_only=True,
            thread_count=1,
            timeout=MAX_PDF_RENDER_SECONDS,
        )
        for i, rendered_path in enumerate(rendered_paths):
            out = temp_dir / f"page-{i+1:03d}.jpg"
            os.replace(rendered_path, out)
            with out.open("rb") as f:
                f.flush()
                os.fsync(f.fileno())
        # Retry pages that are suspiciously small — indicates a blank render
        # from a poppler font-cache miss on first conversion.
        blank = [i+1 for i in range(len(rendered_paths)) if (temp_dir / f"page-{i+1:03d}.jpg").stat().st_size < 10_000]
        for page_num in blank:
            retry = convert_from_path(
                str(pdf_path), dpi=250, first_page=page_num, last_page=page_num,
                fmt="jpeg", timeout=MAX_PDF_RENDER_SECONDS,
            )
            if retry:
                out = temp_dir / f"page-{page_num:03d}.jpg"
                with open(str(out), "wb") as f:
                    retry[0].save(f, "JPEG", quality=90)
                    f.flush()
                    os.fsync(f.fileno())
        temp_bytes = sum(path.stat().st_size for path in temp_dir.iterdir() if path.is_file())
        output_bytes = sum(path.stat().st_size for path in temp_dir.glob("page-*.jpg"))
        decoded_pixels = 0
        from PIL import Image as PILImage
        for page_path in temp_dir.glob("page-*.jpg"):
            with PILImage.open(page_path) as image:
                decoded_pixels += image.width * image.height
        if (
            temp_bytes > MAX_PDF_RENDER_TEMP_BYTES
            or output_bytes > MAX_PDF_RENDER_OUTPUT_BYTES
            or decoded_pixels > MAX_PDF_RENDER_DECODED_PIXELS
        ):
            raise ValueError("Rendered PDF pages exceed resource limits")
        if not pdf_path.is_file() or _pdf_identity(pdf_path) != source_identity:
            raise RuntimeError("PDF changed while pages were being rendered")
        (temp_dir / PDF_PAGES_MANIFEST).write_text(json.dumps(source_identity), encoding="utf-8")
        old_output = recipe_dir / f".{PDF_PAGES_DIR}-{uuid.uuid4().hex}.old"
        if output_dir.exists():
            os.replace(output_dir, old_output)
        os.replace(temp_dir, output_dir)
        shutil.rmtree(old_output, ignore_errors=True)
        print(f"PDF converted: {len(rendered_paths)} pages → {output_dir}")
        return sorted(output_dir.glob("page-*.jpg"))
    except Exception as e:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)
        if old_output is not None and old_output.exists() and not (recipe_dir / PDF_PAGES_DIR).exists():
            os.replace(old_output, recipe_dir / PDF_PAGES_DIR)
        print(f"PDF conversion failed: {e}")
        return []


def _pdf_pages_signature(path: Path) -> list[tuple[str, int]]:
    if not path.is_dir():
        return []
    return [(page.name, page.stat().st_size) for page in sorted(path.glob("page-*.jpg"))]


def _create_generated_pdf_backup(recipe_dir: Path) -> Optional[Path]:
    """Create and verify a complete backup before exposing it to rollback code."""
    if not _pdf_is_app_generated(recipe_dir):
        return None
    staging = recipe_dir / f".pdf-conversion-backup-{uuid.uuid4().hex}.tmp"
    backup = recipe_dir / staging.name.removesuffix(".tmp")
    try:
        staging.mkdir()
        shutil.copy2(recipe_dir / "recipe.pdf", staging / "recipe.pdf")
        shutil.copy2(recipe_dir / GENERATED_PDF_MANIFEST, staging / GENERATED_PDF_MANIFEST)
        pages = recipe_dir / PDF_PAGES_DIR
        if pages.is_dir():
            shutil.copytree(pages, staging / PDF_PAGES_DIR)
        if not _generated_manifest_matches_pdf(staging):
            raise RuntimeError("Generated PDF backup identity verification failed")
        if _pdf_pages_signature(pages) != _pdf_pages_signature(staging / PDF_PAGES_DIR):
            raise RuntimeError("Generated PDF page backup verification failed")
        if pages.is_dir() and not _pdf_page_dir_matches_pdf(staging, staging / PDF_PAGES_DIR):
            raise RuntimeError("Generated PDF page identity backup verification failed")
        os.replace(staging, backup)
        return backup
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _restore_generated_pdf_backup(recipe_dir: Path, backup: Path) -> bool:
    """Restore from a verified staging copy; retain backup on any failure."""
    staging = recipe_dir / f".pdf-conversion-restore-{uuid.uuid4().hex}.tmp"
    old_pages = recipe_dir / f".{PDF_PAGES_DIR}-{uuid.uuid4().hex}.restore-old"
    try:
        shutil.copytree(backup, staging)
        if not _generated_manifest_matches_pdf(staging):
            raise RuntimeError("Generated PDF restore identity verification failed")
        expected_pages = _pdf_pages_signature(staging / PDF_PAGES_DIR)
        os.replace(staging / "recipe.pdf", recipe_dir / "recipe.pdf")
        os.replace(staging / GENERATED_PDF_MANIFEST, recipe_dir / GENERATED_PDF_MANIFEST)
        output_pages = recipe_dir / PDF_PAGES_DIR
        if output_pages.exists():
            os.replace(output_pages, old_pages)
        if (staging / PDF_PAGES_DIR).is_dir():
            os.replace(staging / PDF_PAGES_DIR, output_pages)
        if not _generated_manifest_matches_pdf(recipe_dir):
            raise RuntimeError("Restored generated PDF identity does not match")
        if expected_pages != _pdf_pages_signature(output_pages):
            raise RuntimeError("Restored generated PDF pages do not match")
        if output_pages.is_dir() and not _pdf_page_dir_matches_pdf(recipe_dir, output_pages):
            raise RuntimeError("Restored generated PDF page identity does not match")
        shutil.rmtree(old_pages, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
        return True
    except Exception as exc:
        # A restore spans three filesystem entries and cannot be published as
        # one atomic rename. If any publication step fails, expose none of the
        # set rather than a PDF, manifest, and pages from different identities.
        (recipe_dir / "recipe.pdf").unlink(missing_ok=True)
        (recipe_dir / GENERATED_PDF_MANIFEST).unlink(missing_ok=True)
        shutil.rmtree(recipe_dir / PDF_PAGES_DIR, ignore_errors=True)
        shutil.rmtree(old_pages, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
        print(f"Generated PDF rollback backup retained at {backup}: {exc}")
        return False


def _rollback_generated_pdf_conversion(recipe_dir: Path, backup: Optional[Path]) -> None:
    if backup is not None:
        if _restore_generated_pdf_backup(recipe_dir, backup):
            shutil.rmtree(backup, ignore_errors=True)
        return
    (recipe_dir / "recipe.pdf").unlink(missing_ok=True)
    (recipe_dir / GENERATED_PDF_MANIFEST).unlink(missing_ok=True)
    shutil.rmtree(recipe_dir / PDF_PAGES_DIR, ignore_errors=True)


def _generate_thumbnail(recipe_dir: Path, file_type: str) -> str:
    thumb = recipe_dir / "thumbnail.jpg"
    try:
        if file_type == "pdf":
            from pdf2image import convert_from_path
            pdf = next(recipe_dir.glob("*.pdf"), None)
            if pdf:
                pages = convert_from_path(str(pdf), first_page=1, last_page=1, dpi=150)
                if pages:
                    pages[0].save(str(thumb), "JPEG", quality=85)
                    return "thumbnail.jpg"
        else:
            # Use iterdir + suffix.lower() so files with uppercase extensions
            # (e.g. .JPG, .PNG from cameras/scanners) are found on Linux where
            # glob() is case-sensitive.
            all_images = sorted(
                f for f in recipe_dir.iterdir()
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS and f.name != "thumbnail.jpg"
            )
            candidates = all_images[:1]
            if candidates:
                    from PIL import Image, ImageOps
                    img = Image.open(candidates[0])
                    img = ImageOps.exif_transpose(img)  # honour camera rotation metadata
                    img = img.convert("RGB")             # strip alpha so JPEG save works
                    img.thumbnail((400, 400))
                    img.save(str(thumb), "JPEG", quality=85)
                    return "thumbnail.jpg"
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")
    return ""



def _image_file_for_recipe(recipe_id: str, filename: str) -> tuple[Path, str]:
    safe_name = Path(filename).name
    if not safe_name or Path(safe_name).suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Invalid image filename")
    path = DATA_DIR / recipe_id / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return path, safe_name


def _ensure_image_recipe(recipe_id: str, conn) -> sqlite3.Row:
    recipe = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if recipe["file_type"] != "images":
        raise HTTPException(status_code=400, detail="Recipe is not an image-type recipe")
    return recipe



def get_thumbnail(recipe_id: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    thumb = DATA_DIR / recipe_id / "thumbnail.jpg"
    if thumb.exists():
        # no-cache: browser must revalidate with the server before using a
        # cached copy. FileResponse already sends ETag/Last-Modified, so if
        # the file hasn't changed the browser gets a fast 304 Not Modified.
        # This ensures a newly set cover image is always picked up immediately.
        return FileResponse(
            str(thumb),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"},
        )
    raise HTTPException(status_code=404, detail="Thumbnail not found")


def _pdf_snapshot_response(pdf_path: Path, media_type: str, headers: Optional[dict] = None) -> FileResponse:
    """Serve an immutable PDF copy so lazy response reads cannot race replacement."""
    snapshot_dir = None
    try:
        with IMAGE_PDF_CONVERSION_LOCK:
            if not pdf_path.is_file():
                raise HTTPException(status_code=404, detail="PDF not found")
            snapshot_dir = Path(tempfile.mkdtemp(prefix="knitting-pdf-download-"))
            snapshot = snapshot_dir / "recipe.pdf"
            shutil.copy2(pdf_path, snapshot)
        return FileResponse(
            str(snapshot),
            media_type=media_type,
            headers=headers,
            background=BackgroundTask(shutil.rmtree, snapshot_dir, ignore_errors=True),
        )
    except Exception:
        if snapshot_dir is not None:
            shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise


def get_pdf(recipe_id: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    pdf = DATA_DIR / recipe_id / "recipe.pdf"
    return _pdf_snapshot_response(pdf, media_type="application/pdf")


def get_image(recipe_id: str, filename: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    safe = Path(filename).name          # strip any path traversal attempt
    path = DATA_DIR / recipe_id / safe
    if path.exists():
        return FileResponse(str(path))
    raise HTTPException(status_code=404, detail="Image not found")


def get_pdf_pages(recipe_id: str, current_user: dict = Depends(get_current_user)):
    pages = _discover_pdf_pages(DATA_DIR / recipe_id)
    return {"pages": [p.name for p in pages]}


def convert_pdf(recipe_id: str, current_user: dict = Depends(get_current_user)):
    """Manually trigger PDF-to-pages conversion (for recipes uploaded before this feature)."""
    recipe_dir = DATA_DIR / recipe_id
    if not (recipe_dir / "recipe.pdf").exists():
        raise HTTPException(status_code=404, detail="No PDF found for this recipe")
    _convert_pdf_to_pages(recipe_dir)
    pages = _discover_pdf_pages(recipe_dir)
    return {"pages": [p.name for p in pages]}


def convert_images_to_pdf(recipe_id: str, current_user: dict = Depends(get_current_user)):
    """Create a non-destructive PDF from an image recipe's saved page order."""
    conn = get_db()
    lock_acquired = False
    conversion_started = False
    backup_dir = None
    recipe_dir = DATA_DIR / recipe_id
    try:
        lock_acquired = IMAGE_PDF_CONVERSION_LOCK.acquire(blocking=False)
        if not lock_acquired:
            raise HTTPException(status_code=429, detail="Another image-to-PDF conversion is already running")

        row = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recipe not found")
        if row["file_type"] != "images":
            raise HTTPException(status_code=400, detail="Recipe is not image-based")
        image_names = _source_image_names(recipe_dir, row["image_order"] or "")
        if not image_names:
            raise HTTPException(status_code=400, detail="No source images found")

        if (recipe_dir / "recipe.pdf").is_file() and not _pdf_is_app_generated(recipe_dir):
            raise HTTPException(status_code=409, detail="This recipe has a manually supplied PDF that will not be overwritten")
        backup_dir = _create_generated_pdf_backup(recipe_dir)

        conversion_started = True
        try:
            _convert_images_to_pdf(recipe_dir, image_names)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        pages = _convert_pdf_to_pages(recipe_dir)
        if len(pages) != len(image_names):
            raise RuntimeError("Could not render every generated PDF page")
        _write_generated_pdf_manifest(recipe_dir, image_names)
        from app.recipes.repository import _get_recipe_full
        recipe = _get_recipe_full(recipe_id, conn, current_user)
        if backup_dir is not None:
            shutil.rmtree(backup_dir, ignore_errors=True)
            backup_dir = None
        return {"status": "converted", "recipe": recipe, "pages": [p.name for p in pages]}
    except HTTPException:
        if conversion_started:
            _rollback_generated_pdf_conversion(recipe_dir, backup_dir)
            backup_dir = None
        raise
    except Exception as exc:
        if conversion_started:
            _rollback_generated_pdf_conversion(recipe_dir, backup_dir)
            backup_dir = None
        print(f"Image-to-PDF conversion failed for {recipe_id}: {exc}")
        raise HTTPException(status_code=500, detail="PDF conversion failed")
    finally:
        if lock_acquired:
            IMAGE_PDF_CONVERSION_LOCK.release()
        conn.close()


def _read_pdf_page_bytes(recipe_dir: Path, filename: str) -> Optional[bytes]:
    safe = Path(filename).name
    if not (safe.startswith("page-") and safe.endswith(".jpg")):
        return None
    with IMAGE_PDF_CONVERSION_LOCK:
        pages_dir = recipe_dir / PDF_PAGES_DIR
        if pages_dir.is_dir():
            if not _pdf_page_dir_matches_pdf(recipe_dir, pages_dir):
                return None
            path = pages_dir / safe
        else:
            path = recipe_dir / safe
        return path.read_bytes() if path.is_file() else None


def get_pdf_page_image(recipe_id: str, filename: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    page_data = _read_pdf_page_bytes(DATA_DIR / recipe_id, filename)
    if page_data is not None:
        return Response(content=page_data, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Page not found")


def set_thumbnail(recipe_id: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    """Set a custom thumbnail from a specific PDF page or image file."""
    conn = get_db()
    row = conn.execute("SELECT file_type FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")

    source   = data.get("source", "")   # "pdf_page" or "image"
    filename = Path(data.get("filename", "")).name  # sanitise — strip any path traversal

    recipe_dir = DATA_DIR / recipe_id
    src_path = recipe_dir / filename
    page_data = None
    if source == "pdf_page":
        page_data = _read_pdf_page_bytes(recipe_dir, filename)

    # Validate: file must exist in the recipe dir
    if source == "pdf_page" and page_data is None:
        raise HTTPException(status_code=400, detail="File not found in this recipe")
    if source != "pdf_page" and (not src_path.exists() or not src_path.is_file()):
        raise HTTPException(status_code=400, detail="File not found in this recipe")

    # For PDF pages, filename must match page-NNN.jpg pattern
    if source == "pdf_page" and not (filename.startswith("page-") and filename.endswith(".jpg")):
        raise HTTPException(status_code=400, detail="Invalid PDF page filename")

    # For images, extension must be an allowed image type
    if source == "image" and Path(filename).suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Invalid image file")

    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(page_data) if page_data is not None else str(src_path))
        img = ImageOps.exif_transpose(img)  # honour camera rotation metadata
        img = img.convert("RGB")
        img.thumbnail((600, 600))
        thumb_path = recipe_dir / "thumbnail.jpg"
        img.save(str(thumb_path), "JPEG", quality=88)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Thumbnail generation failed: {e}")

    # Increment thumbnail_version so clients with a cached old thumbnail
    # will see a different URL and fetch the new image.
    conn2 = get_db()
    conn2.execute(
        "UPDATE recipes SET thumbnail_version = thumbnail_version + 1 WHERE id = ?",
        (recipe_id,)
    )
    conn2.commit()
    new_version = conn2.execute(
        "SELECT thumbnail_version FROM recipes WHERE id = ?", (recipe_id,)
    ).fetchone()["thumbnail_version"]
    conn2.close()

    return {"message": "Thumbnail updated", "thumbnail_version": new_version}


@_serialized_recipe_source_mutation
def set_image_order(recipe_id: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    """Save a custom display order for image-type recipes."""
    order = data.get("order", [])
    if not isinstance(order, list) or not all(isinstance(n, str) for n in order):
        raise HTTPException(status_code=400, detail="order must be a list of strings")
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    conn.execute("UPDATE recipes SET image_order=? WHERE id=?", (json.dumps(order), recipe_id))
    conn.commit()
    conn.close()
    pdf_invalidated = _invalidate_generated_pdf(DATA_DIR / recipe_id)
    return {"status": "ok", "order": order, "pdf_invalidated": pdf_invalidated}


@_serialized_recipe_source_mutation
def delete_recipe_image(recipe_id: str, filename: str, current_user: dict = Depends(get_current_user)):
    """Delete a single image from an image-type recipe, update order, clear annotations, regenerate thumbnail."""
    safe_name = Path(filename).name  # strip any path traversal
    if not safe_name or Path(safe_name).suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Invalid image filename")

    img_path = DATA_DIR / recipe_id / safe_name
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    conn = get_db()
    recipe = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    if not recipe:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    if recipe["file_type"] != "images":
        conn.close()
        raise HTTPException(status_code=400, detail="Recipe is not an image-type recipe")

    # Delete the image file
    img_path.unlink(missing_ok=True)
    pdf_invalidated = _invalidate_generated_pdf(DATA_DIR / recipe_id)

    # Remove from image_order if present
    image_order_json = recipe["image_order"] or ""
    if image_order_json:
        try:
            saved_order = json.loads(image_order_json)
            new_order = [n for n in saved_order if n != safe_name]
            conn.execute("UPDATE recipes SET image_order=? WHERE id=?", (json.dumps(new_order), recipe_id))
        except Exception:
            pass

    # Clear annotations for this image
    conn.execute("DELETE FROM annotations WHERE recipe_id=? AND page_key=?", (recipe_id, safe_name))

    # Regenerate thumbnail from whatever images remain
    recipe_dir = DATA_DIR / recipe_id
    thumb = _generate_thumbnail(recipe_dir, "images")
    new_version = None
    if thumb:
        conn.execute(
            "UPDATE recipes SET thumbnail_path=?, thumbnail_version=thumbnail_version+1 WHERE id=?",
            (thumb, recipe_id)
        )
        row = conn.execute("SELECT thumbnail_version FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        new_version = row["thumbnail_version"] if row else None

    conn.commit()
    conn.close()
    return {"status": "deleted", "filename": safe_name, "thumbnail_version": new_version, "pdf_invalidated": pdf_invalidated}


def _commit_added_images(recipe_id: str, uploads: list[tuple[str, str, bytes]], current_user: dict):
    """Commit validated uploads in a worker thread under the conversion lock."""
    with IMAGE_PDF_CONVERSION_LOCK:
        conn = get_db()
        try:
            row = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Recipe not found")
            recipe = dict(row)
            if recipe["file_type"] != "images":
                raise HTTPException(status_code=400, detail="Recipe is not an image-type recipe")

            recipe_dir = DATA_DIR / recipe_id
            existing_order: list = []
            if recipe.get("image_order"):
                try:
                    existing_order = json.loads(recipe["image_order"])
                except (TypeError, json.JSONDecodeError):
                    existing_order = []

            added = []
            for base, ext, file_data in uploads:
                dest = f"{base}{ext}"
                counter = 1
                while (recipe_dir / dest).exists():
                    dest = f"{base}_{counter}{ext}"
                    counter += 1
                with open(recipe_dir / dest, "wb") as handle:
                    handle.write(file_data)
                added.append(dest)

            _remove_generated_pdf_unlocked(recipe_dir)
            new_order = existing_order + added
            thumb = _generate_thumbnail(recipe_dir, "images")
            new_version = (recipe.get("thumbnail_version") or 0) + 1
            conn.execute(
                "UPDATE recipes SET image_order=?, thumbnail_path=?, thumbnail_version=? WHERE id=?",
                (json.dumps(new_order), thumb, new_version, recipe_id)
            )
            conn.commit()
            from app.recipes.repository import _get_recipe_full
            return _get_recipe_full(recipe_id, conn, current_user)
        finally:
            conn.close()


async def add_images_to_recipe(
    recipe_id: str,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Append a bounded batch of image files to an existing image recipe."""
    if len(files) > MAX_ADD_IMAGE_FILES:
        raise HTTPException(status_code=413, detail=f"Too many image files; maximum is {MAX_ADD_IMAGE_FILES}")

    uploads = []
    total_bytes = 0
    for upload in files:
        filename = upload.filename or ""
        ext = Path(filename).suffix.lower()
        if ext not in IMAGE_EXTS:
            continue
        file_data = await upload.read()
        if len(file_data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large: {filename}")
        total_bytes += len(file_data)
        if total_bytes > MAX_ADD_IMAGE_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="Combined image total upload size is too large")
        if not _validate_file_magic(file_data, ext):
            raise HTTPException(status_code=400, detail=f"File content does not match extension: {filename}")
        uploads.append((Path(filename).stem.lower(), ext, file_data))

    if not uploads:
        raise HTTPException(status_code=400, detail="No valid image files were uploaded")

    # Lock acquisition and all synchronous filesystem/SQLite work run off-loop.
    return await asyncio.to_thread(_commit_added_images, recipe_id, uploads, current_user)


@_serialized_recipe_source_mutation
def rotate_image(recipe_id: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    """Rotate a single image 90° CW or CCW in place, then regenerate the thumbnail."""
    filename  = Path(data.get("filename", "")).name   # strip any path traversal
    direction = data.get("direction", "cw")           # "cw" or "ccw"

    if not filename or Path(filename).suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Invalid image filename")

    img_path = DATA_DIR / recipe_id / filename
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    try:
        from PIL import Image as PILImage, ImageOps
        img = PILImage.open(str(img_path))
        img = ImageOps.exif_transpose(img)   # normalise EXIF rotation first
        img = img.convert("RGB")
        # PIL rotate(): positive = CCW; use transpose for lossless 90° steps
        if direction == "cw":
            img = img.transpose(PILImage.ROTATE_270)
        else:
            img = img.transpose(PILImage.ROTATE_90)
        img.save(str(img_path), "JPEG", quality=95)
        pdf_invalidated = _invalidate_generated_pdf(DATA_DIR / recipe_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rotation failed: {e}")

    conn = get_db()
    # Annotations for this image will be misaligned after rotation — clear them
    conn.execute("DELETE FROM annotations WHERE recipe_id=? AND page_key=?", (recipe_id, filename))
    # Regenerate thumbnail (picks first image alphabetically; harmless if unchanged)
    recipe_dir = DATA_DIR / recipe_id
    thumb = _generate_thumbnail(recipe_dir, "images")
    new_version = None
    if thumb:
        conn.execute(
            "UPDATE recipes SET thumbnail_path=?, thumbnail_version=thumbnail_version+1 WHERE id=?",
            (thumb, recipe_id)
        )
        row = conn.execute("SELECT thumbnail_version FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        new_version = row["thumbnail_version"] if row else None
    conn.commit()
    conn.close()
    return {"status": "rotated", "filename": filename, "thumbnail_version": new_version, "pdf_invalidated": pdf_invalidated}


@_serialized_recipe_source_mutation
def crop_recipe_image(recipe_id: str, filename: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    """Perspective-correct crop a single image using 4 corner points, then regenerate the thumbnail.

    points: [[x0,y0],[x1,y1],[x2,y2],[x3,y3]] = TL, TR, BR, BL (in original image pixels).
    """
    import math
    filename = Path(filename).name  # strip any path traversal

    if not filename or Path(filename).suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Invalid image filename")

    img_path = DATA_DIR / recipe_id / filename
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    points = data.get("points", [])
    if len(points) != 4:
        raise HTTPException(status_code=400, detail="Exactly 4 points required")

    try:
        tl, tr, br, bl = [(float(p[0]), float(p[1])) for p in points]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid point coordinates")

    try:
        from PIL import Image as PILImage, ImageOps

        img = PILImage.open(str(img_path))
        img = ImageOps.exif_transpose(img)  # normalise EXIF rotation first
        img = img.convert("RGB")

        # Compute output dimensions as average of opposite edge lengths
        def dist(a, b):
            return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)

        out_w = int((dist(tl, tr) + dist(bl, br)) / 2)
        out_h = int((dist(tl, bl) + dist(tr, br)) / 2)
        out_w = max(1, out_w)
        out_h = max(1, out_h)

        # PIL QUAD transform: maps src quadrilateral → rectangular output
        # data order for QUAD: upper-left, lower-left, lower-right, upper-right (src coords)
        quad_data = (tl[0], tl[1], bl[0], bl[1], br[0], br[1], tr[0], tr[1])
        result = img.transform((out_w, out_h), PILImage.QUAD, quad_data, PILImage.BICUBIC)
        result.save(str(img_path), "JPEG", quality=95)
        pdf_invalidated = _invalidate_generated_pdf(DATA_DIR / recipe_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Crop failed: {e}")

    conn = get_db()
    # Annotations for this image will be misaligned after crop — clear them
    conn.execute("DELETE FROM annotations WHERE recipe_id=? AND page_key=?", (recipe_id, filename))
    # Regenerate thumbnail
    recipe_dir = DATA_DIR / recipe_id
    thumb = _generate_thumbnail(recipe_dir, "images")
    new_version = None
    if thumb:
        conn.execute(
            "UPDATE recipes SET thumbnail_path=?, thumbnail_version=thumbnail_version+1 WHERE id=?",
            (thumb, recipe_id)
        )
        row = conn.execute("SELECT thumbnail_version FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        new_version = row["thumbnail_version"] if row else None
    conn.commit()
    conn.close()
    return {"status": "cropped", "filename": filename, "thumbnail_version": new_version, "pdf_invalidated": pdf_invalidated}


@_serialized_recipe_source_mutation
def adjust_recipe_image(recipe_id: str, filename: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    """Apply non-geometric image quality adjustments and keep an original backup."""
    img_path, safe_name = _image_file_for_recipe(recipe_id, filename)
    conn = get_db()
    try:
        _ensure_image_recipe(recipe_id, conn)
    except HTTPException:
        conn.close()
        raise

    brightness = _clamped_float(data.get("brightness"), 0, -100, 100)
    contrast   = _clamped_float(data.get("contrast"), 0, -100, 100)
    gamma      = _clamped_float(data.get("gamma"), 1, 0.2, 3)
    saturation = _clamped_float(data.get("saturation"), 0, -100, 100)
    warmth     = _clamped_float(data.get("warmth"), 0, -100, 100)
    sharpness  = _clamped_float(data.get("sharpness"), 0, -100, 100)

    try:
        from PIL import Image as PILImage, ImageOps, ImageEnhance
        originals_dir = DATA_DIR / recipe_id / ".originals"
        originals_dir.mkdir(exist_ok=True)
        backup_path = originals_dir / safe_name
        if not backup_path.exists():
            shutil.copy2(img_path, backup_path)

        img = PILImage.open(str(img_path))
        img = ImageOps.exif_transpose(img).convert("RGB")
        if brightness:
            img = ImageEnhance.Brightness(img).enhance(1 + brightness / 100)
        if contrast:
            img = ImageEnhance.Contrast(img).enhance(1 + contrast / 100)
        if saturation:
            img = ImageEnhance.Color(img).enhance(max(0, 1 + saturation / 100))
        if sharpness:
            img = ImageEnhance.Sharpness(img).enhance(max(0, 1 + sharpness / 50))
        if warmth:
            r, g, b = img.split()
            factor = warmth / 100
            r = r.point(lambda i: max(0, min(255, i * (1 + 0.16 * factor))))
            b = b.point(lambda i: max(0, min(255, i * (1 - 0.16 * factor))))
            img = PILImage.merge("RGB", (r, g, b))
        if gamma != 1:
            inv = 1 / gamma
            table = [max(0, min(255, int(((i / 255) ** inv) * 255))) for i in range(256)]
            img = img.point(table * 3)
        img.save(str(img_path), "JPEG", quality=95)
        pdf_invalidated = _invalidate_generated_pdf(DATA_DIR / recipe_id)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Image adjustment failed: {e}")

    new_version = _bump_recipe_thumbnail(conn, recipe_id)
    conn.commit()
    conn.close()
    return {"status": "adjusted", "filename": safe_name, "thumbnail_version": new_version, "has_original": True, "pdf_invalidated": pdf_invalidated}


@_serialized_recipe_source_mutation
def restore_original_recipe_image(recipe_id: str, filename: str, current_user: dict = Depends(get_current_user)):
    """Restore an image from the original backup created by quality adjustments."""
    img_path, safe_name = _image_file_for_recipe(recipe_id, filename)
    backup_path = DATA_DIR / recipe_id / ".originals" / safe_name
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Original backup not found")
    conn = get_db()
    try:
        _ensure_image_recipe(recipe_id, conn)
        shutil.copy2(backup_path, img_path)
        pdf_invalidated = _invalidate_generated_pdf(DATA_DIR / recipe_id)
        new_version = _bump_recipe_thumbnail(conn, recipe_id)
        conn.commit()
    finally:
        conn.close()
    return {"status": "restored", "filename": safe_name, "thumbnail_version": new_version, "pdf_invalidated": pdf_invalidated}


def get_recipe_text_version(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    fingerprint = _source_fingerprint(recipe_id, conn)
    row = conn.execute("SELECT * FROM recipe_text_versions WHERE recipe_id=?", (recipe_id,)).fetchone()
    audit = conn.execute("SELECT * FROM recipe_text_generation_audits WHERE recipe_id=?", (recipe_id,)).fetchone()
    conn.close()
    data = _text_version_dict(row, fingerprint)
    data["generation_audit"] = _audit_dict(audit)
    return data


def save_recipe_text_version(recipe_id: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    content = str(data.get("content_markdown", ""))
    language = str(data.get("language", "") or current_user.get("language", ""))
    now = datetime.utcnow().isoformat()
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    fingerprint = _source_fingerprint(recipe_id, conn)
    conn.execute(
        "INSERT INTO recipe_text_versions (recipe_id,content_markdown,status,language,prompt,provider,model,source_fingerprint,generated_by,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(recipe_id) DO UPDATE SET content_markdown=excluded.content_markdown,status=excluded.status,language=excluded.language,source_fingerprint=excluded.source_fingerprint,generated_by=excluded.generated_by,updated_at=excluded.updated_at",
        (recipe_id, content, "ready", language, "", "manual", "", fingerprint, current_user["username"], now, now)
    )
    conn.execute("DELETE FROM recipe_text_generation_audits WHERE recipe_id=?", (recipe_id,))
    conn.commit()
    row = conn.execute("SELECT * FROM recipe_text_versions WHERE recipe_id=?", (recipe_id,)).fetchone()
    conn.close()
    return _text_version_dict(row, fingerprint)



def download_recipe(recipe_id: str, request: Request, token: Optional[str] = None):
    """Download the original recipe.
    PDF recipes → returns the PDF as a file attachment.
    Image recipes → streams all images as a ZIP archive.
    """
    _verify_token_param(request, token)
    conn = get_db()
    row = conn.execute("SELECT title, file_type FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")

    title     = row["title"]
    file_type = row["file_type"]
    # Build a safe filename (strip special characters)
    safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_") or "recipe"

    recipe_dir = DATA_DIR / recipe_id
    pdf_path = recipe_dir / "recipe.pdf"
    if pdf_path.is_file():
        return _pdf_snapshot_response(
            pdf_path,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.pdf"'},
        )
    else:
        # Image recipe — bundle all images into a ZIP
        # Use iterdir + suffix.lower() so files with uppercase extensions
        # (e.g. .JPG, .PNG from cameras/scanners) are found on Linux where
        # glob() is case-sensitive.
        image_names = _source_image_names(recipe_dir)
        images = [recipe_dir / name for name in image_names]
        if not images:
            raise HTTPException(status_code=404, detail="No images found")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for img in images:
                zf.write(str(img), img.name)
        buf.seek(0)
        zip_name = f"{safe_title}.zip"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
        )


# ── Project sessions ──────────────────────────────────────────────────────────


__all__ = [name for name in globals() if not name.startswith("__")]
