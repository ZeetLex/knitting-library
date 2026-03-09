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

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
import sqlite3
import io
import zipfile

app = FastAPI(title="Knitting Recipe Library", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

DATA_DIR = Path("/data/recipes")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH  = Path("/data/recipes.db")
YARN_DIR = Path("/data/yarns")
YARN_DIR.mkdir(parents=True, exist_ok=True)

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
            yarn_id     TEXT,
            yarn_colour_id TEXT,
            FOREIGN KEY (recipe_id) REFERENCES recipes(id),
            FOREIGN KEY (yarn_id)   REFERENCES yarns(id)
        );
        CREATE TABLE IF NOT EXISTS yarn_colours (
            id           TEXT PRIMARY KEY,
            yarn_id      TEXT NOT NULL,
            name         TEXT NOT NULL,
            image_path   TEXT DEFAULT '',
            price        TEXT DEFAULT '',
            created_date TEXT NOT NULL,
            FOREIGN KEY (yarn_id) REFERENCES yarns(id)
        );
        CREATE TABLE IF NOT EXISTS yarns (
            id               TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            colour           TEXT DEFAULT '',
            wool_type        TEXT DEFAULT '',
            yardage          TEXT DEFAULT '',
            needles          TEXT DEFAULT '',
            tension          TEXT DEFAULT '',
            origin           TEXT DEFAULT '',
            seller           TEXT DEFAULT '',
            price_per_skein  TEXT DEFAULT '',
            product_info     TEXT DEFAULT '',
            image_path       TEXT DEFAULT '',
            created_date     TEXT NOT NULL
        );
        -- No default categories — users create their own
        CREATE TABLE IF NOT EXISTS inventory_items (
            id              TEXT PRIMARY KEY,
            type            TEXT NOT NULL DEFAULT 'yarn',  -- 'yarn' or 'tool'
            -- yarn-specific links
            yarn_id         TEXT,
            yarn_colour_id  TEXT,
            -- tool-specific
            category        TEXT DEFAULT '',  -- needle/tool/notion/other
            -- shared fields
            name            TEXT NOT NULL,
            quantity        INTEGER NOT NULL DEFAULT 0,
            purchase_date   TEXT DEFAULT '',
            purchase_price  TEXT DEFAULT '',
            purchase_note   TEXT DEFAULT '',
            notes           TEXT DEFAULT '',
            created_date    TEXT NOT NULL,
            FOREIGN KEY (yarn_id)        REFERENCES yarns(id),
            FOREIGN KEY (yarn_colour_id) REFERENCES yarn_colours(id)
        );
        CREATE TABLE IF NOT EXISTS inventory_log (
            id          TEXT PRIMARY KEY,
            item_id     TEXT NOT NULL,
            change      INTEGER NOT NULL,  -- positive = added, negative = used
            reason      TEXT NOT NULL DEFAULT 'manual',  -- manual/project_start/adjustment
            recipe_id   TEXT,
            session_id  TEXT,
            note        TEXT DEFAULT '',
            created_at  TEXT NOT NULL,
            FOREIGN KEY (item_id)    REFERENCES inventory_items(id),
            FOREIGN KEY (recipe_id)  REFERENCES recipes(id),
            FOREIGN KEY (session_id) REFERENCES project_sessions(id)
        );
    """)
    existing = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    if existing == 0:
        admin_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, username, password_hash, is_admin, theme, language, created_date) VALUES (?,?,?,1,'light','en',?)",
            (admin_id, "admin", hash_password("admin"), datetime.utcnow().isoformat())
        )
        print("Default admin created: username=admin password=admin  -- PLEASE CHANGE THIS!")
    # Migrations — add columns that may not exist in older databases
    existing_cols = [r["name"] for r in conn.execute("PRAGMA table_info(yarns)").fetchall()]
    if "colour" not in existing_cols:
        conn.execute("ALTER TABLE yarns ADD COLUMN colour TEXT DEFAULT ''")
        print("Migration: added 'colour' column to yarns")
    if "seller" not in existing_cols:
        conn.execute("ALTER TABLE yarns ADD COLUMN seller TEXT DEFAULT ''")
        print("Migration: added 'seller' column to yarns")
    if "price_per_skein" not in existing_cols:
        conn.execute("ALTER TABLE yarns ADD COLUMN price_per_skein TEXT DEFAULT ''")
        print("Migration: added 'price_per_skein' column to yarns")
    # project_sessions migrations
    ps_cols = [r["name"] for r in conn.execute("PRAGMA table_info(project_sessions)").fetchall()]
    if "yarn_id" not in ps_cols:
        conn.execute("ALTER TABLE project_sessions ADD COLUMN yarn_id TEXT")
        print("Migration: added 'yarn_id' column to project_sessions")
    if "yarn_colour_id" not in ps_cols:
        conn.execute("ALTER TABLE project_sessions ADD COLUMN yarn_colour_id TEXT")
        print("Migration: added 'yarn_colour_id' column to project_sessions")
    # yarn_colours table — safe to create if it doesn't exist yet
    conn.execute("""
        CREATE TABLE IF NOT EXISTS yarn_colours (
            id           TEXT PRIMARY KEY,
            yarn_id      TEXT NOT NULL,
            name         TEXT NOT NULL,
            image_path   TEXT DEFAULT '',
            price        TEXT DEFAULT '',
            created_date TEXT NOT NULL,
            FOREIGN KEY (yarn_id) REFERENCES yarns(id)
        )
    """)
    yc_cols = [r["name"] for r in conn.execute("PRAGMA table_info(yarn_colours)").fetchall()]
    if "price" not in yc_cols:
        conn.execute("ALTER TABLE yarn_colours ADD COLUMN price TEXT DEFAULT ''")
        print("Migration: added 'price' column to yarn_colours")
    # inventory tables — safe to create if they don't exist yet
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id              TEXT PRIMARY KEY,
            type            TEXT NOT NULL DEFAULT 'yarn',
            yarn_id         TEXT,
            yarn_colour_id  TEXT,
            category        TEXT DEFAULT '',
            name            TEXT NOT NULL,
            quantity        INTEGER NOT NULL DEFAULT 0,
            purchase_date   TEXT DEFAULT '',
            purchase_price  TEXT DEFAULT '',
            purchase_note   TEXT DEFAULT '',
            notes           TEXT DEFAULT '',
            created_date    TEXT NOT NULL,
            FOREIGN KEY (yarn_id)        REFERENCES yarns(id),
            FOREIGN KEY (yarn_colour_id) REFERENCES yarn_colours(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_log (
            id          TEXT PRIMARY KEY,
            item_id     TEXT NOT NULL,
            change      INTEGER NOT NULL,
            reason      TEXT NOT NULL DEFAULT 'manual',
            recipe_id   TEXT,
            session_id  TEXT,
            note        TEXT DEFAULT '',
            created_at  TEXT NOT NULL,
            FOREIGN KEY (item_id)    REFERENCES inventory_items(id),
            FOREIGN KEY (recipe_id)  REFERENCES recipes(id),
            FOREIGN KEY (session_id) REFERENCES project_sessions(id)
        )
    """)
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
            "SELECT ps.id, ps.started_at, ps.finished_at, ps.yarn_id, ps.yarn_colour_id, y.name as yarn_name, yc.name as yarn_colour FROM project_sessions ps LEFT JOIN yarns y ON ps.yarn_id = y.id LEFT JOIN yarn_colours yc ON ps.yarn_colour_id = yc.id WHERE ps.recipe_id=? ORDER BY ps.started_at ASC",
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
def start_project(recipe_id: str, body: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close(); raise HTTPException(status_code=404, detail="Recipe not found")
    active = conn.execute(
        "SELECT id FROM project_sessions WHERE recipe_id=? AND finished_at IS NULL", (recipe_id,)
    ).fetchone()
    if active:
        conn.close(); raise HTTPException(status_code=400, detail="Project already active")
    yarn_id        = body.get("yarn_id") or None
    yarn_colour_id = body.get("yarn_colour_id") or None
    session_id     = str(uuid.uuid4())
    now            = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO project_sessions (id, recipe_id, started_at, yarn_id, yarn_colour_id) VALUES (?,?,?,?,?)",
        (session_id, recipe_id, now, yarn_id, yarn_colour_id)
    )
    # Optional inventory deduction
    inventory_item_id = body.get("inventory_item_id") or None
    skeins_used       = int(body.get("skeins_used") or 0)
    if inventory_item_id and skeins_used > 0:
        inv_row = conn.execute("SELECT * FROM inventory_items WHERE id=?", (inventory_item_id,)).fetchone()
        if inv_row:
            new_qty = max(0, inv_row["quantity"] - skeins_used)
            conn.execute("UPDATE inventory_items SET quantity=? WHERE id=?", (new_qty, inventory_item_id))
            recipe_row = conn.execute("SELECT title FROM recipes WHERE id=?", (recipe_id,)).fetchone()
            recipe_title = recipe_row["title"] if recipe_row else recipe_id
            conn.execute(
                "INSERT INTO inventory_log (id,item_id,change,reason,recipe_id,session_id,note,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), inventory_item_id, -skeins_used, "project_start",
                 recipe_id, session_id, f"Used for: {recipe_title}", now)
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
    """
    Export everything needed for a full backup or migration:
      recipes.db          — SQLite database (recipes, tags, categories, users,
                            annotations, project sessions, yarns, yarn colours,
                            inventory items, inventory log)
      recipes/<id>/...    — Recipe PDF and image files + thumbnails
      yarns/<id>/...      — Yarn type images and colour variant images

    Inventory data (items + log) lives entirely in the database — no extra files.
    """
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. SQLite database — contains ALL metadata including inventory
        if DB_PATH.exists():
            zf.write(str(DB_PATH), arcname="recipes.db")

        # 2. Recipe files (PDFs, images, thumbnails)
        if DATA_DIR.exists():
            for recipe_dir in DATA_DIR.iterdir():
                if recipe_dir.is_dir():
                    for file in recipe_dir.rglob("*"):
                        if file.is_file():
                            arcname = "recipes/" + str(file.relative_to(DATA_DIR))
                            zf.write(str(file), arcname=arcname)

        # 3. Yarn images and colour variant images
        if YARN_DIR.exists():
            for yarn_dir in YARN_DIR.iterdir():
                if yarn_dir.is_dir():
                    for file in yarn_dir.rglob("*"):
                        if file.is_file():
                            arcname = "yarns/" + str(file.relative_to(YARN_DIR))
                            zf.write(str(file), arcname=arcname)

    buf.seek(0)

    from datetime import datetime
    filename = f"knitting-library-export-{datetime.now().strftime('%Y-%m-%d')}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )

