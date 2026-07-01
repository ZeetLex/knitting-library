"""AI text review sessions, review assets, diagrams, legends, and chart review endpoints."""
from app.core.foundation import *
from app.auth.service import get_current_user, require_admin, _verify_token_param

def _review_asset_dir(recipe_id: str, session_id: str) -> Path:
    path = DATA_DIR / recipe_id / "review_assets" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _review_crop_box(crop: dict, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    x = int(_clamped_float(crop.get("x"), 0, 0, width - 1))
    y = int(_clamped_float(crop.get("y"), 0, 0, height - 1))
    w = int(_clamped_float(crop.get("width"), width - x, 1, width - x))
    h = int(_clamped_float(crop.get("height"), height - y, 1, height - y))
    return x, y, min(width, x + w), min(height, y + h)


def _review_crop_points(crop: dict, image_size: tuple[int, int]) -> list[tuple[float, float]] | None:
    raw = crop.get("points") if isinstance(crop, dict) else None
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    width, height = image_size
    points = []
    for point in raw:
        if not isinstance(point, dict):
            return None
        points.append((
            _clamped_float(point.get("x"), 0, 0, width),
            _clamped_float(point.get("y"), 0, 0, height),
        ))
    return points


def _perspective_coefficients(source: list[tuple[float, float]], target: list[tuple[float, float]]) -> list[float]:
    matrix = []
    for (sx, sy), (tx, ty) in zip(source, target):
        matrix.append([sx, sy, 1, 0, 0, 0, -tx * sx, -tx * sy, tx])
        matrix.append([0, 0, 0, sx, sy, 1, -ty * sx, -ty * sy, ty])

    # Small Gaussian elimination solver for the 8 perspective coefficients.
    for col in range(8):
        pivot = max(range(col, 8), key=lambda row: abs(matrix[row][col]))
        if abs(matrix[pivot][col]) < 1e-9:
            raise ValueError("Invalid perspective crop")
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        factor = matrix[col][col]
        matrix[col] = [value / factor for value in matrix[col]]
        for row in range(8):
            if row == col:
                continue
            factor = matrix[row][col]
            matrix[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(matrix[row], matrix[col])
            ]
    return [matrix[row][8] for row in range(8)]


def _perspective_crop(img, crop: dict):
    from PIL import Image
    import math

    points = _review_crop_points(crop, img.size)
    if not points:
        return None
    tl, tr, br, bl = points
    width_top = math.dist(tl, tr)
    width_bottom = math.dist(bl, br)
    height_left = math.dist(tl, bl)
    height_right = math.dist(tr, br)
    out_w = max(1, int(round(max(width_top, width_bottom))))
    out_h = max(1, int(round(max(height_left, height_right))))
    target = [(0, 0), (out_w, 0), (out_w, out_h), (0, out_h)]
    try:
        coeffs = _perspective_coefficients(target, points)
    except ValueError:
        return None
    return img.transform(
        (out_w, out_h),
        Image.Transform.PERSPECTIVE,
        coeffs,
        Image.Resampling.BICUBIC,
        fillcolor=(246, 246, 242),
    )


def _make_review_asset(
    recipe_id: str,
    session_id: str,
    page_path: Path,
    crop: dict,
    title: str = "",
    grid_columns: int = 0,
    grid_rows: int = 0,
    rotation: float = 0.0,
    grid_line_width: int = 1,
    kind: str = "diagram",
) -> str:
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter, ImageDraw, ImageFont

    img = ImageOps.exif_transpose(Image.open(page_path)).convert("RGB")
    box = _review_crop_box(crop, img.size)
    perspective_img = _perspective_crop(img, crop)
    if perspective_img is not None:
        crop_img = perspective_img
    elif kind == "diagram" and rotation:
        center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        deskewed = img.rotate(
            float(rotation),
            center=center,
            expand=False,
            fillcolor=(246, 246, 242),
            resample=Image.Resampling.BICUBIC,
        )
        crop_img = deskewed.crop(box)
    else:
        crop_img = img.crop(box)
    crop_img = ImageOps.autocontrast(crop_img)
    crop_img = ImageEnhance.Contrast(crop_img).enhance(1.18)
    crop_img = ImageEnhance.Sharpness(crop_img).enhance(1.25)
    crop_img = crop_img.filter(ImageFilter.SHARPEN)

    title = (title or ("Diagram" if kind == "diagram" else "Legend")).strip()
    if kind == "diagram":
        title_h = 44 if title else 0
        out = Image.new("RGB", (crop_img.width, crop_img.height + title_h), (255, 255, 255))
        draw = ImageDraw.Draw(out)
        if title_h:
            draw.rectangle((0, 0, out.width, title_h), fill=(248, 246, 241))
            try:
                font = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
            except Exception:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), title, font=font)
            draw.text(((out.width - (bbox[2] - bbox[0])) / 2, 12), title, fill=(30, 30, 30), font=font)
        out.paste(crop_img, (0, title_h))
        if grid_columns > 0 and grid_rows > 0:
            grid_top = title_h
            line_color = (45, 45, 45)
            line_width = max(1, int(grid_line_width or 1))
            for col in range(grid_columns + 1):
                x = round(col * crop_img.width / grid_columns)
                draw.line((x, grid_top, x, grid_top + crop_img.height), fill=line_color, width=line_width)
            for row in range(grid_rows + 1):
                y = grid_top + round(row * crop_img.height / grid_rows)
                draw.line((0, y, crop_img.width, y), fill=line_color, width=line_width)
    else:
        out = crop_img

    asset_name = f"{kind}-{uuid.uuid4().hex[:12]}.jpg"
    rel = f"review_assets/{session_id}/{asset_name}"
    path = _review_asset_dir(recipe_id, session_id) / asset_name
    out.save(path, "JPEG", quality=92)
    return rel


