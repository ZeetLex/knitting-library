"""Recipe file, image, PDF, thumbnail, and text-version handlers."""
from app.core.foundation import *
from app.auth.service import get_current_user, require_admin, _verify_token_param

def _convert_pdf_to_pages(recipe_dir: Path):
    """Convert recipe.pdf to page-001.jpg, page-002.jpg, etc.
    Intentionally single-threaded so the function is fully synchronous —
    using thread_count>1 causes convert_from_path to return before worker
    threads finish writing files, creating a race condition."""
    pdf_path = recipe_dir / "recipe.pdf"
    if not pdf_path.exists():
        return
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(str(pdf_path), dpi=200, fmt="jpeg")
        for i, page in enumerate(pages):
            out = recipe_dir / f"page-{i+1:03d}.jpg"
            with open(str(out), "wb") as f:
                page.save(f, "JPEG", quality=90)
                f.flush()
                os.fsync(f.fileno())
        # Retry pages that are suspiciously small — indicates a blank render
        # from a poppler font-cache miss on first conversion.
        blank = [i+1 for i in range(len(pages)) if (recipe_dir / f"page-{i+1:03d}.jpg").stat().st_size < 10_000]
        for page_num in blank:
            retry = convert_from_path(str(pdf_path), dpi=250, first_page=page_num, last_page=page_num, fmt="jpeg")
            if retry:
                out = recipe_dir / f"page-{page_num:03d}.jpg"
                with open(str(out), "wb") as f:
                    retry[0].save(f, "JPEG", quality=90)
                    f.flush()
                    os.fsync(f.fileno())
        print(f"PDF converted: {len(pages)} pages → {recipe_dir}")
    except Exception as e:
        print(f"PDF conversion failed: {e}")


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


def get_pdf(recipe_id: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    pdf = DATA_DIR / recipe_id / "recipe.pdf"
    if pdf.exists():
        return FileResponse(str(pdf), media_type="application/pdf")
    raise HTTPException(status_code=404, detail="PDF not found")


def get_image(recipe_id: str, filename: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    safe = Path(filename).name          # strip any path traversal attempt
    path = DATA_DIR / recipe_id / safe
    if path.exists():
        return FileResponse(str(path))
    raise HTTPException(status_code=404, detail="Image not found")


def get_pdf_pages(recipe_id: str, current_user: dict = Depends(get_current_user)):
    pages = sorted((DATA_DIR / recipe_id).glob("page-*.jpg"))
    return {"pages": [p.name for p in pages]}


def convert_pdf(recipe_id: str, current_user: dict = Depends(get_current_user)):
    """Manually trigger PDF-to-pages conversion (for recipes uploaded before this feature)."""
    recipe_dir = DATA_DIR / recipe_id
    if not (recipe_dir / "recipe.pdf").exists():
        raise HTTPException(status_code=404, detail="No PDF found for this recipe")
    _convert_pdf_to_pages(recipe_dir)
    pages = sorted(recipe_dir.glob("page-*.jpg"))
    return {"pages": [p.name for p in pages]}


def get_pdf_page_image(recipe_id: str, filename: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    safe = Path(filename).name
    path = DATA_DIR / recipe_id / safe
    if path.exists() and safe.startswith("page-") and safe.endswith(".jpg"):
        return FileResponse(str(path), media_type="image/jpeg")
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
    src_path   = recipe_dir / filename

    # Validate: file must exist in the recipe dir
    if not src_path.exists() or not src_path.is_file():
        raise HTTPException(status_code=400, detail="File not found in this recipe")

    # For PDF pages, filename must match page-NNN.jpg pattern
    if source == "pdf_page" and not (filename.startswith("page-") and filename.endswith(".jpg")):
        raise HTTPException(status_code=400, detail="Invalid PDF page filename")

    # For images, extension must be an allowed image type
    if source == "image" and Path(filename).suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Invalid image file")

    try:
        from PIL import Image, ImageOps
        img = Image.open(str(src_path))
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
    return {"status": "ok", "order": order}


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
    return {"status": "deleted", "filename": safe_name, "thumbnail_version": new_version}


async def add_images_to_recipe(
    recipe_id: str,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Append one or more image files to an existing image-type recipe."""
    conn = get_db()
    row = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    recipe = dict(row)
    if recipe["file_type"] != "images":
        conn.close()
        raise HTTPException(status_code=400, detail="Recipe is not an image-type recipe")

    recipe_dir = DATA_DIR / recipe_id
    existing_order: list = []
    if recipe.get("image_order"):
        try:
            existing_order = json.loads(recipe["image_order"])
        except Exception:
            existing_order = []

    added = []
    for upload in files:
        ext = Path(upload.filename).suffix.lower()
        if ext not in IMAGE_EXTS:
            continue
        file_data = await upload.read()
        if len(file_data) > MAX_IMAGE_BYTES:
            conn.close()
            raise HTTPException(status_code=413, detail=f"File too large: {upload.filename}")
        if not _validate_file_magic(file_data, ext):
            conn.close()
            raise HTTPException(status_code=400, detail=f"File content does not match extension: {upload.filename}")
        # Normalise name, avoid collisions
        base = Path(upload.filename).stem.lower()
        dest = f"{base}{ext}"
        counter = 1
        while (recipe_dir / dest).exists():
            dest = f"{base}_{counter}{ext}"
            counter += 1
        with open(recipe_dir / dest, "wb") as f:
            f.write(file_data)
        added.append(dest)

    if not added:
        conn.close()
        raise HTTPException(status_code=400, detail="No valid image files were uploaded")

    new_order = existing_order + added
    thumb = _generate_thumbnail(recipe_dir, "images")
    new_version = (recipe.get("thumbnail_version") or 0) + 1
    conn.execute(
        "UPDATE recipes SET image_order=?, thumbnail_path=?, thumbnail_version=? WHERE id=?",
        (json.dumps(new_order), thumb, new_version, recipe_id)
    )
    conn.commit()
    result = _get_recipe_full(recipe_id, conn)
    conn.close()
    return result


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
    return {"status": "rotated", "filename": filename, "thumbnail_version": new_version}


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
    return {"status": "cropped", "filename": filename, "thumbnail_version": new_version}


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
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Image adjustment failed: {e}")

    new_version = _bump_recipe_thumbnail(conn, recipe_id)
    conn.commit()
    conn.close()
    return {"status": "adjusted", "filename": safe_name, "thumbnail_version": new_version, "has_original": True}


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
        new_version = _bump_recipe_thumbnail(conn, recipe_id)
        conn.commit()
    finally:
        conn.close()
    return {"status": "restored", "filename": safe_name, "thumbnail_version": new_version}


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

    if file_type == "pdf":
        pdf_path = DATA_DIR / recipe_id / "recipe.pdf"
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="PDF not found")
        return FileResponse(
            str(pdf_path),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.pdf"'},
        )
    else:
        # Image recipe — bundle all images into a ZIP
        # Use iterdir + suffix.lower() so files with uppercase extensions
        # (e.g. .JPG, .PNG from cameras/scanners) are found on Linux where
        # glob() is case-sensitive.
        recipe_dir = DATA_DIR / recipe_id
        images = sorted(
            f for f in recipe_dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS and f.name != "thumbnail.jpg"
        )
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