# ── Bulk Import ────────────────────────────────────────────────────────────────
#
# How it works (browser-upload flow):
#   1. User selects a folder in their browser (webkitdirectory input)
#   2. Frontend groups files by folder structure into recipe candidates
#   3. POST /api/import/upload-group  → receives one group (files), stages it as
#                                        a draft recipe with thumbnail, returns recipe_id
#   4. GET  /api/import/queue         → returns all currently staged (pending) recipes
#   5. POST /api/import/confirm/{id}  → saves title/tags/categories, marks as done
#   6. POST /api/import/discard/{id}  → deletes the draft recipe entirely
#
# The import_queue table persists staged items across sessions so the wizard
# is fully resumable — close at item 20, come back and pick up from item 21.

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PDF_EXT    = ".pdf"

def _init_import_table():
    """Create import_queue table if it doesn't exist yet."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS import_queue (
            recipe_id   TEXT PRIMARY KEY,
            group_name  TEXT,              -- original folder/file name
            status      TEXT DEFAULT 'staged'  -- staged | done | discarded
        )
    """)
    conn.commit()
    conn.close()

_init_import_table()


@app.post("/api/import/upload-group")
async def import_upload_group(
    group_name: str = Form(...),
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Receive one recipe group uploaded from the browser.
    Creates a draft recipe, generates thumbnail, records in import_queue.
    Returns { recipe_id, recipe } for immediate preview in the wizard.
    """
    recipe_id  = str(uuid.uuid4())
    recipe_dir = DATA_DIR / recipe_id
    recipe_dir.mkdir(parents=True)

    saved_files = []
    file_type   = "images"

    for upload in files:
        ext = Path(upload.filename).suffix.lower()
        if ext == PDF_EXT:
            dest_name = "recipe.pdf"
            file_type = "pdf"
        elif ext in IMAGE_EXTS:
            # Use just the filename (strip any path prefix the browser may send)
            dest_name = Path(upload.filename).name
        else:
            continue
        dest = recipe_dir / dest_name
        with open(dest, "wb") as f:
            f.write(await upload.read())
        saved_files.append(dest_name)

    if not saved_files:
        shutil.rmtree(recipe_dir)
        raise HTTPException(status_code=400, detail="No valid files in group")

    # Generate thumbnail + convert PDF pages
    if file_type == "pdf":
        _convert_pdf_to_pages(recipe_dir)
    thumb = generate_thumbnail(recipe_dir, file_type, saved_files)

    # Default title = group name (folder name or filename without extension)
    default_title = Path(group_name).stem if group_name.lower().endswith(".pdf") else group_name

    conn = get_db()
    conn.execute(
        "INSERT INTO recipes (id,title,description,file_type,thumbnail_path,created_date) VALUES (?,?,?,?,?,?)",
        (recipe_id, default_title, "", file_type, thumb, datetime.utcnow().isoformat())
    )
    conn.execute(
        "INSERT INTO import_queue (recipe_id, group_name, status) VALUES (?,?,?)",
        (recipe_id, group_name, "staged")
    )
    conn.commit()
    recipe = get_recipe_full(recipe_id, conn)
    conn.close()
    return {"recipe_id": recipe_id, "recipe": recipe}


@app.get("/api/import/queue")
def import_get_queue(current_user: dict = Depends(get_current_user)):
    """
    Return all staged (pending) import items so the wizard can resume.
    Each item includes the full recipe object for preview.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT recipe_id, group_name FROM import_queue WHERE status='staged' ORDER BY rowid"
    ).fetchall()
    items = []
    for row in rows:
        recipe = get_recipe_full(row["recipe_id"], conn)
        if recipe:
            items.append({
                "recipe_id":  row["recipe_id"],
                "group_name": row["group_name"],
                "recipe":     recipe,
            })
    conn.close()
    return {"items": items, "count": len(items)}


