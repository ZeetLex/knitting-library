"""Instance-wide app branding, public metadata, and icon file handling."""
from app.core.foundation import *
from app.auth.service import require_admin

DEFAULT_APP_TITLE = "Knitting Library"
BRANDING_DIR = Path("/data/branding")
BRANDING_TITLE_KEY = "branding_app_title"
BRANDING_ICON_VERSION_KEY = "branding_icon_version"
BRANDING_ICON_SIZES = (32, 180, 192, 512)
MAX_BRANDING_ICON_BYTES = 5 * 1024 * 1024
ALLOWED_BRANDING_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


def _branding_settings() -> dict:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT key, value FROM app_settings WHERE key IN (?, ?)",
            (BRANDING_TITLE_KEY, BRANDING_ICON_VERSION_KEY),
        ).fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        conn.close()


def _set_branding_setting(key: str, value: str) -> None:
    conn = get_db()
    try:
        if value:
            conn.execute(
                "INSERT INTO app_settings (key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
        else:
            conn.execute("DELETE FROM app_settings WHERE key=?", (key,))
        conn.commit()
    finally:
        conn.close()


def _custom_icon_exists() -> bool:
    return all((BRANDING_DIR / f"icon-{size}.png").is_file() for size in BRANDING_ICON_SIZES)


def get_branding_payload() -> dict:
    settings = _branding_settings()
    title = settings.get(BRANDING_TITLE_KEY, "").strip() or DEFAULT_APP_TITLE
    version = settings.get(BRANDING_ICON_VERSION_KEY, "")
    has_custom_icon = bool(version and _custom_icon_exists())
    suffix = f"?v={version}" if has_custom_icon else ""
    return {
        "title": title,
        "has_custom_title": title != DEFAULT_APP_TITLE,
        "has_custom_icon": has_custom_icon,
        "version": version if has_custom_icon else "default",
        "icon_url": f"/api/branding/icon/512.png{suffix}" if has_custom_icon else "/brand-logo.png",
        "favicon_url": f"/api/branding/icon/32.png{suffix}" if has_custom_icon else "/favicon-32.png",
        "apple_touch_icon_url": f"/api/branding/icon/180.png{suffix}" if has_custom_icon else "/apple-touch-icon.png",
    }


def get_branding():
    return get_branding_payload()


def get_branding_icon(size: int):
    if size not in BRANDING_ICON_SIZES:
        raise HTTPException(status_code=404, detail="Icon size not found")
    custom_path = BRANDING_DIR / f"icon-{size}.png"
    if custom_path.is_file():
        path = custom_path
    else:
        defaults = {
            32: STATIC_DIR / "favicon-32.png",
            180: STATIC_DIR / "apple-touch-icon.png",
            192: STATIC_DIR / "favicon-192.png",
            512: STATIC_DIR / "brand-logo.png",
        }
        path = defaults[size]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Icon not found")
    return FileResponse(
        str(path),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


def get_branding_manifest():
    branding = get_branding_payload()
    title = branding["title"]
    version = branding["version"]
    suffix = f"?v={version}" if branding["has_custom_icon"] else ""
    icons = [
        {"src": f"/api/branding/icon/32.png{suffix}", "sizes": "32x32", "type": "image/png"},
        {"src": f"/api/branding/icon/192.png{suffix}", "sizes": "192x192", "type": "image/png"},
        {"src": f"/api/branding/icon/512.png{suffix}", "sizes": "512x512", "type": "image/png"},
        {"src": f"/api/branding/icon/180.png{suffix}", "sizes": "180x180", "type": "image/png"},
    ]
    return JSONResponse(
        {
            "name": title,
            "short_name": title[:30],
            "description": "Personal knitting pattern library",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#1a1a2e",
            "theme_color": "#1a1a2e",
            "icons": icons,
        },
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


def update_branding_title(data: dict = Body(...), admin: dict = Depends(require_admin)):
    raw_title = data.get("title", "")
    if not isinstance(raw_title, str):
        raise HTTPException(status_code=400, detail="Title must be text")
    title = raw_title.strip()
    if len(title) > 60:
        raise HTTPException(status_code=400, detail="Title must be 60 characters or fewer")
    _set_branding_setting(BRANDING_TITLE_KEY, "" if not title or title == DEFAULT_APP_TITLE else title)
    return get_branding_payload()


async def upload_branding_icon(
    icon: UploadFile = File(...),
    admin: dict = Depends(require_admin),
):
    if icon.content_type not in ALLOWED_BRANDING_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Use a PNG, JPEG, or WebP image")
    content = await icon.read(MAX_BRANDING_ICON_BYTES + 1)
    if len(content) > MAX_BRANDING_ICON_BYTES:
        raise HTTPException(status_code=413, detail="Icon must be 5 MB or smaller")
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
        source = Image.open(io.BytesIO(content))
        source.load()
        if source.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Unsupported image format")
        source = ImageOps.exif_transpose(source).convert("RGBA")
        if min(source.size) < 64 or max(source.size) > 4096:
            raise ValueError("Icon dimensions must be between 64 and 4096 pixels")
        source = ImageOps.fit(source, (512, 512), method=Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Invalid image") from exc

    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    temporary_paths = []
    try:
        for size in BRANDING_ICON_SIZES:
            resized = source if size == 512 else source.resize((size, size), Image.Resampling.LANCZOS)
            temp_path = BRANDING_DIR / f".icon-{size}-{uuid.uuid4().hex}.tmp"
            resized.save(str(temp_path), format="PNG", optimize=True)
            temporary_paths.append((temp_path, BRANDING_DIR / f"icon-{size}.png"))
        for temp_path, final_path in temporary_paths:
            os.replace(temp_path, final_path)
        _set_branding_setting(BRANDING_ICON_VERSION_KEY, uuid.uuid4().hex)
    finally:
        for temp_path, _ in temporary_paths:
            temp_path.unlink(missing_ok=True)
    return get_branding_payload()


def delete_branding_icon(admin: dict = Depends(require_admin)):
    for size in BRANDING_ICON_SIZES:
        (BRANDING_DIR / f"icon-{size}.png").unlink(missing_ok=True)
    _set_branding_setting(BRANDING_ICON_VERSION_KEY, "")
    return get_branding_payload()


def reset_branding(admin: dict = Depends(require_admin)):
    _set_branding_setting(BRANDING_TITLE_KEY, "")
    return delete_branding_icon(admin)


__all__ = [name for name in globals() if not name.startswith("__")]