def _review_image_path(recipe_id: str, rel_path: str) -> Path:
    safe = Path(rel_path)
    if safe.is_absolute() or ".." in safe.parts:
        raise HTTPException(status_code=400, detail="Invalid review asset path")
    path = DATA_DIR / recipe_id / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="Review asset not found")
    return path


def _review_page_source(recipe_id: str, page_key: str, conn) -> Path:
    return _chart_source_for_recipe(recipe_id, page_key, conn)


def _review_page_dict(row: sqlite3.Row, diagrams: list[sqlite3.Row], legends: list[sqlite3.Row]) -> dict:
    page = dict(row)
    page["source_text"] = page.get("ocr_text", "")
    page["diagrams"] = [_review_diagram_dict(item) for item in diagrams if item["page_id"] == row["id"]]
    page["legends"] = [_review_legend_dict(item) for item in legends if item["page_id"] == row["id"]]
    return page


def _review_diagram_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    try:
        data["crop"] = json.loads(data.pop("crop_json") or "{}")
    except Exception:
        data["crop"] = {}
    data["grid_columns"] = int(data.get("grid_columns") or 0)
    data["grid_rows"] = int(data.get("grid_rows") or 0)
    data["rotation"] = float(data.get("rotation") or 0)
    return data


def _review_legend_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    try:
        data["crop"] = json.loads(data.pop("crop_json") or "{}")
    except Exception:
        data["crop"] = {}
    return data


def _review_session_dict(conn, session_row: sqlite3.Row) -> dict:
    pages = conn.execute("SELECT * FROM recipe_review_pages WHERE session_id=? ORDER BY page_order", (session_row["id"],)).fetchall()
    diagrams = conn.execute("SELECT * FROM recipe_review_diagrams WHERE session_id=? ORDER BY created_at", (session_row["id"],)).fetchall()
    legends = conn.execute("SELECT * FROM recipe_review_legends WHERE session_id=? ORDER BY created_at", (session_row["id"],)).fetchall()
    data = dict(session_row)
    data["pages"] = [_review_page_dict(page, diagrams, legends) for page in pages]
    data["page_count"] = len(pages)
    data["accepted_count"] = sum(1 for page in pages if page["status"] == "accepted")
    return data