@app.post("/api/import/confirm/{recipe_id}")
def import_confirm(recipe_id: str, data: dict,
                   current_user: dict = Depends(get_current_user)):
    """
    Save user-entered metadata onto the draft recipe and mark it as done.
    The recipe stays in the library — nothing is moved or deleted.
    """
    title       = data.get("title", "").strip()
    categories  = data.get("categories", "")
    tags        = data.get("tags", "")
    description = data.get("description", "")

    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    conn = get_db()
    if not conn.execute(
        "SELECT recipe_id FROM import_queue WHERE recipe_id=? AND status='staged'",
        (recipe_id,)
    ).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Staged recipe not found")

    conn.execute("UPDATE recipes SET title=?, description=? WHERE id=?",
                 (title, description, recipe_id))
    conn.execute("DELETE FROM recipe_categories WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_tags       WHERE recipe_id=?", (recipe_id,))
    _save_cats_tags(conn, recipe_id, categories, tags)
    conn.execute("UPDATE import_queue SET status='done' WHERE recipe_id=?", (recipe_id,))
    conn.commit()
    conn.close()
    return {"status": "confirmed", "recipe_id": recipe_id}


@app.post("/api/import/discard/{recipe_id}")
def import_discard(recipe_id: str, current_user: dict = Depends(get_current_user)):
    """
    Delete a staged draft recipe entirely — removes files and DB rows.
    Used when the user clicks Skip and chooses not to keep the item.
    """
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
        "SELECT ps.id, ps.started_at, ps.finished_at, ps.yarn_id, ps.yarn_colour_id, y.name as yarn_name, yc.name as yarn_colour FROM project_sessions ps LEFT JOIN yarns y ON ps.yarn_id = y.id LEFT JOIN yarn_colours yc ON ps.yarn_colour_id = yc.id WHERE ps.recipe_id=? ORDER BY ps.started_at ASC",
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

