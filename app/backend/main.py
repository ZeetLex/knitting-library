"""
Knitting Recipe Library - Backend API v2
New: User auth, user management, per-user settings (theme + language)
"""

import uuid
import shutil
import secrets
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
import sqlite3
import io
import zipfile

app = FastAPI(title="Knitting Recipe Library", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

DATA_DIR = Path("/data/recipes")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path("/data/recipes.db")

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    salt = "knitting_library_salt_v1"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS recipes (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT DEFAULT '',
            file_type TEXT NOT NULL, thumbnail_path TEXT DEFAULT '', created_date TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS recipe_categories (
            recipe_id TEXT, category_id INTEGER, PRIMARY KEY (recipe_id, category_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id), FOREIGN KEY (category_id) REFERENCES categories(id)
        );
        CREATE TABLE IF NOT EXISTS recipe_tags (
            recipe_id TEXT, tag_id INTEGER, PRIMARY KEY (recipe_id, tag_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id), FOREIGN KEY (tag_id) REFERENCES tags(id)
        );
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0, theme TEXT DEFAULT 'light', language TEXT DEFAULT 'en',
            created_date TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS annotations (
            recipe_id TEXT NOT NULL,
            page_key  TEXT NOT NULL,
            data      TEXT NOT NULL DEFAULT '[]',
            updated   TEXT NOT NULL,
            PRIMARY KEY (recipe_id, page_key)
        );
        CREATE TABLE IF NOT EXISTS project_sessions (
            id          TEXT PRIMARY KEY,
            recipe_id   TEXT NOT NULL,
            started_at  TEXT NOT NULL,
            finished_at TEXT,
            FOREIGN KEY (recipe_id) REFERENCES recipes(id)
        );
        -- No default categories — users create their own
    """)
    existing = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    if existing == 0:
        admin_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, username, password_hash, is_admin, theme, language, created_date) VALUES (?,?,?,1,'light','en',?)",
            (admin_id, "admin", hash_password("admin"), datetime.utcnow().isoformat())
        )
        print("Default admin created: username=admin password=admin  -- PLEASE CHANGE THIS!")
    conn.commit()
    conn.close()

init_db()

# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_current_user(request: Request):
    token = request.headers.get("X-Session-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    conn = get_db()
    row = conn.execute(
        "SELECT u.* FROM users u JOIN sessions s ON u.id = s.user_id WHERE s.token = ?", (token,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return dict(row)

def require_admin(current_user: dict = Depends(get_current_user)):
    if not current_user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

def user_dict(u):
    return {"id": u["id"], "username": u["username"], "is_admin": bool(u["is_admin"]), "theme": u["theme"], "language": u["language"]}

# ── Auth routes ───────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(data: dict):
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND password_hash = ?",
        (username, hash_password(password))
    ).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    user = dict(user)
    token = secrets.token_hex(32)
    conn.execute("INSERT INTO sessions (token, user_id, created_date) VALUES (?,?,?)",
                 (token, user["id"], datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"token": token, "user": user_dict(user)}

@app.post("/api/auth/logout")
def logout(request: Request):
    token = request.headers.get("X-Session-Token")
    if token:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
    return {"message": "Logged out"}

@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return user_dict(current_user)

@app.put("/api/auth/settings")
def update_settings(data: dict, current_user: dict = Depends(get_current_user)):
    theme    = data.get("theme", current_user["theme"])
    language = data.get("language", current_user["language"])
    if theme not in ("light", "dark"):
        raise HTTPException(status_code=400, detail="Theme must be light or dark")
    if language not in ("en", "no"):
        raise HTTPException(status_code=400, detail="Language must be en or no")
    conn = get_db()
    conn.execute("UPDATE users SET theme=?, language=? WHERE id=?", (theme, language, current_user["id"]))
    conn.commit()
    conn.close()
    return {"theme": theme, "language": language}

@app.put("/api/auth/change-password")
def change_password(data: dict, current_user: dict = Depends(get_current_user)):
    old_pw = data.get("old_password", "")
    new_pw = data.get("new_password", "")
    if not old_pw or not new_pw:
        raise HTTPException(status_code=400, detail="Both passwords required")
    if len(new_pw) < 4:
        raise HTTPException(status_code=400, detail="New password must be at least 4 characters")
    conn = get_db()
    user = conn.execute(
        "SELECT id FROM users WHERE id=? AND password_hash=?",
        (current_user["id"], hash_password(old_pw))
    ).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_pw), current_user["id"]))
    conn.commit()
    conn.close()
    return {"message": "Password changed"}

# ── Admin: user management ────────────────────────────────────────────────────

@app.get("/api/admin/users")
def list_users(admin: dict = Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT id, username, is_admin, theme, language, created_date FROM users ORDER BY created_date").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/admin/users")
def create_user(data: dict, admin: dict = Depends(require_admin)):
    username = data.get("username", "").strip()
    password = data.get("password", "")
    is_admin = data.get("is_admin", False)
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    conn = get_db()
    if conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    uid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO users (id, username, password_hash, is_admin, theme, language, created_date) VALUES (?,?,?,?,'light','en',?)",
        (uid, username, hash_password(password), 1 if is_admin else 0, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return {"id": uid, "username": username, "is_admin": is_admin}

@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"message": "User deleted"}

@app.put("/api/admin/users/{user_id}/reset-password")
def reset_password(user_id: str, data: dict, admin: dict = Depends(require_admin)):
    new_pw = data.get("new_password", "")
    if len(new_pw) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    conn = get_db()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_pw), user_id))
    conn.commit()
    conn.close()
    return {"message": "Password reset"}

# ── Recipes (all require login) ───────────────────────────────────────────────

@app.get("/api/recipes")
def list_recipes(search: Optional[str]=None, category: Optional[str]=None, tags: Optional[str]=None,
                 status: Optional[str]=None,
                 current_user: dict=Depends(get_current_user)):
    conn = get_db()
    query = """
        SELECT DISTINCT r.id, r.title, r.description, r.file_type, r.thumbnail_path, r.created_date
        FROM recipes r
        LEFT JOIN recipe_categories rc ON r.id = rc.recipe_id
        LEFT JOIN categories c ON rc.category_id = c.id
        LEFT JOIN recipe_tags rt ON r.id = rt.recipe_id
        LEFT JOIN tags t ON rt.tag_id = t.id WHERE 1=1
    """
    params = []
    if search:
        query += " AND (r.title LIKE ? OR r.description LIKE ? OR t.name LIKE ?)"
        like = f"%{search}%"; params.extend([like,like,like])
    if category:
        query += " AND c.name = ?"; params.append(category)
    if tags:
        tl = [t.strip() for t in tags.split(",")]
        query += f" AND t.name IN ({','.join('?'*len(tl))})"; params.extend(tl)
    query += " ORDER BY r.created_date DESC"
    recipes = conn.execute(query, params).fetchall()
    result = []
    for r in recipes:
        recipe = dict(r)
        recipe["categories"] = [x["name"] for x in conn.execute("SELECT c.name FROM categories c JOIN recipe_categories rc ON c.id=rc.category_id WHERE rc.recipe_id=?", (recipe["id"],)).fetchall()]
        recipe["tags"] = [x["name"] for x in conn.execute("SELECT t.name FROM tags t JOIN recipe_tags rt ON t.id=rt.tag_id WHERE rt.recipe_id=?", (recipe["id"],)).fetchall()]
        # Attach project status
        sessions = conn.execute(
            "SELECT id, started_at, finished_at FROM project_sessions WHERE recipe_id=? ORDER BY started_at ASC",
            (recipe["id"],)
        ).fetchall()
        recipe["sessions"] = [dict(s) for s in sessions]
        active = next((s for s in reversed(recipe["sessions"]) if not s["finished_at"]), None)
        if active:
            recipe["project_status"] = "active"
            recipe["active_started_at"] = active["started_at"]
        elif recipe["sessions"]:
            recipe["project_status"] = "finished"
        else:
            recipe["project_status"] = "none"
        result.append(recipe)
    conn.close()
    # Filter by status if requested
    if status == "active":
        result = [r for r in result if r["project_status"] == "active"]
    elif status == "finished":
        result = [r for r in result if r["project_status"] == "finished"]
    elif status == "started":  # alias
        result = [r for r in result if r["project_status"] == "active"]
    # Pin active projects to top, then finished, then rest — all by date within group
    def sort_key(r):
        if r["project_status"] == "active":   return 0
        if r["project_status"] == "finished": return 1
        return 2
    result.sort(key=sort_key)
    return result

@app.get("/api/recipes/{recipe_id}")
def get_recipe(recipe_id: str, current_user: dict=Depends(get_current_user)):
    conn = get_db()
    recipe = get_recipe_full(recipe_id, conn)
    conn.close()
    if not recipe: raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe

@app.post("/api/recipes")
async def create_recipe(title: str=Form(...), description: str=Form(""), categories: str=Form(""),
                        tags: str=Form(""), files: List[UploadFile]=File(...),
                        current_user: dict=Depends(get_current_user)):
    recipe_id = str(uuid.uuid4())
    recipe_dir = DATA_DIR / recipe_id
    recipe_dir.mkdir(parents=True)
    saved_files = []; file_type = "images"
    for upload in files:
        ext = Path(upload.filename.lower()).suffix
        if ext == ".pdf": file_type = "pdf"; save_name = "recipe.pdf"
        elif ext in [".jpg",".jpeg",".png",".webp"]: save_name = upload.filename
        else: continue
        dest = recipe_dir / save_name
        with open(dest, "wb") as f: f.write(await upload.read())
        saved_files.append(save_name)
    if not saved_files:
        shutil.rmtree(recipe_dir)
        raise HTTPException(status_code=400, detail="No valid files uploaded")
    # Convert PDF pages to images so the viewer can annotate per-page
    if file_type == "pdf":
        _convert_pdf_to_pages(recipe_dir)
    thumb = generate_thumbnail(recipe_dir, file_type, saved_files)
    conn = get_db()
    conn.execute("INSERT INTO recipes (id,title,description,file_type,thumbnail_path,created_date) VALUES (?,?,?,?,?,?)",
                 (recipe_id, title, description, file_type, thumb, datetime.utcnow().isoformat()))
    _save_cats_tags(conn, recipe_id, categories, tags)
    conn.commit()
    recipe = get_recipe_full(recipe_id, conn); conn.close()
    return recipe

@app.put("/api/recipes/{recipe_id}")
async def update_recipe(recipe_id: str, title: str=Form(...), description: str=Form(""),
                        categories: str=Form(""), tags: str=Form(""),
                        current_user: dict=Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close(); raise HTTPException(status_code=404, detail="Recipe not found")
    conn.execute("UPDATE recipes SET title=?, description=? WHERE id=?", (title, description, recipe_id))
    conn.execute("DELETE FROM recipe_categories WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_tags WHERE recipe_id=?", (recipe_id,))
    _save_cats_tags(conn, recipe_id, categories, tags)
    conn.commit()
    recipe = get_recipe_full(recipe_id, conn); conn.close()
    return recipe

@app.delete("/api/recipes/{recipe_id}")
def delete_recipe(recipe_id: str, current_user: dict=Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close(); raise HTTPException(status_code=404, detail="Recipe not found")
    conn.execute("DELETE FROM recipe_categories WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_tags WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipes WHERE id=?", (recipe_id,))
    conn.commit(); conn.close()
    recipe_dir = DATA_DIR / recipe_id
    if recipe_dir.exists(): shutil.rmtree(recipe_dir)
    return {"message": "Recipe deleted"}

@app.get("/api/categories")
def list_categories(current_user: dict=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    conn.close(); return [r["name"] for r in rows]

@app.get("/api/tags")
def list_tags(current_user: dict=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT t.name FROM tags t JOIN recipe_tags rt ON t.id=rt.tag_id ORDER BY t.name").fetchall()
    conn.close(); return [r["name"] for r in rows]

@app.post("/api/categories")
def add_category(data: dict, current_user: dict=Depends(get_current_user)):
    name = data.get("name","").strip()
    if not name: raise HTTPException(status_code=400, detail="Name required")
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
    conn.commit(); conn.close()
    return {"message": f"Category '{name}' added"}

@app.delete("/api/categories/{name}")
def delete_category(name: str, current_user: dict=Depends(get_current_user)):
    """Delete a category. Recipes that used it simply lose that category tag."""
    conn = get_db()
    row = conn.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Category not found")
    conn.execute("DELETE FROM recipe_categories WHERE category_id=?", (row["id"],))
    conn.execute("DELETE FROM categories WHERE id=?", (row["id"],))
    conn.commit(); conn.close()
    return {"message": f"Category '{name}' deleted"}

# ── File serving ──────────────────────────────────────────────────────────────
# Images and PDFs are loaded by the browser directly via <img src> and <iframe>,
# so they cannot send headers. We accept the token as a ?token= query param instead.

def verify_token_param(request: Request, token: Optional[str] = None):
    t = token or request.headers.get("X-Session-Token")
    if not t:
        raise HTTPException(status_code=401, detail="Not logged in")
    conn = get_db()
    row = conn.execute(
        "SELECT u.* FROM users u JOIN sessions s ON u.id = s.user_id WHERE s.token = ?", (t,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return dict(row)

@app.get("/api/recipes/{recipe_id}/thumbnail")
def get_thumbnail(recipe_id: str, request: Request, token: Optional[str] = None):
    verify_token_param(request, token)
    thumb = DATA_DIR / recipe_id / "thumbnail.jpg"
    if thumb.exists(): return FileResponse(str(thumb), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Thumbnail not found")

@app.get("/api/recipes/{recipe_id}/pdf")
def get_pdf(recipe_id: str, request: Request, token: Optional[str] = None):
    verify_token_param(request, token)
    pdf = DATA_DIR / recipe_id / "recipe.pdf"
    if pdf.exists(): return FileResponse(str(pdf), media_type="application/pdf")
    raise HTTPException(status_code=404, detail="PDF not found")

@app.get("/api/recipes/{recipe_id}/images/{filename}")
def get_image(recipe_id: str, filename: str, request: Request, token: Optional[str] = None):
    verify_token_param(request, token)
    safe_name = Path(filename).name
    image_path = DATA_DIR / recipe_id / safe_name
    if image_path.exists(): return FileResponse(str(image_path))
    raise HTTPException(status_code=404, detail="Image not found")

@app.get("/api/health")
def health():
    return {"status": "ok", "message": "Knitting Library API v2"}

# ── Project Sessions ──────────────────────────────────────────────────────────

@app.post("/api/recipes/{recipe_id}/start")
def start_project(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close(); raise HTTPException(status_code=404, detail="Recipe not found")
    # Check no active session already running
    active = conn.execute(
        "SELECT id FROM project_sessions WHERE recipe_id=? AND finished_at IS NULL", (recipe_id,)
    ).fetchone()
    if active:
        conn.close(); raise HTTPException(status_code=400, detail="Project already active")
    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO project_sessions (id, recipe_id, started_at) VALUES (?,?,?)",
        (session_id, recipe_id, now)
    )
    conn.commit()
    recipe = get_recipe_full(recipe_id, conn); conn.close()
    return recipe

@app.post("/api/recipes/{recipe_id}/finish")
def finish_project(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    active = conn.execute(
        "SELECT id FROM project_sessions WHERE recipe_id=? AND finished_at IS NULL", (recipe_id,)
    ).fetchone()
    if not active:
        conn.close(); raise HTTPException(status_code=400, detail="No active session")
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE project_sessions SET finished_at=? WHERE id=?", (now, active["id"])
    )
    conn.commit()
    recipe = get_recipe_full(recipe_id, conn); conn.close()
    return recipe

@app.delete("/api/recipes/{recipe_id}/sessions")
def clear_sessions(recipe_id: str, current_user: dict = Depends(get_current_user)):
    """Delete all session history for a recipe, resetting it to 'not started'."""
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close(); raise HTTPException(status_code=404, detail="Recipe not found")
    conn.execute("DELETE FROM project_sessions WHERE recipe_id=?", (recipe_id,))
    conn.commit()
    recipe = get_recipe_full(recipe_id, conn); conn.close()
    return recipe

# ── Annotations ───────────────────────────────────────────────────────────────
# page_key is either an image filename (e.g. "image1.jpg") or "pdf-<pagenum>"
# Data is stored as a JSON array of stroke objects.

@app.get("/api/recipes/{recipe_id}/annotations/{page_key}")
def get_annotations(recipe_id: str, page_key: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM annotations WHERE recipe_id=? AND page_key=?",
        (recipe_id, page_key)
    ).fetchone()
    conn.close()
    import json
    return {"strokes": json.loads(row["data"]) if row else []}

@app.put("/api/recipes/{recipe_id}/annotations/{page_key}")
def save_annotations(recipe_id: str, page_key: str, data: dict,
                     current_user: dict = Depends(get_current_user)):
    import json
    strokes_json = json.dumps(data.get("strokes", []))
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO annotations (recipe_id, page_key, data, updated) VALUES (?,?,?,?) "
        "ON CONFLICT(recipe_id, page_key) DO UPDATE SET data=excluded.data, updated=excluded.updated",
        (recipe_id, page_key, strokes_json, now)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/api/recipes/{recipe_id}/annotations/{page_key}")
def clear_annotations(recipe_id: str, page_key: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM annotations WHERE recipe_id=? AND page_key=?", (recipe_id, page_key))
    conn.commit()
    conn.close()
    return {"ok": True}

# ── Export ────────────────────────────────────────────────────────────────────
# Streams a ZIP file containing all recipe files + the database.
# The ZIP is built in memory so no temp files are left on disk.

@app.get("/api/export")
def export_library(current_user: dict = Depends(get_current_user)):
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Include the SQLite database
        if DB_PATH.exists():
            zf.write(str(DB_PATH), arcname="recipes.db")

        # 2. Include every recipe folder under /data/recipes/
        if DATA_DIR.exists():
            for recipe_dir in DATA_DIR.iterdir():
                if recipe_dir.is_dir():
                    for file in recipe_dir.rglob("*"):
                        if file.is_file():
                            # Keep folder structure: recipes/<id>/filename
                            arcname = "recipes/" + str(file.relative_to(DATA_DIR))
                            zf.write(str(file), arcname=arcname)

    buf.seek(0)

    from datetime import datetime
    filename = f"knitting-library-export-{datetime.now().strftime('%Y-%m-%d')}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )

# ── Shared helpers ────────────────────────────────────────────────────────────

def _convert_pdf_to_pages(recipe_dir: Path):
    """Convert every page of recipe.pdf to a JPEG image: page-001.jpg, page-002.jpg …"""
    pdf_path = recipe_dir / "recipe.pdf"
    if not pdf_path.exists():
        return
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(str(pdf_path), dpi=150)
        for i, page in enumerate(pages):
            page.save(str(recipe_dir / f"page-{i+1:03d}.jpg"), "JPEG", quality=88)
        print(f"PDF converted: {len(pages)} pages → {recipe_dir}")
    except Exception as e:
        print(f"PDF page conversion failed: {e}")

@app.get("/api/recipes/{recipe_id}/pdf-pages")
def get_pdf_pages(recipe_id: str, current_user: dict = Depends(get_current_user)):
    """Return list of page image filenames for a PDF recipe, if they exist."""
    recipe_dir = DATA_DIR / recipe_id
    pages = sorted(recipe_dir.glob("page-*.jpg"))
    return {"pages": [p.name for p in pages]}

@app.post("/api/recipes/{recipe_id}/convert-pdf")
def convert_pdf(recipe_id: str, current_user: dict = Depends(get_current_user)):
    """Trigger on-demand PDF conversion for recipes uploaded before this feature existed."""
    recipe_dir = DATA_DIR / recipe_id
    if not (recipe_dir / "recipe.pdf").exists():
        raise HTTPException(status_code=404, detail="No PDF found for this recipe")
    _convert_pdf_to_pages(recipe_dir)
    pages = sorted(recipe_dir.glob("page-*.jpg"))
    return {"pages": [p.name for p in pages]}

@app.get("/api/recipes/{recipe_id}/pdf-pages/{filename}")
def get_pdf_page_image(recipe_id: str, filename: str, request: Request, token: Optional[str] = None):
    verify_token_param(request, token)
    safe = Path(filename).name
    path = DATA_DIR / recipe_id / safe
    if path.exists() and safe.startswith("page-") and safe.endswith(".jpg"):
        return FileResponse(str(path), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Page not found")

def _save_cats_tags(conn, recipe_id, categories, tags):
    for cat_name in [c.strip() for c in categories.split(",") if c.strip()]:
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_name,))
        cat_row = conn.execute("SELECT id FROM categories WHERE name=?", (cat_name,)).fetchone()
        if cat_row: conn.execute("INSERT OR IGNORE INTO recipe_categories (recipe_id,category_id) VALUES (?,?)", (recipe_id, cat_row["id"]))
    for tag_name in [t.strip() for t in tags.split(",") if t.strip()]:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
        tag_row = conn.execute("SELECT id FROM tags WHERE name=?", (tag_name,)).fetchone()
        if tag_row: conn.execute("INSERT OR IGNORE INTO recipe_tags (recipe_id,tag_id) VALUES (?,?)", (recipe_id, tag_row["id"]))

def generate_thumbnail(recipe_dir: Path, file_type: str, files: list) -> str:
    thumb_path = recipe_dir / "thumbnail.jpg"
    if file_type == "pdf":
        try:
            from pdf2image import convert_from_path
            pdf_file = next(recipe_dir.glob("*.pdf"), None)
            if pdf_file:
                pages = convert_from_path(str(pdf_file), first_page=1, last_page=1, dpi=150)
                if pages: pages[0].save(str(thumb_path), "JPEG", quality=85); return "thumbnail.jpg"
        except Exception as e: print(f"PDF thumb failed: {e}")
    elif file_type == "images":
        for ext in [".jpg",".jpeg",".png",".webp"]:
            image_files = sorted(recipe_dir.glob(f"*{ext}"))
            if image_files:
                try:
                    from PIL import Image
                    img = Image.open(image_files[0]); img.thumbnail((400,400))
                    img.save(str(thumb_path),"JPEG",quality=85); return "thumbnail.jpg"
                except Exception as e: print(f"Image thumb failed: {e}")
    return ""

def get_recipe_full(recipe_id: str, conn) -> dict:
    recipe = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    if not recipe: return None
    recipe = dict(recipe)
    recipe["categories"] = [r["name"] for r in conn.execute("SELECT c.name FROM categories c JOIN recipe_categories rc ON c.id=rc.category_id WHERE rc.recipe_id=?", (recipe_id,)).fetchall()]
    recipe["tags"] = [r["name"] for r in conn.execute("SELECT t.name FROM tags t JOIN recipe_tags rt ON t.id=rt.tag_id WHERE rt.recipe_id=?", (recipe_id,)).fetchall()]
    if recipe["file_type"] == "images":
        recipe_dir = DATA_DIR / recipe_id
        images = []
        for ext in [".jpg",".jpeg",".png",".webp"]: images.extend(sorted(recipe_dir.glob(f"*{ext}")))
        recipe["images"] = sorted([f.name for f in images if f.name != "thumbnail.jpg"])
    else:
        recipe["images"] = []
    # Project status: derive from sessions
    sessions = conn.execute(
        "SELECT id, started_at, finished_at FROM project_sessions WHERE recipe_id=? ORDER BY started_at ASC",
        (recipe_id,)
    ).fetchall()
    recipe["sessions"] = [dict(s) for s in sessions]
    # Active session = last session with no finished_at
    active = next((s for s in reversed(recipe["sessions"]) if not s["finished_at"]), None)
    if active:
        recipe["project_status"] = "active"
        recipe["active_session_id"] = active["id"]
        recipe["active_started_at"]  = active["started_at"]
    elif recipe["sessions"]:
        recipe["project_status"] = "finished"
    else:
        recipe["project_status"] = "none"
    return recipe
