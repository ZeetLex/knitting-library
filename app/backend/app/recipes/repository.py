"""Recipe persistence, taxonomy, project state, annotations, import, and export workflows."""
from app.core.foundation import *
from app.auth.service import get_current_user, require_admin, _verify_token_param

def _slugify(title: str) -> str:
    """Convert a recipe title to a safe folder name.
    'My Cozy Socks Pattern!' -> 'my-cozy-socks-pattern'
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "recipe"


def _unique_recipe_dir(title: str):
    """Return (recipe_id, recipe_dir) using a slug-based folder name.
    If the slug is already taken, appends -2, -3, etc.
    """
    base = _slugify(title)
    candidate = base
    counter = 2
    while (DATA_DIR / candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate, DATA_DIR / candidate


def _hash_files(file_data_list: list) -> str:
    """SHA-256 fingerprint of a set of files (order-independent).
    Same files always produce the same hash regardless of upload order.
    """
    individual = sorted(hashlib.sha256(data).hexdigest() for data in file_data_list)
    combined = hashlib.sha256("".join(individual).encode()).hexdigest()
    return combined


def _prune_orphan_categories(conn):
    """Legacy no-op.

    Categories are now user-managed taxonomy items and must stay available even
    when no recipe currently uses them.
    """
    return


def _taxonomy_rows(conn, table: str, link_table: str, link_column: str, assigned_only: bool = False):
    join_type = "JOIN" if assigned_only else "LEFT JOIN"
    query = f"""
        SELECT x.name, COUNT(l.recipe_id) AS usage_count
        FROM {table} x
        {join_type} {link_table} l ON l.{link_column}=x.id
        GROUP BY x.id, x.name
        ORDER BY x.name
    """
    return conn.execute(query).fetchall()


def _taxonomy_names(conn, table: str, link_table: str, link_column: str, assigned_only: bool = False):
    return [r["name"] for r in _taxonomy_rows(conn, table, link_table, link_column, assigned_only)]


def _taxonomy_details(conn, table: str, link_table: str, link_column: str, assigned_only: bool = False):
    return [
        {"name": r["name"], "usage_count": int(r["usage_count"] or 0)}
        for r in _taxonomy_rows(conn, table, link_table, link_column, assigned_only)
    ]


def _add_taxonomy_item(conn, table: str, name: str):
    conn.execute(f"INSERT OR IGNORE INTO {table} (name) VALUES (?)", (name,))
    row = conn.execute(f"SELECT id, name FROM {table} WHERE name=?", (name,)).fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="Could not save taxonomy item")
    return row


def _delete_taxonomy_item(conn, table: str, link_table: str, link_column: str, name: str, label: str):
    row = conn.execute(f"SELECT id FROM {table} WHERE name=?", (name,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    usage = conn.execute(
        f"SELECT COUNT(DISTINCT recipe_id) AS value FROM {link_table} WHERE {link_column}=?",
        (row["id"],)
    ).fetchone()["value"]
    conn.execute(f"DELETE FROM {link_table} WHERE {link_column}=?", (row["id"],))
    conn.execute(f"DELETE FROM {table} WHERE id=?", (row["id"],))
    return int(usage or 0)


def _save_cats_tags(conn, recipe_id: str, categories: str, tags: str):
    for name in [c.strip() for c in categories.split(",") if c.strip()]:
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()
        if row:
            conn.execute("INSERT OR IGNORE INTO recipe_categories (recipe_id,category_id) VALUES (?,?)", (recipe_id, row["id"]))
    for name in [t.strip() for t in tags.split(",") if t.strip()]:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()

def _project_scope_is_global(current_user: Optional[dict], project_scope: str = "user") -> bool:
    return bool(current_user and current_user.get("is_admin")) or project_scope == "global"


def _project_owner_filter(current_user: Optional[dict], alias: str = "ps", project_scope: str = "user") -> tuple[str, list]:
    if _project_scope_is_global(current_user, project_scope) or not current_user:
        return "", []
    return f" AND {alias}.user_id=?", [current_user["id"]]


def _apply_project_status(recipe: dict, sessions: list[dict]) -> None:
    active = next((s for s in reversed(sessions) if not s["finished_at"]), None)
    latest_finished = next((s for s in reversed(sessions) if s["finished_at"]), None)
    recipe["active_session_id"] = None
    recipe["active_started_at"] = None
    recipe["active_user_id"] = None
    recipe["active_username"] = ""
    recipe["finished_session_id"] = None
    recipe["finished_at"] = None
    recipe["finished_user_id"] = None
    recipe["finished_username"] = ""
    if active:
        recipe["project_status"]    = "active"
        recipe["active_session_id"] = active["id"]
        recipe["active_started_at"] = active["started_at"]
        recipe["active_user_id"] = active.get("user_id")
        recipe["active_username"] = active.get("username", "") or ""
    elif latest_finished:
        recipe["project_status"] = "finished"
        recipe["finished_session_id"] = latest_finished["id"]
        recipe["finished_at"] = latest_finished["finished_at"]
        recipe["finished_user_id"] = latest_finished.get("user_id")
        recipe["finished_username"] = latest_finished.get("username", "") or ""
    else:
        recipe["project_status"] = "none"


def _get_recipe_full(recipe_id: str, conn, current_user: Optional[dict] = None, project_scope: str = "user") -> Optional[dict]:
    row = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    if not row:
        return None
    recipe = dict(row)
    recipe["categories"] = [r["name"] for r in conn.execute(
        "SELECT c.name FROM categories c JOIN recipe_categories rc ON c.id=rc.category_id WHERE rc.recipe_id=?",
        (recipe_id,)
    ).fetchall()]
    recipe["tags"] = [r["name"] for r in conn.execute(
        "SELECT t.name FROM tags t JOIN recipe_tags rt ON t.id=rt.tag_id WHERE rt.recipe_id=?",
        (recipe_id,)
    ).fetchall()]
    if recipe["file_type"] == "images":
        recipe_dir = DATA_DIR / recipe_id
        # Use iterdir + suffix.lower() so files with uppercase extensions
        # (e.g. .JPG, .PNG from cameras/scanners) are found on Linux where
        # glob() is case-sensitive.
        images = sorted(
            f for f in recipe_dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS and f.name != "thumbnail.jpg"
        ) if recipe_dir.exists() else []
        image_names = [f.name for f in images]
        # Apply custom order if saved
        image_order_json = recipe.get("image_order", "")
        if image_order_json:
            try:
                saved_order = json.loads(image_order_json)
                existing = set(image_names)
                # Start with saved order (skip any files that no longer exist)
                ordered = [n for n in saved_order if n in existing]
                # Append new files not yet in the saved order
                ordered += [n for n in image_names if n not in set(ordered)]
                image_names = ordered
            except Exception:
                pass  # Fall back to alphabetical on malformed JSON
        recipe["images"] = image_names
    else:
        recipe["images"] = []
    owner_sql, owner_params = _project_owner_filter(current_user, "ps", project_scope)
    sessions = conn.execute(
        """SELECT ps.id, ps.user_id, ps.username, ps.started_at, ps.finished_at, ps.yarn_id, ps.yarn_colour_id,
                  y.name as yarn_name, yc.name as yarn_colour
           FROM project_sessions ps
           LEFT JOIN yarns y        ON ps.yarn_id=y.id
           LEFT JOIN yarn_colours yc ON ps.yarn_colour_id=yc.id
           WHERE ps.recipe_id=?""" + owner_sql + " ORDER BY ps.started_at ASC",
        (recipe_id, *owner_params)
    ).fetchall()
    session_list = []
    for s in sessions:
        sd = dict(s)
        sd["feedback"] = [dict(f) for f in conn.execute(
            "SELECT id, user_id, username, rating_recipe, rating_difficulty, rating_result, notes, created_date FROM project_feedback WHERE session_id=?",
            (sd["id"],)
        ).fetchall()]
        session_list.append(sd)
    recipe["sessions"] = session_list
    feedback_owner_sql, feedback_owner_params = _project_owner_filter(current_user, "project_feedback", project_scope)
    all_fb = conn.execute(
        "SELECT rating_recipe, rating_difficulty, rating_result FROM project_feedback WHERE recipe_id=?" + feedback_owner_sql,
        (recipe_id, *feedback_owner_params)
    ).fetchall()
    if all_fb:
        total = sum(f["rating_recipe"] + f["rating_difficulty"] + f["rating_result"] for f in all_fb)
        recipe["avg_score"]      = round(total / (len(all_fb) * 3), 1)
        recipe["feedback_count"] = len(all_fb)
    else:
        recipe["avg_score"]      = None
        recipe["feedback_count"] = 0
    _apply_project_status(recipe, recipe["sessions"])
    return recipe



def _bump_recipe_thumbnail(conn, recipe_id: str) -> Optional[int]:
    recipe_dir = DATA_DIR / recipe_id
    thumb = _generate_thumbnail(recipe_dir, "images")
    if not thumb:
        return None
    conn.execute(
        "UPDATE recipes SET thumbnail_path=?, thumbnail_version=thumbnail_version+1 WHERE id=?",
        (thumb, recipe_id)
    )
    row = conn.execute("SELECT thumbnail_version FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    return row["thumbnail_version"] if row else None


def _clamped_float(value, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _source_fingerprint(recipe_id: str, conn) -> str:
    recipe = _get_recipe_full(recipe_id, conn)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    recipe_dir = DATA_DIR / recipe_id
    names = recipe["images"] if recipe["file_type"] == "images" else [p.name for p in sorted(recipe_dir.glob("page-*.jpg"))]
    parts = []
    for name in names:
        path = recipe_dir / name
        if path.exists():
            stat = path.stat()
            parts.append(f"{name}:{stat.st_size}:{int(stat.st_mtime)}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _text_version_dict(row: Optional[sqlite3.Row], current_fingerprint: str = "") -> dict:
    if not row:
        return {
            "exists": False,
            "content_markdown": "",
            "status": "empty",
            "is_outdated": False,
            "generation_audit": None,
        }
    data = dict(row)
    data["exists"] = bool(data.get("content_markdown"))
    data["is_outdated"] = bool(current_fingerprint and data.get("source_fingerprint") and data.get("source_fingerprint") != current_fingerprint)
    data["generation_audit"] = None
    return data


def _audit_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if not row:
        return None
    data = dict(row)
    for key in ("steps_json", "warnings_json"):
        try:
            data[key.replace("_json", "")] = json.loads(data.get(key) or "[]")
        except json.JSONDecodeError:
            data[key.replace("_json", "")] = []
        data.pop(key, None)
    for key in (
        "pages_processed", "ocr_chars", "ocr_words", "output_chars", "output_words",
        "provider_prompt_tokens", "provider_completion_tokens", "provider_total_tokens",
        "estimated_input_tokens", "estimated_image_tokens",
    ):
        if data.get(key) is not None:
            data[key] = int(data[key] or 0)
    if data.get("duration_seconds") is not None:
        data["duration_seconds"] = round(float(data["duration_seconds"]), 1)
    return data



def _get_recipes_summary(
    conn,
    ids: list[str],
    current_user: Optional[dict] = None,
    project_scope: str = "user",
    status_context: Optional[str] = None,
) -> list[dict]:
    """Fetch lightweight recipe summaries for the grid view.

    Instead of making 5+ queries per recipe (the old N+1 pattern), this
    fetches categories, tags and project-status for ALL recipes in 3 bulk
    queries and joins the data in Python.  For a library of 200 recipes that
    drops ~1000 DB round-trips down to ~3.
    """
    if not ids:
        return []

    placeholders = ",".join("?" * len(ids))

    # 1. Base recipe rows
    rows = conn.execute(
        f"SELECT id,title,description,file_type,thumbnail_path,thumbnail_version,created_date FROM recipes WHERE id IN ({placeholders})",
        ids
    ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    for d in by_id.values():
        d["categories"] = []
        d["tags"] = []
        d["project_status"] = "none"
        d["active_session_id"] = None
        d["active_started_at"] = None
        d["active_user_id"] = None
        d["active_username"] = ""
        d["finished_session_id"] = None
        d["finished_at"] = None
        d["finished_user_id"] = None
        d["finished_username"] = ""
        d["avg_score"] = None
        d["feedback_count"] = 0

    # 2. Categories for all recipes in one query
    for row in conn.execute(
        f"""SELECT rc.recipe_id, c.name
            FROM recipe_categories rc
            JOIN categories c ON c.id = rc.category_id
            WHERE rc.recipe_id IN ({placeholders})""",
        ids
    ).fetchall():
        if row["recipe_id"] in by_id:
            by_id[row["recipe_id"]]["categories"].append(row["name"])

    # 3. Tags for all recipes in one query
    for row in conn.execute(
        f"""SELECT rt.recipe_id, t.name
            FROM recipe_tags rt
            JOIN tags t ON t.id = rt.tag_id
            WHERE rt.recipe_id IN ({placeholders})""",
        ids
    ).fetchall():
        if row["recipe_id"] in by_id:
            by_id[row["recipe_id"]]["tags"].append(row["name"])

    # 4. Project status — scoped for library views, global for Home/admin.
    owner_sql, owner_params = _project_owner_filter(current_user, "ps", project_scope)
    session_rows = conn.execute(
        f"""SELECT ps.recipe_id, ps.id, ps.user_id, ps.username, ps.started_at, ps.finished_at
            FROM project_sessions ps
            WHERE ps.recipe_id IN ({placeholders}){owner_sql}
            ORDER BY ps.started_at ASC""",
        (*ids, *owner_params)
    ).fetchall()
    sessions_by_recipe: dict[str, list[dict]] = {}
    for row in session_rows:
        sessions_by_recipe.setdefault(row["recipe_id"], []).append(dict(row))
    for rid, sessions in sessions_by_recipe.items():
        if rid in by_id:
            if project_scope == "global" and status_context == "finished":
                sessions = [s for s in sessions if s["finished_at"]]
            _apply_project_status(by_id[rid], sessions)

    # 5. Feedback averages in one query
    feedback_owner_sql, feedback_owner_params = _project_owner_filter(current_user, "project_feedback", project_scope)
    for row in conn.execute(
        f"""SELECT recipe_id,
                   ROUND(AVG((rating_recipe + rating_difficulty + rating_result) / 3.0), 1) as avg_score,
                   COUNT(*) as feedback_count
            FROM project_feedback
            WHERE recipe_id IN ({placeholders}){feedback_owner_sql}
            GROUP BY recipe_id""",
        (*ids, *feedback_owner_params)
    ).fetchall():
        rid = row["recipe_id"]
        if rid in by_id:
            by_id[rid]["avg_score"]      = row["avg_score"]
            by_id[rid]["feedback_count"] = row["feedback_count"]

    # Return in the original order
    return [by_id[i] for i in ids if i in by_id]


_RECIPES_PER_PAGE = 60   # default page size for the recipe grid

def list_recipes(
    search:   Optional[str] = None,
    category: Optional[str] = None,
    tags:     Optional[str] = None,
    status:   Optional[str] = None,
    sort:     str = "default",
    project_scope: str = "user",
    page:     int = 1,
    per_page: int = _RECIPES_PER_PAGE,
    current_user: dict = Depends(get_current_user)
):
    # Clamp per_page to a safe range so one request can't load the whole DB
    per_page = max(1, min(per_page, 200))
    page     = max(1, page)

    conn = get_db()

    allowed_sorts = {
        "default",
        "title_asc",
        "title_desc",
        "created_desc",
        "created_asc",
        "last_completed_desc",
        "rating_desc",
    }
    if sort not in allowed_sorts:
        sort = "default"
    if project_scope != "global":
        project_scope = "user"
    scope_all = _project_scope_is_global(current_user, project_scope)
    session_scope_sql = "" if scope_all else " AND user_id=?"
    feedback_scope_sql = "" if scope_all else " AND user_id=?"
    session_scope_params = [] if scope_all else [current_user["id"]]
    feedback_scope_params = [] if scope_all else [current_user["id"]]

    # Build the filtered ID list with a single query
    id_query = """
        SELECT DISTINCT
            r.id,
            r.title,
            r.created_date,
            CASE WHEN active_ps.recipe_id IS NOT NULL THEN 1 ELSE 0 END AS has_active,
            CASE WHEN any_ps.recipe_id IS NOT NULL THEN 1 ELSE 0 END AS has_sessions,
            completed_ps.last_completed_at,
            rating.avg_score
        FROM recipes r
        LEFT JOIN recipe_categories rc ON r.id=rc.recipe_id
        LEFT JOIN categories c         ON rc.category_id=c.id
        LEFT JOIN recipe_tags rt       ON r.id=rt.recipe_id
        LEFT JOIN tags t               ON rt.tag_id=t.id
        LEFT JOIN (
            SELECT DISTINCT recipe_id FROM project_sessions WHERE finished_at IS NULL{session_scope_sql}
        ) active_ps ON active_ps.recipe_id = r.id
        LEFT JOIN (
            SELECT DISTINCT recipe_id FROM project_sessions WHERE 1=1{session_scope_sql}
        ) any_ps ON any_ps.recipe_id = r.id
        LEFT JOIN (
            SELECT recipe_id, MAX(finished_at) AS last_completed_at
            FROM project_sessions
            WHERE finished_at IS NOT NULL{session_scope_sql}
            GROUP BY recipe_id
        ) completed_ps ON completed_ps.recipe_id = r.id
        LEFT JOIN (
            SELECT recipe_id, AVG((rating_recipe + rating_difficulty + rating_result) / 3.0) AS avg_score
            FROM project_feedback
            WHERE 1=1{feedback_scope_sql}
            GROUP BY recipe_id
        ) rating ON rating.recipe_id = r.id
        WHERE 1=1
    """.format(
        session_scope_sql=session_scope_sql,
        feedback_scope_sql=feedback_scope_sql,
    )
    params = [*session_scope_params, *session_scope_params, *session_scope_params, *feedback_scope_params]
    if search:
        like = f"%{search}%"
        id_query += " AND (r.title LIKE ? OR r.description LIKE ? OR t.name LIKE ?)"
        params.extend([like, like, like])
    if category:
        id_query += " AND c.name=?"; params.append(category)
    if tags:
        tl = [t.strip() for t in tags.split(",") if t.strip()]
        id_query += f" AND t.name IN ({','.join('?'*len(tl))})"; params.extend(tl)

    # Status filter — active/finished must be handled via a sub-select
    # because project_status is derived, not stored.
    if status in ("active", "started"):
        id_query += """ AND r.id IN (
            SELECT recipe_id FROM project_sessions WHERE finished_at IS NULL""" + session_scope_sql + """
        )"""
        params.extend(session_scope_params)
    elif status == "finished":
        if project_scope == "global":
            id_query += """ AND r.id IN (
                SELECT recipe_id FROM project_sessions WHERE finished_at IS NOT NULL""" + session_scope_sql + """
            )"""
            params.extend(session_scope_params)
        else:
            id_query += """ AND r.id NOT IN (
                SELECT recipe_id FROM project_sessions WHERE finished_at IS NULL""" + session_scope_sql + """
            ) AND r.id IN (
                SELECT recipe_id FROM project_sessions WHERE 1=1""" + session_scope_sql + """
            )"""
            params.extend([*session_scope_params, *session_scope_params])

    sort_sql = {
        "default": """
            ORDER BY
                CASE WHEN has_active = 1 THEN 0
                     WHEN has_sessions = 1 THEN 1
                     ELSE 2 END,
                r.created_date DESC,
                LOWER(r.title) ASC
        """,
        "title_asc": "ORDER BY LOWER(r.title) ASC, r.created_date DESC",
        "title_desc": "ORDER BY LOWER(r.title) DESC, r.created_date DESC",
        "created_desc": "ORDER BY r.created_date DESC, LOWER(r.title) ASC",
        "created_asc": "ORDER BY r.created_date ASC, LOWER(r.title) ASC",
        "last_completed_desc": """
            ORDER BY
                CASE WHEN completed_ps.last_completed_at IS NULL THEN 1 ELSE 0 END,
                completed_ps.last_completed_at DESC,
                LOWER(r.title) ASC
        """,
        "rating_desc": """
            ORDER BY
                CASE WHEN rating.avg_score IS NULL THEN 1 ELSE 0 END,
                rating.avg_score DESC,
                LOWER(r.title) ASC
        """,
    }
    id_query += sort_sql[sort]

    all_ids = [row["id"] for row in conn.execute(id_query, params).fetchall()]
    total   = len(all_ids)

    # Paginate — slice the ID list, then bulk-fetch only those recipes
    offset   = (page - 1) * per_page
    page_ids = all_ids[offset : offset + per_page]

    result = _get_recipes_summary(conn, page_ids, current_user, project_scope, status)
    conn.close()

    return {
        "recipes":  result,
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    max(1, (total + per_page - 1) // per_page),
    }


def get_recipe(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn   = get_db()
    recipe = _get_recipe_full(recipe_id, conn, current_user)
    conn.close()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


def _viewer_progress_dict(row) -> dict:
    if not row:
        return {"exists": False}
    return {
        "exists": True,
        "recipeId": row["recipe_id"],
        "viewMode": row["view_mode"],
        "imageIndex": row["image_index"],
        "zoom": row["zoom"],
        "scrollY": row["scroll_y"],
        "textScrollY": row["text_scroll_y"],
        "mobileImagesVisible": bool(row["mobile_images_visible"]),
        "updatedAt": row["updated_at"],
    }


def get_recipe_viewer_progress(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    row = conn.execute(
        "SELECT * FROM recipe_viewer_progress WHERE recipe_id=? AND user_id=?",
        (recipe_id, current_user["id"])
    ).fetchone()
    conn.close()
    return _viewer_progress_dict(row)


def save_recipe_viewer_progress(recipe_id: str, data: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    view_mode = str(data.get("viewMode") or data.get("view_mode") or "original")
    if view_mode not in {"original", "text", "review", "charts"}:
        view_mode = "original"
    try:
        image_index = max(0, int(data.get("imageIndex", data.get("image_index", 0)) or 0))
    except (TypeError, ValueError):
        image_index = 0
    try:
        zoom = float(data.get("zoom", 1) or 1)
    except (TypeError, ValueError):
        zoom = 1
    zoom = max(0.5, min(4, zoom))
    try:
        scroll_y = max(0, int(float(data.get("scrollY", data.get("scroll_y", 0)) or 0)))
    except (TypeError, ValueError):
        scroll_y = 0
    try:
        text_scroll_y = max(0, int(float(data.get("textScrollY", data.get("text_scroll_y", 0)) or 0)))
    except (TypeError, ValueError):
        text_scroll_y = 0
    mobile_images_visible = 1 if data.get("mobileImagesVisible", data.get("mobile_images_visible", False)) else 0
    now = datetime.utcnow().isoformat()
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    conn.execute(
        """
        INSERT INTO recipe_viewer_progress
            (recipe_id,user_id,view_mode,image_index,zoom,scroll_y,text_scroll_y,mobile_images_visible,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(recipe_id,user_id) DO UPDATE SET
            view_mode=excluded.view_mode,
            image_index=excluded.image_index,
            zoom=excluded.zoom,
            scroll_y=excluded.scroll_y,
            text_scroll_y=excluded.text_scroll_y,
            mobile_images_visible=excluded.mobile_images_visible,
            updated_at=excluded.updated_at
        """,
        (recipe_id, current_user["id"], view_mode, image_index, zoom, scroll_y, text_scroll_y, mobile_images_visible, now)
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM recipe_viewer_progress WHERE recipe_id=? AND user_id=?",
        (recipe_id, current_user["id"])
    ).fetchone()
    conn.close()
    return _viewer_progress_dict(row)


async def check_duplicate(
    files: List[UploadFile] = File(...),
    title: str = Form(""),
    current_user: dict = Depends(get_current_user)
):
    """Check uploaded files for duplicate content or title before saving.
    Returns lists of content duplicates and title duplicates so the frontend
    can warn the user and let them decide whether to proceed.
    """
    # Read all file data
    file_data_list = []
    for upload in files:
        ext = Path(upload.filename.lower()).suffix
        if ext in IMAGE_EXTS or ext == ".pdf":
            data = await upload.read()
            file_data_list.append(data)

    results = {"content_duplicates": [], "title_duplicates": []}
    if not file_data_list:
        return results

    conn = get_db()

    # Content duplicate check — hash the uploaded files and compare to DB
    upload_hash = _hash_files(file_data_list)
    content_matches = conn.execute(
        "SELECT id, title FROM recipes WHERE content_hash=? AND content_hash!=''",
        (upload_hash,)
    ).fetchall()
    results["content_duplicates"] = [{"id": r["id"], "title": r["title"]} for r in content_matches]

    # Title duplicate check — case-insensitive exact match
    if title.strip():
        title_matches = conn.execute(
            "SELECT id, title FROM recipes WHERE LOWER(title)=LOWER(?)",
            (title.strip(),)
        ).fetchall()
        results["title_duplicates"] = [{"id": r["id"], "title": r["title"]} for r in title_matches]

    conn.close()
    return results


async def create_recipe(
    background_tasks: BackgroundTasks,
    title:       str = Form(...),
    description: str = Form(""),
    categories:  str = Form(""),
    tags:        str = Form(""),
    files:       List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    # Use slug-based folder name instead of UUID for clean, readable paths
    recipe_id, recipe_dir = _unique_recipe_dir(title)
    recipe_dir.mkdir(parents=True)

    saved, file_type = [], "images"
    all_file_data = []  # collect for hashing

    for upload in files:
        ext = Path(upload.filename.lower()).suffix
        if ext not in IMAGE_EXTS and ext != ".pdf":
            continue
        file_data = await upload.read()
        size_limit = MAX_PDF_BYTES if ext == ".pdf" else MAX_IMAGE_BYTES
        if len(file_data) > size_limit:
            shutil.rmtree(recipe_dir, ignore_errors=True)
            raise HTTPException(status_code=413, detail=f"File too large: {upload.filename}")
        if not _validate_file_magic(file_data, ext):
            shutil.rmtree(recipe_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"File content does not match extension: {upload.filename}")
        if ext == ".pdf":
            file_type, dest_name = "pdf", "recipe.pdf"
        else:
            # Normalize to lowercase so the filesystem matches IMAGE_EXTS globs
            # on case-sensitive Linux (e.g. .JPG → .jpg)
            dest_name = Path(upload.filename).name.lower()
        with open(recipe_dir / dest_name, "wb") as f:
            f.write(file_data)
        saved.append(dest_name)
        all_file_data.append(file_data)

    if not saved:
        shutil.rmtree(recipe_dir)
        raise HTTPException(status_code=400, detail="No valid files uploaded")

    # Generate thumbnail synchronously — it only renders page 1 and is fast.
    # Full PDF-to-pages conversion is slow (all pages at high DPI) so we
    # defer it to a background task and return the response immediately.
    # The individual page images will appear in the viewer within seconds.
    thumb = _generate_thumbnail(recipe_dir, file_type)
    if file_type == "pdf":
        background_tasks.add_task(_convert_pdf_to_pages, recipe_dir)

    content_hash = _hash_files(all_file_data)

    conn = get_db()
    conn.execute(
        "INSERT INTO recipes (id,title,description,file_type,thumbnail_path,created_date,content_hash) VALUES (?,?,?,?,?,?,?)",
        (recipe_id, title, description, file_type, thumb, datetime.utcnow().isoformat(), content_hash)
    )
    _save_cats_tags(conn, recipe_id, categories, tags)
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn)
    conn.close()
    return recipe


def bulk_update_recipes(data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    """Add tags and/or categories to multiple recipes (additive — never removes existing ones)."""
    ids      = data.get("ids", [])
    new_tags = [t.strip() for t in data.get("tags", []) if t.strip()]
    new_cats = [c.strip() for c in data.get("categories", []) if c.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="No recipe IDs provided")
    conn = get_db()
    for recipe_id in ids:
        if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
            continue
        # _save_cats_tags uses INSERT OR IGNORE so existing links are preserved
        _save_cats_tags(conn, recipe_id, ",".join(new_cats), ",".join(new_tags))
    _prune_orphan_categories(conn)
    conn.commit()
    conn.close()
    return {"status": "ok", "updated": len(ids)}


async def update_recipe(
    recipe_id:   str,
    title:       str = Form(...),
    description: str = Form(""),
    categories:  str = Form(""),
    tags:        str = Form(""),
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    conn.execute("UPDATE recipes SET title=?, description=? WHERE id=?", (title, description, recipe_id))
    conn.execute("DELETE FROM recipe_categories WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_tags       WHERE recipe_id=?", (recipe_id,))
    _save_cats_tags(conn, recipe_id, categories, tags)
    _prune_orphan_categories(conn)
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn)
    conn.close()
    return recipe


def delete_recipe(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    conn.execute("DELETE FROM recipe_categories WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_tags       WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM project_feedback  WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM project_sessions  WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM annotations       WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_viewer_progress WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_text_versions WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_text_generation_audits WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_charts WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_review_legends WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_review_diagrams WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_review_pages WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_review_sessions WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipes           WHERE id=?",        (recipe_id,))
    _prune_orphan_categories(conn)
    conn.commit()
    conn.close()
    recipe_dir = DATA_DIR / recipe_id
    if recipe_dir.exists():
        shutil.rmtree(recipe_dir)
    return {"message": "Recipe deleted"}


def list_categories(
    all: bool = False,
    details: bool = False,
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    assigned_only = not all
    result = (
        _taxonomy_details(conn, "categories", "recipe_categories", "category_id", assigned_only)
        if details else
        _taxonomy_names(conn, "categories", "recipe_categories", "category_id", assigned_only)
    )
    conn.close()
    return result


def add_category(data: dict, current_user: dict = Depends(get_current_user)):
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    conn = get_db()
    _add_taxonomy_item(conn, "categories", name)
    conn.commit()
    conn.close()
    return {"message": f"Category '{name}' added"}


def delete_category(name: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    usage = _delete_taxonomy_item(conn, "categories", "recipe_categories", "category_id", name, "Category")
    conn.commit()
    conn.close()
    return {"message": f"Category '{name}' deleted", "usage_count": usage}


def list_tags(
    all: bool = False,
    details: bool = False,
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    assigned_only = not all
    result = (
        _taxonomy_details(conn, "tags", "recipe_tags", "tag_id", assigned_only)
        if details else
        _taxonomy_names(conn, "tags", "recipe_tags", "tag_id", assigned_only)
    )
    conn.close()
    return result


def add_tag(data: dict, current_user: dict = Depends(get_current_user)):
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    conn = get_db()
    _add_taxonomy_item(conn, "tags", name)
    conn.commit()
    conn.close()
    return {"message": f"Tag '{name}' added"}


def delete_tag(name: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    usage = _delete_taxonomy_item(conn, "tags", "recipe_tags", "tag_id", name, "Tag")
    conn.commit()
    conn.close()
    return {"message": f"Tag '{name}' deleted", "usage_count": usage}

# ── File serving ──────────────────────────────────────────────────────────────


def _get_editable_project_session(conn, recipe_id: str, session_id: str, current_user: dict):
    query = """
        SELECT ps.id, ps.recipe_id, ps.user_id, ps.username, ps.started_at, ps.finished_at,
               ps.yarn_id, ps.yarn_colour_id, r.title
        FROM project_sessions ps
        JOIN recipes r ON r.id=ps.recipe_id
        WHERE ps.id=? AND ps.recipe_id=?
    """
    params = [session_id, recipe_id]
    if not current_user.get("is_admin"):
        query += " AND ps.user_id=?"
        params.append(current_user["id"])
    row = conn.execute(query, tuple(params)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return row


def _clean_project_time(value, field_name: str) -> str:
    value = str(value or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")
    return value


def start_project(recipe_id: str, body: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    recipe_row = conn.execute("SELECT id, title FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    if not recipe_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    active_check_sql = "SELECT id FROM project_sessions WHERE recipe_id=? AND finished_at IS NULL AND user_id=?"
    active_check_params = [recipe_id, current_user["id"]]
    if conn.execute(active_check_sql, tuple(active_check_params)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Project already active")
    session_id = str(uuid.uuid4())
    now        = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO project_sessions (id, recipe_id, user_id, username, started_at, yarn_id, yarn_colour_id) VALUES (?,?,?,?,?,?,?)",
        (
            session_id,
            recipe_id,
            current_user["id"],
            current_user["username"],
            now,
            body.get("yarn_id") or None,
            body.get("yarn_colour_id") or None,
        )
    )
    inv_id      = body.get("inventory_item_id") or None
    skeins_used = int(body.get("skeins_used") or 0)
    if inv_id and skeins_used > 0:
        inv = conn.execute("SELECT quantity FROM inventory_items WHERE id=?", (inv_id,)).fetchone()
        if inv:
            conn.execute("UPDATE inventory_items SET quantity=? WHERE id=?", (max(0, inv["quantity"] - skeins_used), inv_id))
            recipe_title = conn.execute("SELECT title FROM recipes WHERE id=?", (recipe_id,)).fetchone()["title"]
            conn.execute(
                "INSERT INTO inventory_log (id,item_id,change,reason,recipe_id,session_id,note,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), inv_id, -skeins_used, "project_start", recipe_id, session_id, f"Used for: {recipe_title}", now)
            )
    _log_user_action(
        conn,
        current_user,
        "project_started",
        recipe_id=recipe_id,
        recipe_title=recipe_row["title"],
        metadata={"session_id": session_id},
    )
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn, current_user)
    conn.close()
    return recipe


def finish_project(recipe_id: str, data: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    conn   = get_db()
    session_id = (data or {}).get("session_id")
    if session_id:
        active_sql = (
            "SELECT ps.id, r.title FROM project_sessions ps "
            "JOIN recipes r ON r.id=ps.recipe_id "
            "WHERE ps.recipe_id=? AND ps.id=? AND ps.finished_at IS NULL"
        )
        active_params = [recipe_id, session_id]
    else:
        active_sql = (
            "SELECT ps.id, r.title FROM project_sessions ps "
            "JOIN recipes r ON r.id=ps.recipe_id "
            "WHERE ps.recipe_id=? AND ps.finished_at IS NULL"
        )
        active_params = [recipe_id]
    if not current_user.get("is_admin"):
        active_sql += " AND ps.user_id=?"
        active_params.append(current_user["id"])
    active_sql += " ORDER BY ps.started_at DESC LIMIT 1"
    active = conn.execute(active_sql, tuple(active_params)).fetchone()
    if not active:
        conn.close()
        raise HTTPException(status_code=400, detail="No active session")
    conn.execute("UPDATE project_sessions SET finished_at=? WHERE id=?", (datetime.utcnow().isoformat(), active["id"]))
    _log_user_action(
        conn,
        current_user,
        "project_finished",
        recipe_id=recipe_id,
        recipe_title=active["title"],
        metadata={"session_id": active["id"]},
    )
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn, current_user)
    conn.close()
    return recipe


def save_feedback(recipe_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    session_id = data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    r_recipe = int(data.get("rating_recipe", 0))
    r_diff   = int(data.get("rating_difficulty", 0))
    r_result = int(data.get("rating_result", 0))
    for r in (r_recipe, r_diff, r_result):
        if not (1 <= r <= 6):
            raise HTTPException(status_code=400, detail="Ratings must be 1–6")
    conn = get_db()
    session_owner_sql = ""
    session_owner_params = []
    if not current_user.get("is_admin"):
        session_owner_sql = " AND ps.user_id=?"
        session_owner_params.append(current_user["id"])
    sess = conn.execute(
        "SELECT ps.id, ps.finished_at, r.title FROM project_sessions ps JOIN recipes r ON r.id=ps.recipe_id WHERE ps.id=? AND ps.recipe_id=?" + session_owner_sql,
        (session_id, recipe_id, *session_owner_params)
    ).fetchone()
    if not sess:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")
    now = datetime.utcnow().isoformat()
    if data.get("finish_session") and not sess["finished_at"]:
        conn.execute("UPDATE project_sessions SET finished_at=? WHERE id=?", (now, session_id))
        _log_user_action(
            conn,
            current_user,
            "project_finished",
            recipe_id=recipe_id,
            recipe_title=sess["title"],
            metadata={"session_id": session_id, "source": "feedback"},
        )
    existing = conn.execute(
        "SELECT id FROM project_feedback WHERE session_id=? AND user_id=?", (session_id, current_user["id"])
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE project_feedback SET rating_recipe=?, rating_difficulty=?, rating_result=?, notes=?, username=? WHERE id=?",
            (r_recipe, r_diff, r_result, data.get("notes", "").strip(), current_user["username"], existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO project_feedback (id,recipe_id,user_id,session_id,username,rating_recipe,rating_difficulty,rating_result,notes,created_date) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), recipe_id, current_user["id"], session_id,
             current_user["username"], r_recipe, r_diff, r_result, data.get("notes", "").strip(), now)
        )
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn, current_user)
    conn.close()
    return recipe


def get_session_feedback(recipe_id: str, session_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    sess_sql = "SELECT id FROM project_sessions WHERE id=? AND recipe_id=?"
    sess_params = [session_id, recipe_id]
    if not current_user.get("is_admin"):
        sess_sql += " AND user_id=?"
        sess_params.append(current_user["id"])
    if not conn.execute(sess_sql, tuple(sess_params)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")
    rows = conn.execute(
        "SELECT id, user_id, username, rating_recipe, rating_difficulty, rating_result, notes, created_date FROM project_feedback WHERE session_id=? AND recipe_id=?",
        (session_id, recipe_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_project_session(recipe_id: str, session_id: str, data: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    try:
        sess = _get_editable_project_session(conn, recipe_id, session_id, current_user)
        started_at = _clean_project_time(data.get("started_at", sess["started_at"]), "started_at")
        yarn_id = data.get("yarn_id") or None
        yarn_colour_id = data.get("yarn_colour_id") or None
        if yarn_colour_id and not yarn_id:
            raise HTTPException(status_code=400, detail="yarn_id required when yarn_colour_id is set")
        if yarn_id and not conn.execute("SELECT id FROM yarns WHERE id=?", (yarn_id,)).fetchone():
            raise HTTPException(status_code=400, detail="Yarn not found")
        if yarn_colour_id and not conn.execute(
            "SELECT id FROM yarn_colours WHERE id=? AND yarn_id=?", (yarn_colour_id, yarn_id)
        ).fetchone():
            raise HTTPException(status_code=400, detail="Yarn colour not found")
        conn.execute(
            "UPDATE project_sessions SET started_at=?, yarn_id=?, yarn_colour_id=? WHERE id=?",
            (started_at, yarn_id, yarn_colour_id, session_id),
        )
        _log_user_action(
            conn,
            current_user,
            "project_session_updated",
            recipe_id=recipe_id,
            recipe_title=sess["title"],
            metadata={"session_id": session_id},
        )
        conn.commit()
        recipe = _get_recipe_full(recipe_id, conn, current_user)
    finally:
        conn.close()
    return recipe


def reopen_project_session(recipe_id: str, session_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    try:
        sess = _get_editable_project_session(conn, recipe_id, session_id, current_user)
        active = conn.execute(
            "SELECT id FROM project_sessions WHERE recipe_id=? AND user_id=? AND finished_at IS NULL AND id!=?",
            (recipe_id, sess["user_id"], session_id),
        ).fetchone()
        if active:
            raise HTTPException(status_code=400, detail="User already has an active session for this recipe")
        conn.execute("UPDATE project_sessions SET finished_at=NULL WHERE id=?", (session_id,))
        _log_user_action(
            conn,
            current_user,
            "project_session_reopened",
            recipe_id=recipe_id,
            recipe_title=sess["title"],
            metadata={"session_id": session_id, "session_user_id": sess["user_id"]},
        )
        conn.commit()
        recipe = _get_recipe_full(recipe_id, conn, current_user)
    finally:
        conn.close()
    return recipe


def delete_project_session(recipe_id: str, session_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    try:
        sess = _get_editable_project_session(conn, recipe_id, session_id, current_user)
        conn.execute("DELETE FROM project_feedback WHERE recipe_id=? AND session_id=?", (recipe_id, session_id))
        conn.execute("DELETE FROM project_sessions WHERE recipe_id=? AND id=?", (recipe_id, session_id))
        _log_user_action(
            conn,
            current_user,
            "project_session_deleted",
            recipe_id=recipe_id,
            recipe_title=sess["title"],
            metadata={"session_id": session_id, "session_user_id": sess["user_id"]},
        )
        conn.commit()
        recipe = _get_recipe_full(recipe_id, conn, current_user)
    finally:
        conn.close()
    return recipe


def clear_sessions(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    if current_user.get("is_admin"):
        conn.execute("DELETE FROM project_feedback WHERE recipe_id=?", (recipe_id,))
        conn.execute("DELETE FROM project_sessions  WHERE recipe_id=?", (recipe_id,))
    else:
        session_ids = [
            row["id"] for row in conn.execute(
                "SELECT id FROM project_sessions WHERE recipe_id=? AND user_id=?",
                (recipe_id, current_user["id"]),
            ).fetchall()
        ]
        if session_ids:
            placeholders = ",".join("?" * len(session_ids))
            conn.execute(
                f"DELETE FROM project_feedback WHERE recipe_id=? AND session_id IN ({placeholders})",
                (recipe_id, *session_ids),
            )
            conn.execute(
                f"DELETE FROM project_sessions WHERE recipe_id=? AND id IN ({placeholders})",
                (recipe_id, *session_ids),
            )
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn, current_user)
    conn.close()
    return recipe

# ── Annotations ───────────────────────────────────────────────────────────────

def get_annotations(recipe_id: str, page_key: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row  = conn.execute(
        "SELECT data FROM annotations WHERE recipe_id=? AND page_key=? AND user_id=?",
        (recipe_id, page_key, current_user["id"])
    ).fetchone()
    conn.close()
    return {"strokes": json.loads(row["data"]) if row else []}


def save_annotations(recipe_id: str, page_key: str, data: dict, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    conn.execute(
        "INSERT INTO annotations (recipe_id,page_key,user_id,data,updated) VALUES (?,?,?,?,?) "
        "ON CONFLICT(recipe_id,page_key,user_id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
        (recipe_id, page_key, current_user["id"], json.dumps(data.get("strokes", [])), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def clear_annotations(recipe_id: str, page_key: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    conn.execute(
        "DELETE FROM annotations WHERE recipe_id=? AND page_key=? AND user_id=?",
        (recipe_id, page_key, current_user["id"])
    )
    conn.commit()
    conn.close()
    return {"ok": True}

# ── Bulk import ───────────────────────────────────────────────────────────────

async def import_upload_group(
    group_name:  str = Form(...),
    files:       List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    recipe_id  = str(uuid.uuid4())
    recipe_dir = DATA_DIR / recipe_id
    recipe_dir.mkdir(parents=True)
    saved, file_type = [], "images"
    for upload in files:
        ext = Path(upload.filename).suffix.lower()
        if ext not in IMAGE_EXTS and ext != ".pdf":
            continue
        file_data = await upload.read()
        size_limit = MAX_PDF_BYTES if ext == ".pdf" else MAX_IMAGE_BYTES
        if len(file_data) > size_limit:
            shutil.rmtree(recipe_dir, ignore_errors=True)
            raise HTTPException(status_code=413, detail=f"File too large: {upload.filename}")
        if not _validate_file_magic(file_data, ext):
            shutil.rmtree(recipe_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"File content does not match extension: {upload.filename}")
        if ext == ".pdf":
            dest_name, file_type = "recipe.pdf", "pdf"
        else:
            # Normalize to lowercase so the filesystem matches IMAGE_EXTS globs
            # on case-sensitive Linux (e.g. .JPG → .jpg)
            dest_name = Path(upload.filename).name.lower()
        with open(recipe_dir / dest_name, "wb") as f:
            f.write(file_data)
        saved.append(dest_name)
    if not saved:
        shutil.rmtree(recipe_dir)
        raise HTTPException(status_code=400, detail="No valid files in group")
    if file_type == "pdf":
        _convert_pdf_to_pages(recipe_dir)
    thumb         = _generate_thumbnail(recipe_dir, file_type)
    default_title = Path(group_name).stem if group_name.lower().endswith(".pdf") else group_name
    conn = get_db()
    conn.execute(
        "INSERT INTO recipes (id,title,description,file_type,thumbnail_path,created_date) VALUES (?,?,?,?,?,?)",
        (recipe_id, default_title, "", file_type, thumb, datetime.utcnow().isoformat())
    )
    conn.execute("INSERT INTO import_queue (recipe_id,group_name,status) VALUES (?,?,?)", (recipe_id, group_name, "staged"))
    conn.commit()
    recipe    = _get_recipe_full(recipe_id, conn)
    pdf_pages = sorted([f.name for f in recipe_dir.glob("page-*.jpg")])
    conn.close()
    return {"recipe_id": recipe_id, "recipe": recipe, "pdf_pages": pdf_pages, "group_name": group_name}


def import_get_queue(current_user: dict = Depends(get_current_user)):
    conn  = get_db()
    _cleanup_stale_import_queue(conn)
    conn.commit()
    rows  = conn.execute("SELECT recipe_id, group_name FROM import_queue WHERE status='staged' ORDER BY rowid").fetchall()
    items = []
    for row in rows:
        recipe = _get_recipe_full(row["recipe_id"], conn)
        if recipe:
            items.append({"recipe_id": row["recipe_id"], "group_name": row["group_name"], "recipe": recipe})
    conn.close()
    return {"items": items, "count": len(items)}


def import_check_duplicate(recipe_id: str, title: str = "", current_user: dict = Depends(get_current_user)):
    """Check a staged recipe for content/title duplicates before confirming."""
    conn = get_db()
    results = {"content_duplicates": [], "title_duplicates": []}

    # Hash the staged files and compare against confirmed recipes
    recipe_dir = DATA_DIR / recipe_id
    if recipe_dir.exists():
        file_data_list = []
        for f in sorted(recipe_dir.iterdir()):
            if f.is_file() and f.name not in ("thumbnail.jpg",) and not f.name.startswith("."):
                file_data_list.append(f.read_bytes())
        if file_data_list:
            staged_hash = _hash_files(file_data_list)
            matches = conn.execute(
                "SELECT id, title FROM recipes WHERE content_hash=? AND content_hash!='' AND id!=?",
                (staged_hash, recipe_id)
            ).fetchall()
            results["content_duplicates"] = [{"id": r["id"], "title": r["title"]} for r in matches]

    # Title check
    if title.strip():
        title_matches = conn.execute(
            "SELECT id, title FROM recipes WHERE LOWER(title)=LOWER(?) AND id!=?",
            (title.strip(), recipe_id)
        ).fetchall()
        results["title_duplicates"] = [{"id": r["id"], "title": r["title"]} for r in title_matches]

    conn.close()
    return results


def import_confirm(recipe_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    title = data.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    conn = get_db()
    if not conn.execute("SELECT recipe_id FROM import_queue WHERE recipe_id=? AND status='staged'", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Staged recipe not found")

    # Rename folder from temporary UUID to slug-based name
    new_id, new_dir = _unique_recipe_dir(title)
    old_dir = DATA_DIR / recipe_id
    if old_dir.exists() and not new_dir.exists():
        old_dir.rename(new_dir)
    else:
        new_id = recipe_id  # fallback: keep original id if rename not possible
        new_dir = old_dir

    # Compute and store content hash
    file_data_list = []
    for f in sorted(new_dir.iterdir()):
        if f.is_file() and f.name not in ("thumbnail.jpg",) and not f.name.startswith("."):
            file_data_list.append(f.read_bytes())
    content_hash = _hash_files(file_data_list) if file_data_list else ""

    # Update recipe record with new id, title, and hash
    conn.execute("UPDATE recipes SET id=?, title=?, description=?, content_hash=? WHERE id=?",
                 (new_id, title, data.get("description", ""), content_hash, recipe_id))
    conn.execute("UPDATE import_queue    SET recipe_id=?, status='done' WHERE recipe_id=?", (new_id, recipe_id))
    conn.execute("UPDATE recipe_categories SET recipe_id=? WHERE recipe_id=?", (new_id, recipe_id))
    conn.execute("UPDATE recipe_tags       SET recipe_id=? WHERE recipe_id=?", (new_id, recipe_id))
    conn.execute("UPDATE project_sessions  SET recipe_id=? WHERE recipe_id=?", (new_id, recipe_id))
    conn.execute("UPDATE project_feedback  SET recipe_id=? WHERE recipe_id=?", (new_id, recipe_id))
    conn.execute("UPDATE annotations       SET recipe_id=? WHERE recipe_id=?", (new_id, recipe_id))
    conn.execute("DELETE FROM recipe_categories WHERE recipe_id=?", (new_id,))
    conn.execute("DELETE FROM recipe_tags       WHERE recipe_id=?", (new_id,))
    _save_cats_tags(conn, new_id, data.get("categories", ""), data.get("tags", ""))
    _log_user_action(
        conn,
        current_user,
        "recipe_added",
        recipe_id=new_id,
        recipe_title=title,
        metadata={"import_group": data.get("group_name", "")},
    )
    conn.commit()
    conn.close()
    return {"status": "confirmed", "recipe_id": new_id}


def import_discard(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM recipe_categories WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_tags       WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipes           WHERE id=?",        (recipe_id,))
    conn.execute("UPDATE import_queue SET status='discarded' WHERE recipe_id=?", (recipe_id,))
    conn.commit()
    conn.close()
    recipe_dir = DATA_DIR / recipe_id
    if recipe_dir.exists():
        shutil.rmtree(recipe_dir)
    return {"status": "discarded", "recipe_id": recipe_id}

# ── Export ────────────────────────────────────────────────────────────────────

def export_library(current_user: dict = Depends(get_current_user)):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if DB_PATH.exists():
            zf.write(str(DB_PATH), arcname="recipes.db")
        for directory, prefix in ((DATA_DIR, "recipes"), (YARN_DIR, "yarns")):
            if directory.exists():
                for d in directory.iterdir():
                    if d.is_dir():
                        for file in d.rglob("*"):
                            if file.is_file():
                                zf.write(str(file), arcname=f"{prefix}/{file.relative_to(directory)}")
    buf.seek(0)
    filename = f"knitting-library-export-{datetime.now().strftime('%Y-%m-%d')}.zip"
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

__all__ = [name for name in globals() if not name.startswith("__")]