# ── Yarn Database ─────────────────────────────────────────────────────────────

def yarn_to_dict(row, conn=None) -> dict:
    d = dict(row)
    # Attach colour variants — open a connection if one wasn't passed in
    close = False
    if conn is None:
        conn = get_db(); close = True
    colours = conn.execute(
        "SELECT id, name, image_path, price FROM yarn_colours WHERE yarn_id=? ORDER BY created_date ASC",
        (d["id"],)
    ).fetchall()
    d["colours"] = [dict(c) for c in colours]
    if close:
        conn.close()
    return d

@app.get("/api/yarns")
def list_yarns(
    search: Optional[str] = None, field: Optional[str] = None,
    filter_colour: Optional[str] = None,
    filter_wool_type: Optional[str] = None,
    filter_seller: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    query = "SELECT * FROM yarns WHERE 1=1"
    params = []
    if search:
        like = f"%{search}%"
        if field == "name":
            query += " AND name LIKE ?"; params.append(like)
        elif field == "colour":
            query += " AND colour LIKE ?"; params.append(like)
        elif field == "material":
            query += " AND (wool_type LIKE ? OR origin LIKE ?)"; params.extend([like, like])
        else:
            query += " AND (name LIKE ? OR colour LIKE ? OR wool_type LIKE ? OR origin LIKE ? OR product_info LIKE ? OR seller LIKE ?)"
            params.extend([like, like, like, like, like, like])
    if filter_colour:
        query += " AND colour = ?"; params.append(filter_colour)
    if filter_wool_type:
        query += " AND wool_type = ?"; params.append(filter_wool_type)
    if filter_seller:
        query += " AND seller = ?"; params.append(filter_seller)
    query += " ORDER BY created_date DESC"
    rows = conn.execute(query, params).fetchall()
    result = [yarn_to_dict(r, conn) for r in rows]
    conn.close()
    return result

@app.get("/api/yarns/autocomplete")
def yarn_autocomplete(field: str, current_user: dict = Depends(get_current_user)):
    """Return distinct non-empty values for a given field — powers the search datalist and filter pills."""
    allowed = {"name", "colour", "wool_type", "origin", "seller"}
    if field not in allowed:
        raise HTTPException(status_code=400, detail="Invalid field")
    conn = get_db()
    rows = conn.execute(
        f"SELECT DISTINCT {field} FROM yarns WHERE {field} != '' AND {field} IS NOT NULL ORDER BY {field}"
    ).fetchall()
    conn.close()
    return {"values": [r[field] for r in rows]}

@app.get("/api/yarns/autocomplete")
def yarn_autocomplete(field: str, current_user: dict = Depends(get_current_user)):
    """Return distinct non-empty values for a given field — powers the search datalist and filter pills."""
    allowed = {"name", "colour", "wool_type", "origin", "seller"}
    if field not in allowed:
        raise HTTPException(status_code=400, detail="Invalid field")
    conn = get_db()
    rows = conn.execute(
        f"SELECT DISTINCT {field} FROM yarns WHERE {field} != '' AND {field} IS NOT NULL ORDER BY {field}"
    ).fetchall()
    conn.close()
    return {"values": [r[field] for r in rows]}


@app.post("/api/yarns/scrape")
async def scrape_yarn_url(
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch a yarn product page and extract key fields.
    Strategy 1: Shopify JSON API (garnius.no and most Shopify yarn stores).
    Strategy 2: HTML scraping (sandnesgarn.no and other static sites).
    """
    import httpx
    from bs4 import BeautifulSoup
    import re
    import ipaddress, socket
    from urllib.parse import urlparse as _urlparse

    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="No URL provided")
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="URL must start with http/https")

    # Block private/internal addresses — SSRF protection
    _parsed = _urlparse(url)
    _hostname = _parsed.hostname or ""
    if _hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        raise HTTPException(status_code=400, detail="URL not allowed")
    try:
        _ip = ipaddress.ip_address(socket.gethostbyname(_hostname))
        if _ip.is_private or _ip.is_loopback or _ip.is_link_local or _ip.is_reserved:
            raise HTTPException(status_code=400, detail="URL not allowed")
    except (socket.gaierror, ValueError):
        pass

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7",
    }

    def clean(s):
        return re.sub(r"\s+", " ", s).strip() if s else ""

    # Shared label map used by both strategies
    label_map = {
        "løpelengde":            "yardage",
        "run length":            "yardage",
        "meterage":              "yardage",
        "yardage":               "yardage",
        "vekt per nøste":        "yardage",
        "veiledende pinner":     "needles",
        "anbefalt pinnestørrelse": "needles",
        "needle size":           "needles",
        "recommended needle":    "needles",
        "pinner":                "needles",
        "strikkefasthet":        "tension",
        "gauge":                 "tension",
        "tension":               "tension",
        "råvare kommer fra":     "origin",
        "raw material":          "origin",
        "opprinnelse":           "origin",
        "sammensetning":         "wool_type",
        "composition":           "wool_type",
        "fiber content":         "wool_type",
        "material":              "wool_type",
    }

    def parse_specs_from_soup(spec_soup, result):
        """Parse key:value spec lines from any BeautifulSoup fragment."""
        for el in spec_soup.find_all(["li", "dt", "dd", "p", "span", "td", "th"]):
            t = clean(el.get_text())
            if ":" in t:
                k, _, v = t.partition(":")
                k_lower = k.strip().lower()
                v_clean = v.strip()
                for label, field in label_map.items():
                    if label in k_lower and field not in result and v_clean:
                        result[field] = v_clean
                        break

    # ── Strategy 1: Shopify JSON API ─────────────────────────────────────────
    handle = _parsed.path.strip("/").split("/")[-1].split("?")[0]
    shopify_url = f"{_parsed.scheme}://{_parsed.netloc}/products/{handle}.json"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            sj = await client.get(shopify_url, headers=headers)
        if sj.status_code == 200:
            data = sj.json().get("product", {})
            if data.get("title"):
                result = {}
                result["name"] = data["title"]
                if data.get("vendor"):
                    result["seller"] = data["vendor"]
                # Parse specs out of the description HTML
                body_html = data.get("body_html", "")
                if body_html:
                    desc_soup = BeautifulSoup(body_html, "html.parser")
                    parse_specs_from_soup(desc_soup, result)
                    plain = clean(desc_soup.get_text(" "))
                    if plain:
                        result["product_info"] = plain[:1000]
                # Image — first product image, strip Shopify resize params
                images = data.get("images", [])
                if images:
                    src = images[0].get("src", "")
                    if src:
                        result["image_url"] = re.sub(r"\?.*$", "", src)
                # Price from first variant
                variants = data.get("variants", [])
                if variants and variants[0].get("price"):
                    result["price_per_skein"] = variants[0]["price"]
                result = {k: v for k, v in result.items() if v}
                return result
    except Exception:
        pass  # Not Shopify or failed — fall through to HTML scraping

    # ── Strategy 2: HTML scraping ────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Page returned {resp.status_code}")
        html = resp.text
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch URL: {e}")

    soup = BeautifulSoup(html, "html.parser")
    result = {}

    def find_text(*selectors):
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                return clean(el.get_text())
        return ""

    # ── Product name ──────────────────────────────────────────────────────────
    result["name"] = (
        find_text("h1.page-title", "h1", "[itemprop='name']")
        or clean(soup.title.get_text()).split("|")[0].split("-")[0]
    )

    # ── Wool type (subtitle / fibre composition) ──────────────────────────────
    # Sandnes shows it as a <p> just below the h1, or in a subtitle element
    subtitle = find_text(".product-subtitle", ".product.attribute.overview p", "h1 + p")
    if not subtitle:
        # Fallback: look for lines containing % signs near the product title
        for tag in soup.find_all(["p", "div", "span"]):
            t = clean(tag.get_text())
            if re.search(r"\d+\s*%", t) and len(t) < 120:
                subtitle = t
                break
    result["wool_type"] = subtitle

    # ── Structured spec rows (Sandnes uses a <ul> list of key: value pairs) ──
    specs = {}
    # Pattern 1: <li> containing "label: value" text
    for li in soup.select("ul li, .product-attribute li, .data.item"):
        text = clean(li.get_text())
        if ":" in text:
            parts = text.split(":", 1)
            key = parts[0].strip().lower()
            val = parts[1].strip()
            specs[key] = val

    # Pattern 2: definition list <dt>/<dd>
    dts = soup.select("dl dt")
    for dt in dts:
        dd = dt.find_next_sibling("dd")
        if dd:
            specs[clean(dt.get_text()).lower()] = clean(dd.get_text())

    # Map spec labels → fields using the shared label_map defined above
    for raw_key, val in specs.items():
        for label, field in label_map.items():
            if label in raw_key and field not in result:
                result[field] = val
                break

    # ── Seller — derive from domain ───────────────────────────────────────────
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace("www.", "")
    seller_map = {
        "sandnesgarn.no": "Sandnes Garn",
        "garnstudio.com":  "Drops",
        "dropsdesign.com": "Drops",
        "rowan.com":       "Rowan",
        "loveknitting.com":"LoveKnitting",
        "woolwarehouse.co.uk": "Wool Warehouse",
    }
    result["seller"] = seller_map.get(domain, domain)

    # ── Price ─────────────────────────────────────────────────────────────────
    price_el = soup.select_one(
        ".price, [itemprop='price'], .product-price, .price-wrapper"
    )
    if price_el:
        price_text = clean(price_el.get_text())
        # Keep only the first price-looking chunk (digits + currency)
        m = re.search(r"[\d,.]+\s*(kr|nok|€|\$|£|eur|usd|gbp)?", price_text, re.I)
        if m:
            result["price_per_skein"] = m.group(0).strip()

    # ── Colour ────────────────────────────────────────────────────────────────
    colour = ""
    # Pattern 1: selected swatch label (works when a colour variant URL is used)
    for sel in [
        ".swatch-option.selected .swatch-label",
        ".swatch-option.selected",
        ".selected-color-label",
        ".product-option-selected",
        "[data-option-type='1'].selected",
    ]:
        el = soup.select_one(sel)
        if el:
            colour = clean(el.get_text())
            if colour:
                break
    # Pattern 2: page title contains more than just the product name
    # e.g. Sandnes title = "Atlas Natural White 1012" vs product name "Atlas"
    if not colour and result.get("name"):
        page_title = clean(soup.title.get_text()) if soup.title else ""
        page_title = re.split(r"\s*[|\-–]\s*", page_title)[0].strip()
        base_name = result["name"]
        if page_title.lower().startswith(base_name.lower()) and len(page_title) > len(base_name):
            colour_candidate = page_title[len(base_name):].strip()
            if colour_candidate and len(colour_candidate) < 60:
                colour = colour_candidate
    # Pattern 3: look for a short text containing a 4-digit colour number
    if not colour:
        for tag in soup.find_all(["span", "div", "p", "h2", "h3"]):
            t = clean(tag.get_text())
            if re.search(r"\b\d{4}\b", t) and 3 < len(t) < 50 and t != result.get("name", ""):
                colour = t
                break
    if colour:
        result["colour"] = colour

    # ── Product image ─────────────────────────────────────────────────────────
    img_url = None

    def get_img_src(el):
        """Return src, checking data-src and data-original for lazy-loaded images too."""
        for attr in ["src", "data-src", "data-original", "data-lazy"]:
            v = el.get(attr, "")
            if v and not v.endswith(".svg") and not v.startswith("data:"):
                if v.startswith("//"):
                    v = "https:" + v
                return v
        return None

    # Try CSS selectors first — Sandnes uses alt="main product photo"
    for sel in [
        "img[alt='main product photo']",
        ".gallery-placeholder img",
        ".product.media img",
        "[itemprop='image']",
        ".fotorama__img",
        "img.product-image-photo",
        ".product-image img",
        ".product__image img",
    ]:
        el = soup.select_one(sel)
        if el:
            src = get_img_src(el)
            if src:
                img_url = src
                break

    # Fallback: scan all images for catalog/product path patterns
    if not img_url:
        for img in soup.find_all("img"):
            if "/icons/" in (img.get("src") or "") or "/logo" in (img.get("src") or ""):
                continue
            src = get_img_src(img)
            if src and any(p in src for p in ["/catalog/product", "/products/", "/media/", "/yarn/"]):
                img_url = src
                break

    # Last resort: first non-SVG, non-base64 image with a real image extension
    if not img_url:
        for img in soup.find_all("img"):
            src = get_img_src(img)
            if src and src.startswith("http") and re.search(r"\.(jpe?g|png|webp)", src, re.I):
                if not any(x in src for x in ["/icons/", "/logo", "/banner", "/sprite"]):
                    img_url = src
                    break

    result["image_url"] = img_url

    # ── Strip empty values ────────────────────────────────────────────────────
    result = {k: v for k, v in result.items() if v}

    return result


@app.get("/api/yarns/{yarn_id}")
def get_yarn(yarn_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Yarn not found")
    result = yarn_to_dict(row, conn)
    conn.close()
    return result

@app.post("/api/yarns")
async def create_yarn(
    name: str = Form(...),
    wool_type: str = Form(""),
    yardage: str = Form(""),
    needles: str = Form(""),
    tension: str = Form(""),
    origin: str = Form(""),
    product_info: str = Form(""),
    seller: str = Form(""),
    price_per_skein: str = Form(""),
    image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    yarn_id = str(uuid.uuid4())
    yarn_dir = YARN_DIR / yarn_id
    yarn_dir.mkdir(parents=True)
    image_path = ""
    if image and image.filename:
        ext = Path(image.filename.lower()).suffix
        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            data = await image.read()
            save_path = yarn_dir / f"yarn{ext}"
            with open(save_path, "wb") as f:
                f.write(data)
            try:
                from PIL import Image as PILImage
                img = PILImage.open(save_path)
                img.thumbnail((600, 600))
                img.save(str(yarn_dir / "thumbnail.jpg"), "JPEG", quality=85)
            except Exception as e:
                print(f"Yarn thumbnail failed: {e}")
            image_path = f"yarn{ext}"
    conn = get_db()
    conn.execute(
        "INSERT INTO yarns (id,name,colour,wool_type,yardage,needles,tension,origin,seller,price_per_skein,product_info,image_path,created_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (yarn_id, name, "", wool_type, yardage, needles, tension, origin, seller, price_per_skein, product_info, image_path, datetime.utcnow().isoformat())
    )
    conn.commit()
    row = conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone()
    result = yarn_to_dict(row, conn)
    conn.close()
    return result

@app.put("/api/yarns/{yarn_id}")
async def update_yarn(
    yarn_id: str,
    name: str = Form(...),
    wool_type: str = Form(""),
    yardage: str = Form(""),
    needles: str = Form(""),
    tension: str = Form(""),
    origin: str = Form(""),
    product_info: str = Form(""),
    seller: str = Form(""),
    price_per_skein: str = Form(""),
    image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    row = conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Yarn not found")
    yarn_dir = YARN_DIR / yarn_id
    yarn_dir.mkdir(parents=True, exist_ok=True)
    image_path = row["image_path"]
    if image and image.filename:
        ext = Path(image.filename.lower()).suffix
        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            data = await image.read()
            save_path = yarn_dir / f"yarn{ext}"
            with open(save_path, "wb") as f:
                f.write(data)
            try:
                from PIL import Image as PILImage
                img = PILImage.open(save_path)
                img.thumbnail((600, 600))
                img.save(str(yarn_dir / "thumbnail.jpg"), "JPEG", quality=85)
            except Exception as e:
                print(f"Yarn thumbnail failed: {e}")
            image_path = f"yarn{ext}"
    conn.execute(
        "UPDATE yarns SET name=?,wool_type=?,yardage=?,needles=?,tension=?,origin=?,seller=?,price_per_skein=?,product_info=?,image_path=? WHERE id=?",
        (name, wool_type, yardage, needles, tension, origin, seller, price_per_skein, product_info, image_path, yarn_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone()
    result = yarn_to_dict(row, conn)
    conn.close()
    return result

# ── Yarn Colour endpoints ─────────────────────────────────────────────────────

@app.get("/api/yarns/{yarn_id}/colours")
def list_yarn_colours(yarn_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM yarn_colours WHERE yarn_id=? ORDER BY created_date ASC", (yarn_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/yarns/{yarn_id}/colours")
async def add_yarn_colour(
    yarn_id: str,
    name: str = Form(...),
    price: str = Form(""),
    image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarns WHERE id=?", (yarn_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Yarn not found")
    colour_id = str(uuid.uuid4())
    colour_dir = YARN_DIR / yarn_id / "colours" / colour_id
    colour_dir.mkdir(parents=True, exist_ok=True)
    image_path = ""
    if image and image.filename:
        ext = Path(image.filename.lower()).suffix
        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            data = await image.read()
            save_path = colour_dir / f"colour{ext}"
            with open(save_path, "wb") as f:
                f.write(data)
            try:
                from PIL import Image as PILImage
                img = PILImage.open(save_path)
                img.thumbnail((400, 400))
                img.save(str(colour_dir / "thumb.jpg"), "JPEG", quality=85)
            except Exception as e:
                print(f"Colour thumb failed: {e}")
            image_path = f"colours/{colour_id}/colour{ext}"
    conn.execute(
        "INSERT INTO yarn_colours (id, yarn_id, name, image_path, price, created_date) VALUES (?,?,?,?,?,?)",
        (colour_id, yarn_id, name, image_path, price, datetime.utcnow().isoformat())
    )
    conn.commit()
    row = conn.execute("SELECT * FROM yarn_colours WHERE id=?", (colour_id,)).fetchone()
    conn.close()
    return dict(row)

@app.delete("/api/yarns/{yarn_id}/colours/{colour_id}")
def delete_yarn_colour(yarn_id: str, colour_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT * FROM yarn_colours WHERE id=? AND yarn_id=?", (colour_id, yarn_id)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Colour not found")
    conn.execute("DELETE FROM yarn_colours WHERE id=?", (colour_id,))
    conn.commit()
    conn.close()
    # Remove colour image files
    colour_dir = YARN_DIR / yarn_id / "colours" / colour_id
    if colour_dir.exists():
        shutil.rmtree(colour_dir)
    return {"message": "Colour deleted"}

@app.get("/api/yarns/{yarn_id}/colours/{colour_id}/image")
def get_yarn_colour_image(yarn_id: str, colour_id: str, request: Request, token: Optional[str] = None):
    """Serve colour image by colour ID."""
    verify_token_param(request, token)
    colour_dir = YARN_DIR / yarn_id / "colours" / colour_id
    for name in ["thumb.jpg", "colour.jpg", "colour.jpeg", "colour.png", "colour.webp"]:
        p = colour_dir / name
        if p.exists():
            mt = "image/jpeg" if name.endswith((".jpg", ".jpeg")) else "image/png" if name.endswith(".png") else "image/webp"
            return FileResponse(str(p), media_type=mt)
    raise HTTPException(status_code=404, detail="No image")

@app.delete("/api/yarns/{yarn_id}")
def delete_yarn(yarn_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarns WHERE id=?", (yarn_id,)).fetchone():
        conn.close(); raise HTTPException(status_code=404, detail="Yarn not found")
    conn.execute("DELETE FROM yarn_colours WHERE yarn_id=?", (yarn_id,))
    conn.execute("DELETE FROM yarns WHERE id=?", (yarn_id,))
    conn.commit(); conn.close()
    yarn_dir = YARN_DIR / yarn_id
    if yarn_dir.exists(): shutil.rmtree(yarn_dir)
    return {"message": "Yarn deleted"}

@app.get("/api/yarns/{yarn_id}/image")
def get_yarn_image(yarn_id: str, request: Request, token: Optional[str] = None):
    verify_token_param(request, token)
    yarn_dir = YARN_DIR / yarn_id
    # Try thumbnail first, then original
    for name in ["thumbnail.jpg", "yarn.jpg", "yarn.jpeg", "yarn.png", "yarn.webp"]:
        p = yarn_dir / name
        if p.exists():
            mt = "image/jpeg" if name.endswith((".jpg",".jpeg")) else "image/png" if name.endswith(".png") else "image/webp"
            return FileResponse(str(p), media_type=mt)
    raise HTTPException(status_code=404, detail="No image")

# ── Inventory endpoints ───────────────────────────────────────────────────────

def inventory_item_to_dict(row, conn) -> dict:
    """Convert an inventory_items row to a dict, enriching yarn items with yarn/colour names."""
    d = dict(row)
    if d.get("type") == "yarn":
        if d.get("yarn_id"):
            y = conn.execute("SELECT name FROM yarns WHERE id=?", (d["yarn_id"],)).fetchone()
            d["yarn_name"] = y["name"] if y else ""
        else:
            d["yarn_name"] = ""
        if d.get("yarn_colour_id"):
            c = conn.execute("SELECT name, image_path FROM yarn_colours WHERE id=?", (d["yarn_colour_id"],)).fetchone()
            d["colour_name"]       = c["name"]       if c else ""
            d["colour_image_path"] = c["image_path"] if c else ""
        else:
            d["colour_name"]       = ""
            d["colour_image_path"] = ""
    return d

@app.get("/api/inventory")
def list_inventory(
    type: Optional[str] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    q = "SELECT * FROM inventory_items WHERE 1=1"
    params = []
    if type:
        q += " AND type=?"; params.append(type)
    if search:
        like = f"%{search}%"
        q += " AND (name LIKE ? OR notes LIKE ?)"; params.extend([like, like])
    q += " ORDER BY created_date DESC"
    rows = conn.execute(q, params).fetchall()
    result = [inventory_item_to_dict(r, conn) for r in rows]
    conn.close()
    return result

@app.get("/api/inventory/{item_id}")
def get_inventory_item(item_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close(); raise HTTPException(status_code=404, detail="Item not found")
    result = inventory_item_to_dict(row, conn)
    conn.close()
    return result

@app.get("/api/inventory/{item_id}/log")
def get_inventory_log(item_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        """SELECT l.*, r.title as recipe_title
           FROM inventory_log l
           LEFT JOIN recipes r ON l.recipe_id = r.id
           WHERE l.item_id=?
           ORDER BY l.created_at DESC""",
        (item_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/inventory")
def create_inventory_item(body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    item_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    t = body.get("type", "yarn")
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    qty = int(body.get("quantity", 0))
    conn = get_db()
    conn.execute(
        """INSERT INTO inventory_items
           (id, type, yarn_id, yarn_colour_id, category, name, quantity,
            purchase_date, purchase_price, purchase_note, notes, created_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (item_id, t,
         body.get("yarn_id") or None,
         body.get("yarn_colour_id") or None,
         body.get("category", ""),
         name, qty,
         body.get("purchase_date", ""),
         body.get("purchase_price", ""),
         body.get("purchase_note", ""),
         body.get("notes", ""),
         now)
    )
    # Log the initial addition if qty > 0
    if qty > 0:
        conn.execute(
            "INSERT INTO inventory_log (id,item_id,change,reason,note,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), item_id, qty, "added", "Initial stock", now)
        )
    conn.commit()
    row = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    result = inventory_item_to_dict(row, conn)
    conn.close()
    return result

@app.put("/api/inventory/{item_id}")
def update_inventory_item(item_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close(); raise HTTPException(status_code=404, detail="Item not found")
    name = body.get("name", row["name"]).strip() or row["name"]
    conn.execute(
        """UPDATE inventory_items SET
           category=?, name=?, purchase_date=?, purchase_price=?,
           purchase_note=?, notes=?, yarn_id=?, yarn_colour_id=?
           WHERE id=?""",
        (body.get("category", row["category"]),
         name,
         body.get("purchase_date", row["purchase_date"]),
         body.get("purchase_price", row["purchase_price"]),
         body.get("purchase_note", row["purchase_note"]),
         body.get("notes", row["notes"]),
         body.get("yarn_id") or row["yarn_id"],
         body.get("yarn_colour_id") or row["yarn_colour_id"],
         item_id)
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    result = inventory_item_to_dict(updated, conn)
    conn.close()
    return result

@app.post("/api/inventory/{item_id}/adjust")
def adjust_inventory(item_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    """Add or remove quantity. body: { change: int, reason: str, note: str, recipe_id: str, session_id: str }"""
    conn = get_db()
    row = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close(); raise HTTPException(status_code=404, detail="Item not found")
    change = int(body.get("change", 0))
    if change == 0:
        conn.close(); raise HTTPException(status_code=400, detail="change cannot be 0")
    new_qty = max(0, row["quantity"] + change)
    now = datetime.utcnow().isoformat()
    conn.execute("UPDATE inventory_items SET quantity=? WHERE id=?", (new_qty, item_id))
    conn.execute(
        "INSERT INTO inventory_log (id,item_id,change,reason,recipe_id,session_id,note,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), item_id, change,
         body.get("reason", "manual"),
         body.get("recipe_id") or None,
         body.get("session_id") or None,
         body.get("note", ""),
         now)
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    result = inventory_item_to_dict(updated, conn)
    conn.close()
    return result

@app.delete("/api/inventory/{item_id}")
def delete_inventory_item(item_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM inventory_items WHERE id=?", (item_id,)).fetchone():
        conn.close(); raise HTTPException(status_code=404, detail="Item not found")
    conn.execute("DELETE FROM inventory_log WHERE item_id=?", (item_id,))
    conn.execute("DELETE FROM inventory_items WHERE id=?", (item_id,))
    conn.commit(); conn.close()
    return {"message": "Deleted"}