async def _create_review_session_from_ai_pages(
    recipe_id: str,
    language: str,
    cfg: dict,
    username: str,
    job_id: str = "",
) -> dict:
    conn = get_db()
    fingerprint = _source_fingerprint(recipe_id, conn)
    max_pages = int(_clamped_float(cfg.get("ai_max_pages"), 8, 1, 30))
    timeout = int(_clamped_float(cfg.get("ai_timeout"), 600, 60, 1800))
    timeout = max(300, timeout)
    _require_ai_vision_config(cfg)
    if job_id:
        _update_ai_job(job_id, progress_stage="ai_pages", pages_sent=0)
    page_results, _usage, _prompt = await _scan_recipe_pages_with_ai(recipe_id, language, cfg, conn, max_pages, timeout, job_id)
    conn.close()

    now = datetime.utcnow().isoformat()
    session_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        "UPDATE recipe_review_sessions SET status='cancelled', updated_at=? WHERE recipe_id=? AND status IN ('ready_to_review','in_review','paused')",
        (now, recipe_id)
    )
    conn.execute(
        "INSERT INTO recipe_review_sessions (id,recipe_id,job_id,status,language,source_fingerprint,current_page_order,created_by,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (session_id, recipe_id, job_id, "ready_to_review", language, fingerprint, 1, username, now, now)
    )
    for page in page_results:
        conn.execute(
            "INSERT INTO recipe_review_pages (id,session_id,recipe_id,page_key,page_order,status,ocr_text,reviewed_text,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                session_id,
                recipe_id,
                page["page_key"],
                page["page_order"],
                "draft",
                page["source_text"],
                page["reviewed_text"],
                now,
                now,
            )
        )
    conn.commit()
    row = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    data = _review_session_dict(conn, row)
    conn.close()
    return data


def _delete_review_session_assets(recipe_id: str, session_id: str) -> None:
    asset_dir = DATA_DIR / recipe_id / "review_assets" / session_id
    if asset_dir.exists():
        shutil.rmtree(asset_dir, ignore_errors=True)


def _complete_review_session(session_id: str, username: str) -> dict:
    conn = get_db()
    session = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Review session not found")
    recipe_id = session["recipe_id"]
    pages = conn.execute("SELECT * FROM recipe_review_pages WHERE session_id=? ORDER BY page_order", (session_id,)).fetchall()
    diagrams = conn.execute("SELECT * FROM recipe_review_diagrams WHERE session_id=? ORDER BY page_key, created_at", (session_id,)).fetchall()
    legends = conn.execute("SELECT * FROM recipe_review_legends WHERE session_id=? ORDER BY page_key, created_at", (session_id,)).fetchall()
    if not pages:
        conn.close()
        raise HTTPException(status_code=400, detail="Review session has no pages")
    now = datetime.utcnow().isoformat()
    parts = []
    for page in pages:
        text = (page["reviewed_text"] or page["ocr_text"] or "").strip()
        if text:
            parts.append(text)
    if diagrams:
        parts.extend(["", "---", "", "## Diagrams"])
        for diagram in diagrams:
            title = diagram["title"] or "Diagram"
            parts.extend(["", f"### {title}", "", f"![{title}](/api/recipes/{recipe_id}/review-assets/{diagram['image_path']})"])
    if legends:
        parts.extend(["", "---", "", "## Legends"])
        for legend in legends:
            title = legend["title"] or "Legend"
            parts.extend(["", f"### {title}", "", f"![{title}](/api/recipes/{recipe_id}/review-assets/{legend['image_path']})"])
    content = "\n".join(parts).strip()
    fingerprint = _source_fingerprint(recipe_id, conn)
    conn.execute(
        "INSERT INTO recipe_text_versions (recipe_id,content_markdown,status,language,prompt,provider,model,source_fingerprint,generated_by,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(recipe_id) DO UPDATE SET content_markdown=excluded.content_markdown,status=excluded.status,language=excluded.language,prompt=excluded.prompt,provider=excluded.provider,model=excluded.model,source_fingerprint=excluded.source_fingerprint,generated_by=excluded.generated_by,updated_at=excluded.updated_at",
        (recipe_id, content, "ready", session["language"], "review_session", "reviewed_ai_scan", "", fingerprint, username, now, now)
    )
    conn.execute("UPDATE recipe_review_sessions SET status='completed', completed_at=?, updated_at=? WHERE id=?", (now, now, session_id))
    conn.commit()
    row = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    data = _review_session_dict(conn, row)
    conn.close()
    return data



def get_recipe_review_session(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM recipe_review_sessions WHERE recipe_id=? AND status IN ('ready_to_review','in_review','paused') ORDER BY updated_at DESC LIMIT 1",
        (recipe_id,)
    ).fetchone()
    if not row:
        conn.close()
        return {"exists": False}
    data = _review_session_dict(conn, row)
    data["exists"] = True
    conn.close()
    return data


async def start_recipe_review_session(recipe_id: str, data: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    language = str(data.get("language", "") or current_user.get("language", "en"))
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    cfg = _ai_settings(conn, reveal_secret=True)
    conn.close()
    if cfg.get("ai_enabled", "false").lower() != "true":
        raise HTTPException(status_code=400, detail="AI text recognition is not enabled")
    session = await _create_review_session_from_ai_pages(recipe_id, language, cfg, current_user["username"])
    session["exists"] = True
    return session


def save_review_page(session_id: str, page_id: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    text = str(data.get("reviewed_text", ""))
    status = str(data.get("status", "draft"))
    status = status if status in {"draft", "accepted"} else "draft"
    now = datetime.utcnow().isoformat()
    conn = get_db()
    page = conn.execute("SELECT * FROM recipe_review_pages WHERE id=? AND session_id=?", (page_id, session_id)).fetchone()
    if not page:
        conn.close()
        raise HTTPException(status_code=404, detail="Review page not found")
    conn.execute(
        "UPDATE recipe_review_pages SET reviewed_text=?, status=?, updated_at=? WHERE id=?",
        (text, status, now, page_id)
    )
    conn.execute(
        "UPDATE recipe_review_sessions SET status='in_review', current_page_order=?, updated_at=? WHERE id=? AND status!='completed'",
        (page["page_order"], now, session_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    data = _review_session_dict(conn, row)
    data["exists"] = True
    conn.close()
    return data


def pause_review_session(session_id: str, current_user: dict = Depends(get_current_user)):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    row = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Review session not found")
    conn.execute("UPDATE recipe_review_sessions SET status='paused', updated_at=? WHERE id=?", (now, session_id))
    conn.commit()
    row = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    data = _review_session_dict(conn, row)
    data["exists"] = True
    conn.close()
    return data


def cancel_review_session(session_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Review session not found")
    recipe_id = row["recipe_id"]
    conn.execute("DELETE FROM recipe_review_legends WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM recipe_review_diagrams WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM recipe_review_pages WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM recipe_review_sessions WHERE id=?", (session_id,))
    if row["job_id"]:
        conn.execute("UPDATE ai_text_jobs SET dismissed=1 WHERE id=?", (row["job_id"],))
    conn.commit()
    conn.close()
    _delete_review_session_assets(recipe_id, session_id)
    return {"status": "cancelled"}


def complete_review_session(session_id: str, current_user: dict = Depends(get_current_user)):
    data = _complete_review_session(session_id, current_user["username"])
    data["exists"] = True
    return data


def create_review_diagram(session_id: str, page_id: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    title = str(data.get("title") or "Diagram").strip()[:120] or "Diagram"
    crop = data.get("crop") if isinstance(data.get("crop"), dict) else {}
    grid_columns = int(_clamped_float(data.get("grid_columns"), 10, 1, 200))
    grid_rows = int(_clamped_float(data.get("grid_rows"), 10, 1, 200))
    rotation = float(_clamped_float(data.get("rotation"), 0, -45, 45))
    grid_line_width = int(_clamped_float(data.get("grid_line_width"), 1, 1, 8))
    now = datetime.utcnow().isoformat()
    conn = get_db()
    session = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    page = conn.execute("SELECT * FROM recipe_review_pages WHERE id=? AND session_id=?", (page_id, session_id)).fetchone()
    if not session or not page:
        conn.close()
        raise HTTPException(status_code=404, detail="Review session/page not found")
    page_path = _review_page_source(session["recipe_id"], page["page_key"], conn)
    rel_path = _make_review_asset(session["recipe_id"], session_id, page_path, crop, title, grid_columns, grid_rows, rotation, grid_line_width, "diagram")
    diagram_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO recipe_review_diagrams (id,session_id,page_id,recipe_id,page_key,title,image_path,crop_json,grid_columns,grid_rows,rotation,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (diagram_id, session_id, page_id, session["recipe_id"], page["page_key"], title, rel_path, json.dumps(crop), grid_columns, grid_rows, rotation, now, now)
    )
    conn.execute("UPDATE recipe_review_sessions SET status='in_review', updated_at=? WHERE id=?", (now, session_id))
    conn.commit()
    row = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    out = _review_session_dict(conn, row)
    out["exists"] = True
    conn.close()
    return out


def create_review_legend(session_id: str, page_id: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    title = str(data.get("title") or "Legend").strip()[:120] or "Legend"
    crop = data.get("crop") if isinstance(data.get("crop"), dict) else {}
    now = datetime.utcnow().isoformat()
    conn = get_db()
    session = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    page = conn.execute("SELECT * FROM recipe_review_pages WHERE id=? AND session_id=?", (page_id, session_id)).fetchone()
    if not session or not page:
        conn.close()
        raise HTTPException(status_code=404, detail="Review session/page not found")
    page_path = _review_page_source(session["recipe_id"], page["page_key"], conn)
    rel_path = _make_review_asset(session["recipe_id"], session_id, page_path, crop, title, 0, 0, 0, 1, "legend")
    legend_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO recipe_review_legends (id,session_id,page_id,recipe_id,page_key,title,image_path,crop_json,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (legend_id, session_id, page_id, session["recipe_id"], page["page_key"], title, rel_path, json.dumps(crop), now, now)
    )
    conn.execute("UPDATE recipe_review_sessions SET status='in_review', updated_at=? WHERE id=?", (now, session_id))
    conn.commit()
    row = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    out = _review_session_dict(conn, row)
    out["exists"] = True
    conn.close()
    return out


def get_review_asset(recipe_id: str, asset_path: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    path = _review_image_path(recipe_id, asset_path)
    return FileResponse(str(path), media_type="image/jpeg")


def get_recipe_charts(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    rows = conn.execute("SELECT * FROM recipe_charts WHERE recipe_id=? ORDER BY page_key, created_at", (recipe_id,)).fetchall()
    conn.close()
    return {"charts": [_chart_dict(row) for row in rows]}


def extract_recipe_charts(recipe_id: str, data: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    conn.close()
    raise HTTPException(status_code=410, detail="Automatic OCR chart extraction has been removed. Use the guided review image tools instead.")


def save_recipe_chart(recipe_id: str, chart_id: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    title = str(data.get("title") or "Chart").strip()[:120] or "Chart"
    cells = data.get("cells") if isinstance(data.get("cells"), list) else []
    cells = [[str(cell or ".")[:1] if str(cell or ".") != "" else "." for cell in row] for row in cells if isinstance(row, list)]
    rows = len(cells)
    columns = max((len(row) for row in cells), default=0)
    if rows < 1 or columns < 1:
        raise HTTPException(status_code=400, detail="Chart must contain at least one row and column")
    cells = [row + ["."] * (columns - len(row)) for row in cells]
    repeat_count = data.get("repeat_count")
    try:
        repeat_count = int(repeat_count) if repeat_count not in (None, "") else None
    except Exception:
        repeat_count = None
    palette = data.get("palette") if isinstance(data.get("palette"), list) else _chart_palette_for_cells(cells)
    chart_code = _chart_code(title, columns, rows, cells, repeat_count)
    now = datetime.utcnow().isoformat()
    conn = get_db()
    row = conn.execute("SELECT * FROM recipe_charts WHERE id=? AND recipe_id=?", (chart_id, recipe_id)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Chart not found")
    conn.execute(
        """
        UPDATE recipe_charts
        SET title=?, rows=?, columns=?, palette_json=?, cells_json=?, chart_code=?,
            repeat_count=?, generated_by='user_reviewed', updated_at=?
        WHERE id=? AND recipe_id=?
        """,
        (
            title,
            rows,
            columns,
            json.dumps(palette, ensure_ascii=False),
            json.dumps(cells, ensure_ascii=False),
            chart_code,
            repeat_count,
            now,
            chart_id,
            recipe_id,
        )
    )
    conn.commit()
    saved = conn.execute("SELECT * FROM recipe_charts WHERE id=? AND recipe_id=?", (chart_id, recipe_id)).fetchone()
    conn.close()
    return {"chart": _chart_dict(saved)}


def get_recipe_chart_source(recipe_id: str, chart_id: str, current_user: dict = Depends(get_current_user)):
    from PIL import Image, ImageOps

    conn = get_db()
    row = conn.execute("SELECT * FROM recipe_charts WHERE id=? AND recipe_id=?", (chart_id, recipe_id)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Chart not found")
    chart = _chart_dict(row)
    path = _chart_source_for_recipe(recipe_id, chart.get("page_key") or "", conn)
    conn.close()
    bbox = chart.get("source_bbox") or []
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if len(bbox) == 4:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        pad = 28
        crop_box = (max(0, x1 - pad), max(0, y1 - pad), min(img.width, x2 + pad), min(img.height, y2 + pad))
        img = img.crop(crop_box)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")

__all__ = [name for name in globals() if not name.startswith("__")]
