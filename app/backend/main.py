"""
Knitting Recipe Library — Backend API
"""

import io
import json
import os
import re
import shutil
import uuid
import zipfile
import hashlib
import secrets
import ipaddress
import socket
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
import sqlite3

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Knitting Recipe Library",
    # Disable the auto-generated docs endpoints in production.
    # They expose route names and models to anyone who can reach the server.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# ── Security headers middleware ────────────────────────────────────────────────

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # Prevent the browser from sniffing content types (stops e.g. JS in a PNG)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Don't allow this app to be embedded in iframes on other domains
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    # Only send referrer info to same-origin requests
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Disable browser features we don't use
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # Content-Security-Policy: tighten what the API can load
    # (The React frontend has its own CSP served by nginx — this covers the /api/ responses)
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response

# ── CORS ──────────────────────────────────────────────────────────────────────
# Restrict to same-origin only. Requests from the React app are same-origin
# because nginx proxies /api/ internally. allow_origins=["*"] is replaced
# with an explicit empty list — the app is not a public API.
# If you expose this behind a named domain, add it here.
_ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",")
_ALLOWED_ORIGINS = [o.strip() for o in _ALLOWED_ORIGINS if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,   # empty = same-origin only
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Session-Token"],
)

DATA_DIR = Path("/data/recipes")
YARN_DIR = Path("/data/yarns")
DB_PATH  = Path("/data/recipes.db")

DATA_DIR.mkdir(parents=True, exist_ok=True)
YARN_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Maximum file upload sizes
MAX_PDF_BYTES   = 50  * 1024 * 1024   # 50 MB
MAX_IMAGE_BYTES = 20  * 1024 * 1024   # 20 MB

# ── File magic-byte validation ─────────────────────────────────────────────────
# Read the first few bytes to confirm the file is what the extension claims.
# This stops a renamed .exe or .php from being saved as a .jpg.

_MAGIC: dict[str, list[bytes]] = {
    ".jpg":  [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png":  [b"\x89PNG"],
    ".webp": [b"RIFF"],          # RIFF....WEBP
    ".pdf":  [b"%PDF"],
}

def _validate_file_magic(data: bytes, ext: str) -> bool:
    """Return True if the file's magic bytes match the claimed extension."""
    signatures = _MAGIC.get(ext.lower(), [])
    if not signatures:
        return False           # unknown extension — reject
    return any(data[:len(sig)] == sig for sig in signatures)

# ── In-memory login rate limiter ───────────────────────────────────────────────
# Limit: 10 failed login attempts per IP per 15 minutes.
# This is intentionally simple and in-memory (resets on container restart).
# For a more persistent solution a Redis-backed approach would be used,
# but for a personal home server this is sufficient.

_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW  = 15 * 60   # 15 minutes in seconds
_RATE_LIMIT_MAX     = 10        # max failures before lockout

def _check_rate_limit(ip: str) -> None:
    now  = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW
    # Remove attempts older than the window
    _login_attempts[ip] = [t for t in _login_attempts[ip] if t > cutoff]
    if len(_login_attempts[ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Please wait 15 minutes."
        )

def _record_failed_attempt(ip: str) -> None:
    _login_attempts[ip].append(time.time())

def _clear_attempts(ip: str) -> None:
    _login_attempts.pop(ip, None)

# ── Session expiry ─────────────────────────────────────────────────────────────
SESSION_LIFETIME_DAYS    = 30   # normal sessions
CHALLENGE_LIFETIME_MINS  = 5    # 2FA challenge tokens expire quickly

# ── Auth helpers ──────────────────────────────────────────────────────────────
# Defined before init_db() so the admin seed at first-run can call _hash_password.

import bcrypt

def _hash_password(password: str) -> str:
    """Hash a password with bcrypt (cost factor 12).
    Returns a string starting with '$2b$' that includes the salt.
    Safe against rainbow tables and brute-force attacks."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def _verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time bcrypt comparison. Returns True if password matches."""
    try:
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    except Exception:
        return False


def _is_legacy_hash(stored: str) -> bool:
    """Return True if this is the old SHA-256 hex hash (64 hex chars, not bcrypt)."""
    return bool(re.fullmatch(r"[0-9a-f]{64}", stored))

def _legacy_hash(password: str) -> str:
    """The old hashing scheme — used only during migration."""
    return hashlib.sha256(f"knitting_library_salt_v1{password}".encode()).hexdigest()


def _user_dict(u: dict) -> dict:
    return {
        "id":           u["id"],
        "username":     u["username"],
        "is_admin":     bool(u["is_admin"]),
        "theme":        u["theme"]        or "light",
        "language":     u["language"]     or "en",
        "currency":     u["currency"]     or "NOK",
        "colour_theme": u["colour_theme"] or "terracotta",
    }

# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    # WAL mode: writes correctly on Windows Docker Desktop bind mounts
    # without creating lock files next to the database file.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS recipes (
            id             TEXT PRIMARY KEY,
            title          TEXT NOT NULL,
            description    TEXT NOT NULL DEFAULT '',
            file_type      TEXT NOT NULL,
            thumbnail_path TEXT NOT NULL DEFAULT '',
            created_date   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS categories (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tags (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recipe_categories (
            recipe_id   TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            PRIMARY KEY (recipe_id, category_id),
            FOREIGN KEY (recipe_id)   REFERENCES recipes(id),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );
        CREATE TABLE IF NOT EXISTS recipe_tags (
            recipe_id TEXT NOT NULL,
            tag_id    INTEGER NOT NULL,
            PRIMARY KEY (recipe_id, tag_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id),
            FOREIGN KEY (tag_id)    REFERENCES tags(id)
        );
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin      INTEGER NOT NULL DEFAULT 0,
            theme         TEXT NOT NULL DEFAULT 'light',
            language      TEXT NOT NULL DEFAULT 'en',
            currency      TEXT NOT NULL DEFAULT 'NOK',
            colour_theme  TEXT NOT NULL DEFAULT 'terracotta',
            created_date  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token        TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL,
            created_date TEXT NOT NULL,
            expires_at   TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS annotations (
            recipe_id TEXT NOT NULL,
            page_key  TEXT NOT NULL,
            data      TEXT NOT NULL DEFAULT '[]',
            updated   TEXT NOT NULL,
            PRIMARY KEY (recipe_id, page_key)
        );
        CREATE TABLE IF NOT EXISTS yarns (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            colour          TEXT NOT NULL DEFAULT '',
            wool_type       TEXT NOT NULL DEFAULT '',
            yardage         TEXT NOT NULL DEFAULT '',
            needles         TEXT NOT NULL DEFAULT '',
            tension         TEXT NOT NULL DEFAULT '',
            origin          TEXT NOT NULL DEFAULT '',
            seller          TEXT NOT NULL DEFAULT '',
            price_per_skein TEXT NOT NULL DEFAULT '',
            product_info    TEXT NOT NULL DEFAULT '',
            image_path      TEXT NOT NULL DEFAULT '',
            created_date    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS yarn_colours (
            id           TEXT PRIMARY KEY,
            yarn_id      TEXT NOT NULL,
            name         TEXT NOT NULL,
            image_path   TEXT NOT NULL DEFAULT '',
            price        TEXT NOT NULL DEFAULT '',
            created_date TEXT NOT NULL,
            FOREIGN KEY (yarn_id) REFERENCES yarns(id)
        );
        CREATE TABLE IF NOT EXISTS project_sessions (
            id             TEXT PRIMARY KEY,
            recipe_id      TEXT NOT NULL,
            started_at     TEXT NOT NULL,
            finished_at    TEXT,
            yarn_id        TEXT,
            yarn_colour_id TEXT,
            FOREIGN KEY (recipe_id) REFERENCES recipes(id),
            FOREIGN KEY (yarn_id)   REFERENCES yarns(id)
        );
        CREATE TABLE IF NOT EXISTS project_feedback (
            id                TEXT PRIMARY KEY,
            recipe_id         TEXT NOT NULL,
            user_id           TEXT NOT NULL,
            session_id        TEXT NOT NULL,
            username          TEXT NOT NULL DEFAULT '',
            rating_recipe     INTEGER NOT NULL DEFAULT 0,
            rating_difficulty INTEGER NOT NULL DEFAULT 0,
            rating_result     INTEGER NOT NULL DEFAULT 0,
            notes             TEXT NOT NULL DEFAULT '',
            created_date      TEXT NOT NULL,
            FOREIGN KEY (recipe_id)  REFERENCES recipes(id),
            FOREIGN KEY (user_id)    REFERENCES users(id),
            FOREIGN KEY (session_id) REFERENCES project_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS inventory_items (
            id             TEXT PRIMARY KEY,
            type           TEXT NOT NULL DEFAULT 'yarn',
            yarn_id        TEXT,
            yarn_colour_id TEXT,
            category       TEXT NOT NULL DEFAULT '',
            name           TEXT NOT NULL,
            quantity       INTEGER NOT NULL DEFAULT 0,
            purchase_date  TEXT NOT NULL DEFAULT '',
            purchase_price TEXT NOT NULL DEFAULT '',
            purchase_note  TEXT NOT NULL DEFAULT '',
            notes          TEXT NOT NULL DEFAULT '',
            created_date   TEXT NOT NULL,
            FOREIGN KEY (yarn_id)        REFERENCES yarns(id),
            FOREIGN KEY (yarn_colour_id) REFERENCES yarn_colours(id)
        );
        CREATE TABLE IF NOT EXISTS inventory_log (
            id         TEXT PRIMARY KEY,
            item_id    TEXT NOT NULL,
            change     INTEGER NOT NULL,
            reason     TEXT NOT NULL DEFAULT 'manual',
            recipe_id  TEXT,
            session_id TEXT,
            note       TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (item_id)    REFERENCES inventory_items(id),
            FOREIGN KEY (recipe_id)  REFERENCES recipes(id),
            FOREIGN KEY (session_id) REFERENCES project_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS import_queue (
            recipe_id  TEXT PRIMARY KEY,
            group_name TEXT NOT NULL DEFAULT '',
            status     TEXT NOT NULL DEFAULT 'staged'
        );
        CREATE TABLE IF NOT EXISTS app_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
    """)
    # Add 2FA columns to users if this is an existing database
    existing = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "totp_secret"  not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN totp_secret  TEXT")
    if "totp_enabled" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0")
    # Add is_challenge and expires_at columns to sessions if missing
    existing_s = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "is_challenge" not in existing_s:
        conn.execute("ALTER TABLE sessions ADD COLUMN is_challenge INTEGER NOT NULL DEFAULT 0")
    if "expires_at" not in existing_s:
        # Give all existing sessions a 30-day expiry from now
        exp = (datetime.utcnow() + timedelta(days=SESSION_LIFETIME_DAYS)).isoformat()
        conn.execute("ALTER TABLE sessions ADD COLUMN expires_at TEXT NOT NULL DEFAULT ?", (exp,))
    # Purge already-expired sessions on startup
    conn.execute("DELETE FROM sessions WHERE expires_at != '' AND expires_at < ?",
                 (datetime.utcnow().isoformat(),))

    # Seed default admin on fresh install
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, is_admin, created_date) VALUES (?,?,?,1,?)",
            (str(uuid.uuid4()), "admin", _hash_password("admin"), datetime.utcnow().isoformat())
        )
        print("Default admin created — username: admin  password: admin — CHANGE THIS IMMEDIATELY")

    conn.commit()
    conn.close()


init_db()

# ── Auth middleware ───────────────────────────────────────────────────────────

def get_current_user(request: Request) -> dict:
    token = request.headers.get("X-Session-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    conn = get_db()
    row = conn.execute(
        "SELECT u.*, s.expires_at FROM users u JOIN sessions s ON u.id=s.user_id "
        "WHERE s.token=? AND s.is_challenge=0", (token,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    # Enforce session expiry
    if row["expires_at"] and row["expires_at"] < datetime.utcnow().isoformat():
        raise HTTPException(status_code=401, detail="Session expired — please log in again")
    return dict(row)


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not current_user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def _verify_token_param(request: Request, token: Optional[str] = None) -> None:
    """Auth check for file-serving endpoints where the browser sends token as
    a query param instead of a header (used by <img> and <iframe> tags)."""
    t = token or request.headers.get("X-Session-Token")
    if not t:
        raise HTTPException(status_code=401, detail="Not logged in")
    conn = get_db()
    row = conn.execute(
        "SELECT u.id, s.expires_at FROM users u JOIN sessions s ON u.id=s.user_id "
        "WHERE s.token=? AND s.is_challenge=0", (t,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    if row["expires_at"] and row["expires_at"] < datetime.utcnow().isoformat():
        raise HTTPException(status_code=401, detail="Session expired")

# ── Auth routes ───────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(data: dict, request: Request):
    # Rate limit by IP to slow brute-force attempts
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
    _check_rate_limit(ip)

    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

    if not user:
        # Record failure even for unknown usernames (prevents username enumeration via timing)
        _record_failed_attempt(ip)
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    stored = user["password_hash"]

    # Migration path: if this user still has the old SHA-256 hash, verify with
    # the legacy scheme and then silently upgrade to bcrypt.
    if _is_legacy_hash(stored):
        if _legacy_hash(password) != stored:
            _record_failed_attempt(ip)
            conn.close()
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        # Upgrade hash in-place
        new_hash = _hash_password(password)
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user["id"]))
        conn.commit()
    else:
        if not _verify_password(password, stored):
            _record_failed_attempt(ip)
            conn.close()
            raise HTTPException(status_code=401, detail="Incorrect username or password")

    _clear_attempts(ip)

    token = secrets.token_hex(32)
    now   = datetime.utcnow().isoformat()

    # If 2FA is enabled, issue a short-lived challenge token — not a real session yet
    if user["totp_enabled"]:
        challenge_exp = (datetime.utcnow() + timedelta(minutes=CHALLENGE_LIFETIME_MINS)).isoformat()
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_date, expires_at, is_challenge) VALUES (?,?,?,?,1)",
            (token, user["id"], now, challenge_exp)
        )
        conn.commit()
        conn.close()
        return {"needs_2fa": True, "challenge_token": token}

    session_exp = (datetime.utcnow() + timedelta(days=SESSION_LIFETIME_DAYS)).isoformat()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_date, expires_at, is_challenge) VALUES (?,?,?,?,0)",
        (token, user["id"], now, session_exp)
    )
    conn.commit()
    conn.close()
    return {"token": token, "user": _user_dict(dict(user))}


@app.post("/api/auth/logout")
def logout(request: Request):
    token = request.headers.get("X-Session-Token")
    if token:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
        conn.close()
    return {"message": "Logged out"}


@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return _user_dict(current_user)


@app.put("/api/auth/settings")
def update_settings(data: dict, current_user: dict = Depends(get_current_user)):
    theme        = data.get("theme",        current_user.get("theme", "light"))
    language     = data.get("language",     current_user.get("language", "en"))
    currency     = data.get("currency",     current_user.get("currency", "NOK"))
    colour_theme = data.get("colour_theme", current_user.get("colour_theme", "terracotta"))
    if theme not in ("light", "dark"):
        raise HTTPException(status_code=400, detail="Invalid theme")
    if language not in ("en", "no"):
        raise HTTPException(status_code=400, detail="Invalid language")
    if currency not in ("NOK", "USD", "GBP"):
        raise HTTPException(status_code=400, detail="Invalid currency")
    if colour_theme not in ("terracotta", "rose", "lavender", "sage", "berry"):
        raise HTTPException(status_code=400, detail="Invalid colour theme")
    conn = get_db()
    conn.execute(
        "UPDATE users SET theme=?, language=?, currency=?, colour_theme=? WHERE id=?",
        (theme, language, currency, colour_theme, current_user["id"])
    )
    conn.commit()
    conn.close()
    return {"theme": theme, "language": language, "currency": currency, "colour_theme": colour_theme}


@app.put("/api/auth/change-password")
def change_password(data: dict, current_user: dict = Depends(get_current_user)):
    old_pw = data.get("old_password", "")
    new_pw = data.get("new_password", "")
    if not old_pw or not new_pw:
        raise HTTPException(status_code=400, detail="Both passwords required")
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    conn = get_db()
    row  = conn.execute("SELECT password_hash FROM users WHERE id=?", (current_user["id"],)).fetchone()
    stored = row["password_hash"] if row else ""
    # Support both legacy and bcrypt hashes during migration window
    ok = (_legacy_hash(old_pw) == stored) if _is_legacy_hash(stored) else _verify_password(old_pw, stored)
    if not ok:
        conn.close()
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash_password(new_pw), current_user["id"]))
    conn.commit()
    conn.close()
    return {"message": "Password changed"}

# ── Admin: user management ────────────────────────────────────────────────────

@app.get("/api/admin/users")
def list_users(admin: dict = Depends(require_admin)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, is_admin, theme, language, created_date FROM users ORDER BY created_date"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/admin/users")
def create_user(data: dict, admin: dict = Depends(require_admin)):
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    conn = get_db()
    if conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    uid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO users (id, username, password_hash, is_admin, created_date) VALUES (?,?,?,?,?)",
        (uid, username, _hash_password(password), 1 if data.get("is_admin") else 0, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return {"id": uid, "username": username, "is_admin": bool(data.get("is_admin"))}


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM users    WHERE id=?",      (user_id,))
    conn.commit()
    conn.close()
    return {"message": "User deleted"}


@app.put("/api/admin/users/{user_id}/reset-password")
def reset_password(user_id: str, data: dict, admin: dict = Depends(require_admin)):
    new_pw = data.get("new_password", "")
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    conn = get_db()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash_password(new_pw), user_id))
    conn.commit()
    conn.close()
    return {"message": "Password reset"}

# ── Shared helpers ────────────────────────────────────────────────────────────

def _save_cats_tags(conn, recipe_id: str, categories: str, tags: str):
    for name in [c.strip() for c in categories.split(",") if c.strip()]:
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()
        if row:
            conn.execute("INSERT OR IGNORE INTO recipe_categories (recipe_id,category_id) VALUES (?,?)", (recipe_id, row["id"]))
    for name in [t.strip() for t in tags.split(",") if t.strip()]:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
        if row:
            conn.execute("INSERT OR IGNORE INTO recipe_tags (recipe_id,tag_id) VALUES (?,?)", (recipe_id, row["id"]))


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
            for ext in IMAGE_EXTS:
                candidates = sorted(f for f in recipe_dir.glob(f"*{ext}") if f.name != "thumbnail.jpg")
                if candidates:
                    from PIL import Image
                    img = Image.open(candidates[0])
                    img.thumbnail((400, 400))
                    img.save(str(thumb), "JPEG", quality=85)
                    return "thumbnail.jpg"
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")
    return ""


def _get_recipe_full(recipe_id: str, conn) -> Optional[dict]:
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
        images = []
        for ext in IMAGE_EXTS:
            images.extend(sorted(recipe_dir.glob(f"*{ext}")))
        recipe["images"] = sorted([f.name for f in images if f.name != "thumbnail.jpg"])
    else:
        recipe["images"] = []
    sessions = conn.execute(
        """SELECT ps.id, ps.started_at, ps.finished_at, ps.yarn_id, ps.yarn_colour_id,
                  y.name as yarn_name, yc.name as yarn_colour
           FROM project_sessions ps
           LEFT JOIN yarns y        ON ps.yarn_id=y.id
           LEFT JOIN yarn_colours yc ON ps.yarn_colour_id=yc.id
           WHERE ps.recipe_id=? ORDER BY ps.started_at ASC""",
        (recipe_id,)
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
    all_fb = conn.execute(
        "SELECT rating_recipe, rating_difficulty, rating_result FROM project_feedback WHERE recipe_id=?",
        (recipe_id,)
    ).fetchall()
    if all_fb:
        total = sum(f["rating_recipe"] + f["rating_difficulty"] + f["rating_result"] for f in all_fb)
        recipe["avg_score"]      = round(total / (len(all_fb) * 3), 1)
        recipe["feedback_count"] = len(all_fb)
    else:
        recipe["avg_score"]      = None
        recipe["feedback_count"] = 0
    active = next((s for s in reversed(recipe["sessions"]) if not s["finished_at"]), None)
    if active:
        recipe["project_status"]    = "active"
        recipe["active_session_id"] = active["id"]
        recipe["active_started_at"] = active["started_at"]
    elif recipe["sessions"]:
        recipe["project_status"] = "finished"
    else:
        recipe["project_status"] = "none"
    return recipe

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}

# ── Recipes ───────────────────────────────────────────────────────────────────

@app.get("/api/recipes")
def list_recipes(
    search:   Optional[str] = None,
    category: Optional[str] = None,
    tags:     Optional[str] = None,
    status:   Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    query = """
        SELECT DISTINCT r.id
        FROM recipes r
        LEFT JOIN recipe_categories rc ON r.id=rc.recipe_id
        LEFT JOIN categories c         ON rc.category_id=c.id
        LEFT JOIN recipe_tags rt       ON r.id=rt.recipe_id
        LEFT JOIN tags t               ON rt.tag_id=t.id
        WHERE 1=1
    """
    params = []
    if search:
        like = f"%{search}%"
        query += " AND (r.title LIKE ? OR r.description LIKE ? OR t.name LIKE ?)"
        params.extend([like, like, like])
    if category:
        query += " AND c.name=?"; params.append(category)
    if tags:
        tl = [t.strip() for t in tags.split(",") if t.strip()]
        query += f" AND t.name IN ({','.join('?'*len(tl))})"; params.extend(tl)
    query += " ORDER BY r.created_date DESC"
    rows   = conn.execute(query, params).fetchall()
    result = [r for r in (_get_recipe_full(row["id"], conn) for row in rows) if r]
    conn.close()
    if status in ("active", "started"):
        result = [r for r in result if r["project_status"] == "active"]
    elif status == "finished":
        result = [r for r in result if r["project_status"] == "finished"]
    result.sort(key=lambda r: {"active": 0, "finished": 1}.get(r["project_status"], 2))
    return result


@app.get("/api/recipes/{recipe_id}")
def get_recipe(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn   = get_db()
    recipe = _get_recipe_full(recipe_id, conn)
    conn.close()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@app.post("/api/recipes")
async def create_recipe(
    title:       str = Form(...),
    description: str = Form(""),
    categories:  str = Form(""),
    tags:        str = Form(""),
    files:       List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    recipe_id  = str(uuid.uuid4())
    recipe_dir = DATA_DIR / recipe_id
    recipe_dir.mkdir(parents=True)
    saved, file_type = [], "images"
    for upload in files:
        ext = Path(upload.filename.lower()).suffix
        if ext not in IMAGE_EXTS and ext != ".pdf":
            continue
        # Read the file data first so we can validate it
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
            # Use only the bare filename — no path components
            dest_name = Path(upload.filename).name
        with open(recipe_dir / dest_name, "wb") as f:
            f.write(file_data)
        saved.append(dest_name)
    if not saved:
        shutil.rmtree(recipe_dir)
        raise HTTPException(status_code=400, detail="No valid files uploaded")
    if file_type == "pdf":
        _convert_pdf_to_pages(recipe_dir)
    thumb = _generate_thumbnail(recipe_dir, file_type)
    conn  = get_db()
    conn.execute(
        "INSERT INTO recipes (id,title,description,file_type,thumbnail_path,created_date) VALUES (?,?,?,?,?,?)",
        (recipe_id, title, description, file_type, thumb, datetime.utcnow().isoformat())
    )
    _save_cats_tags(conn, recipe_id, categories, tags)
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn)
    conn.close()
    return recipe


@app.put("/api/recipes/{recipe_id}")
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
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn)
    conn.close()
    return recipe


@app.delete("/api/recipes/{recipe_id}")
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
    conn.execute("DELETE FROM recipes           WHERE id=?",        (recipe_id,))
    conn.commit()
    conn.close()
    recipe_dir = DATA_DIR / recipe_id
    if recipe_dir.exists():
        shutil.rmtree(recipe_dir)
    return {"message": "Recipe deleted"}


@app.get("/api/categories")
def list_categories(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


@app.post("/api/categories")
def add_category(data: dict, current_user: dict = Depends(get_current_user)):
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()
    return {"message": f"Category '{name}' added"}


@app.delete("/api/categories/{name}")
def delete_category(name: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row  = conn.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Category not found")
    conn.execute("DELETE FROM recipe_categories WHERE category_id=?", (row["id"],))
    conn.execute("DELETE FROM categories        WHERE id=?",          (row["id"],))
    conn.commit()
    conn.close()
    return {"message": f"Category '{name}' deleted"}


@app.get("/api/tags")
def list_tags(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT t.name FROM tags t JOIN recipe_tags rt ON t.id=rt.tag_id ORDER BY t.name"
    ).fetchall()
    conn.close()
    return [r["name"] for r in rows]

# ── File serving ──────────────────────────────────────────────────────────────

@app.get("/api/recipes/{recipe_id}/thumbnail")
def get_thumbnail(recipe_id: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    thumb = DATA_DIR / recipe_id / "thumbnail.jpg"
    if thumb.exists():
        return FileResponse(str(thumb), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Thumbnail not found")


@app.get("/api/recipes/{recipe_id}/pdf")
def get_pdf(recipe_id: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    pdf = DATA_DIR / recipe_id / "recipe.pdf"
    if pdf.exists():
        return FileResponse(str(pdf), media_type="application/pdf")
    raise HTTPException(status_code=404, detail="PDF not found")


@app.get("/api/recipes/{recipe_id}/images/{filename}")
def get_image(recipe_id: str, filename: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    safe = Path(filename).name          # strip any path traversal attempt
    path = DATA_DIR / recipe_id / safe
    if path.exists():
        return FileResponse(str(path))
    raise HTTPException(status_code=404, detail="Image not found")


@app.get("/api/recipes/{recipe_id}/pdf-pages")
def get_pdf_pages(recipe_id: str, current_user: dict = Depends(get_current_user)):
    pages = sorted((DATA_DIR / recipe_id).glob("page-*.jpg"))
    return {"pages": [p.name for p in pages]}


@app.post("/api/recipes/{recipe_id}/convert-pdf")
def convert_pdf(recipe_id: str, current_user: dict = Depends(get_current_user)):
    """Manually trigger PDF-to-pages conversion (for recipes uploaded before this feature)."""
    recipe_dir = DATA_DIR / recipe_id
    if not (recipe_dir / "recipe.pdf").exists():
        raise HTTPException(status_code=404, detail="No PDF found for this recipe")
    _convert_pdf_to_pages(recipe_dir)
    pages = sorted(recipe_dir.glob("page-*.jpg"))
    return {"pages": [p.name for p in pages]}


@app.get("/api/recipes/{recipe_id}/pdf-pages/{filename}")
def get_pdf_page_image(recipe_id: str, filename: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    safe = Path(filename).name
    path = DATA_DIR / recipe_id / safe
    if path.exists() and safe.startswith("page-") and safe.endswith(".jpg"):
        return FileResponse(str(path), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Page not found")

# ── Project sessions ──────────────────────────────────────────────────────────

@app.post("/api/recipes/{recipe_id}/start")
def start_project(recipe_id: str, body: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    if conn.execute("SELECT id FROM project_sessions WHERE recipe_id=? AND finished_at IS NULL", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Project already active")
    session_id = str(uuid.uuid4())
    now        = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO project_sessions (id, recipe_id, started_at, yarn_id, yarn_colour_id) VALUES (?,?,?,?,?)",
        (session_id, recipe_id, now, body.get("yarn_id") or None, body.get("yarn_colour_id") or None)
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
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn)
    conn.close()
    return recipe


@app.post("/api/recipes/{recipe_id}/finish")
def finish_project(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn   = get_db()
    active = conn.execute("SELECT id FROM project_sessions WHERE recipe_id=? AND finished_at IS NULL", (recipe_id,)).fetchone()
    if not active:
        conn.close()
        raise HTTPException(status_code=400, detail="No active session")
    conn.execute("UPDATE project_sessions SET finished_at=? WHERE id=?", (datetime.utcnow().isoformat(), active["id"]))
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn)
    conn.close()
    return recipe


@app.post("/api/recipes/{recipe_id}/feedback")
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
    sess = conn.execute(
        "SELECT id, finished_at FROM project_sessions WHERE id=? AND recipe_id=?", (session_id, recipe_id)
    ).fetchone()
    if not sess:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")
    now = datetime.utcnow().isoformat()
    if data.get("finish_session") and not sess["finished_at"]:
        conn.execute("UPDATE project_sessions SET finished_at=? WHERE id=?", (now, session_id))
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
    recipe = _get_recipe_full(recipe_id, conn)
    conn.close()
    return recipe


@app.get("/api/recipes/{recipe_id}/feedback/{session_id}")
def get_session_feedback(recipe_id: str, session_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, user_id, username, rating_recipe, rating_difficulty, rating_result, notes, created_date FROM project_feedback WHERE session_id=? AND recipe_id=?",
        (session_id, recipe_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.delete("/api/recipes/{recipe_id}/sessions")
def clear_sessions(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    conn.execute("DELETE FROM project_feedback WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM project_sessions  WHERE recipe_id=?", (recipe_id,))
    conn.commit()
    recipe = _get_recipe_full(recipe_id, conn)
    conn.close()
    return recipe

# ── Annotations ───────────────────────────────────────────────────────────────

@app.get("/api/recipes/{recipe_id}/annotations/{page_key}")
def get_annotations(recipe_id: str, page_key: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row  = conn.execute("SELECT data FROM annotations WHERE recipe_id=? AND page_key=?", (recipe_id, page_key)).fetchone()
    conn.close()
    return {"strokes": json.loads(row["data"]) if row else []}


@app.put("/api/recipes/{recipe_id}/annotations/{page_key}")
def save_annotations(recipe_id: str, page_key: str, data: dict, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    conn.execute(
        "INSERT INTO annotations (recipe_id,page_key,data,updated) VALUES (?,?,?,?) "
        "ON CONFLICT(recipe_id,page_key) DO UPDATE SET data=excluded.data, updated=excluded.updated",
        (recipe_id, page_key, json.dumps(data.get("strokes", [])), datetime.utcnow().isoformat())
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

# ── Bulk import ───────────────────────────────────────────────────────────────

@app.post("/api/import/upload-group")
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
            dest_name = Path(upload.filename).name
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


@app.get("/api/import/queue")
def import_get_queue(current_user: dict = Depends(get_current_user)):
    conn  = get_db()
    rows  = conn.execute("SELECT recipe_id, group_name FROM import_queue WHERE status='staged' ORDER BY rowid").fetchall()
    items = []
    for row in rows:
        recipe = _get_recipe_full(row["recipe_id"], conn)
        if recipe:
            items.append({"recipe_id": row["recipe_id"], "group_name": row["group_name"], "recipe": recipe})
    conn.close()
    return {"items": items, "count": len(items)}


@app.post("/api/import/confirm/{recipe_id}")
def import_confirm(recipe_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    title = data.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    conn = get_db()
    if not conn.execute("SELECT recipe_id FROM import_queue WHERE recipe_id=? AND status='staged'", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Staged recipe not found")
    conn.execute("UPDATE recipes SET title=?, description=? WHERE id=?", (title, data.get("description", ""), recipe_id))
    conn.execute("DELETE FROM recipe_categories WHERE recipe_id=?", (recipe_id,))
    conn.execute("DELETE FROM recipe_tags       WHERE recipe_id=?", (recipe_id,))
    _save_cats_tags(conn, recipe_id, data.get("categories", ""), data.get("tags", ""))
    conn.execute("UPDATE import_queue SET status='done' WHERE recipe_id=?", (recipe_id,))
    conn.commit()
    conn.close()
    return {"status": "confirmed", "recipe_id": recipe_id}


@app.post("/api/import/discard/{recipe_id}")
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

@app.get("/api/export")
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

# ── Yarn database ─────────────────────────────────────────────────────────────

def _yarn_to_dict(row, conn) -> dict:
    d = dict(row)
    d["colours"] = [dict(c) for c in conn.execute(
        "SELECT id, name, image_path, price FROM yarn_colours WHERE yarn_id=? ORDER BY created_date ASC",
        (d["id"],)
    ).fetchall()]
    return d


@app.get("/api/yarns")
def list_yarns(
    search:           Optional[str] = None,
    field:            Optional[str] = None,
    filter_colour:    Optional[str] = None,
    filter_wool_type: Optional[str] = None,
    filter_seller:    Optional[str] = None,
    current_user:     dict = Depends(get_current_user)
):
    conn   = get_db()
    query  = "SELECT * FROM yarns WHERE 1=1"
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
            params.extend([like] * 6)
    if filter_colour:
        query += " AND colour=?"; params.append(filter_colour)
    if filter_wool_type:
        query += " AND wool_type=?"; params.append(filter_wool_type)
    if filter_seller:
        query += " AND seller=?"; params.append(filter_seller)
    query += " ORDER BY created_date DESC"
    result = [_yarn_to_dict(r, conn) for r in conn.execute(query, params).fetchall()]
    conn.close()
    return result


@app.get("/api/yarns/autocomplete")
def yarn_autocomplete(field: str, current_user: dict = Depends(get_current_user)):
    allowed = {"name", "colour", "wool_type", "origin", "seller"}
    if field not in allowed:
        raise HTTPException(status_code=400, detail="Invalid field")
    conn = get_db()
    rows = conn.execute(
        f"SELECT DISTINCT {field} FROM yarns WHERE {field} != '' ORDER BY {field}"
    ).fetchall()
    conn.close()
    return {"values": [r[field] for r in rows]}


@app.get("/api/yarns/{yarn_id}")
def get_yarn(yarn_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row  = conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Yarn not found")
    result = _yarn_to_dict(row, conn)
    conn.close()
    return result


@app.post("/api/yarns")
def create_yarn(body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    yarn_id = str(uuid.uuid4())
    conn    = get_db()
    conn.execute(
        "INSERT INTO yarns (id,name,colour,wool_type,yardage,needles,tension,origin,seller,price_per_skein,product_info,image_path,created_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (yarn_id, name,
         body.get("colour",""), body.get("wool_type",""), body.get("yardage",""),
         body.get("needles",""), body.get("tension",""), body.get("origin",""),
         body.get("seller",""), body.get("price_per_skein",""), body.get("product_info",""),
         body.get("image_path",""), datetime.utcnow().isoformat())
    )
    conn.commit()
    result = _yarn_to_dict(conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone(), conn)
    conn.close()
    return result


@app.put("/api/yarns/{yarn_id}")
def update_yarn(yarn_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarns WHERE id=?", (yarn_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Yarn not found")
    conn.execute(
        "UPDATE yarns SET name=?,colour=?,wool_type=?,yardage=?,needles=?,tension=?,origin=?,seller=?,price_per_skein=?,product_info=? WHERE id=?",
        (body.get("name",""), body.get("colour",""), body.get("wool_type",""), body.get("yardage",""),
         body.get("needles",""), body.get("tension",""), body.get("origin",""), body.get("seller",""),
         body.get("price_per_skein",""), body.get("product_info",""), yarn_id)
    )
    conn.commit()
    result = _yarn_to_dict(conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone(), conn)
    conn.close()
    return result


@app.delete("/api/yarns/{yarn_id}")
def delete_yarn(yarn_id: str, current_user: dict = Depends(get_current_user)):
    conn     = get_db()
    yarn_dir = YARN_DIR / yarn_id
    conn.execute("DELETE FROM yarn_colours WHERE yarn_id=?", (yarn_id,))
    conn.execute("DELETE FROM yarns        WHERE id=?",      (yarn_id,))
    conn.commit()
    conn.close()
    if yarn_dir.exists():
        shutil.rmtree(yarn_dir)
    return {"message": "Yarn deleted"}


@app.get("/api/yarns/{yarn_id}/image")
def get_yarn_image(yarn_id: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    yarn_dir = YARN_DIR / yarn_id
    for name in ("thumbnail.jpg", "yarn.jpg", "yarn.jpeg", "yarn.png", "yarn.webp"):
        p = yarn_dir / name
        if p.exists():
            mt = "image/jpeg" if name.endswith((".jpg",".jpeg")) else "image/png" if name.endswith(".png") else "image/webp"
            return FileResponse(str(p), media_type=mt)
    raise HTTPException(status_code=404, detail="No image")

# ── Yarn colours ──────────────────────────────────────────────────────────────

@app.get("/api/yarns/{yarn_id}/colours")
def list_yarn_colours(yarn_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM yarn_colours WHERE yarn_id=? ORDER BY created_date ASC", (yarn_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/yarns/{yarn_id}/colours")
def add_yarn_colour(yarn_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    colour_id = str(uuid.uuid4())
    conn      = get_db()
    conn.execute(
        "INSERT INTO yarn_colours (id,yarn_id,name,image_path,price,created_date) VALUES (?,?,?,?,?,?)",
        (colour_id, yarn_id, name, body.get("image_path",""), body.get("price",""), datetime.utcnow().isoformat())
    )
    conn.commit()
    result = dict(conn.execute("SELECT * FROM yarn_colours WHERE id=?", (colour_id,)).fetchone())
    conn.close()
    return result


@app.put("/api/yarns/{yarn_id}/colours/{colour_id}")
def update_yarn_colour(yarn_id: str, colour_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarn_colours WHERE id=? AND yarn_id=?", (colour_id, yarn_id)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Colour not found")
    conn.execute(
        "UPDATE yarn_colours SET name=?, image_path=?, price=? WHERE id=?",
        (body.get("name",""), body.get("image_path",""), body.get("price",""), colour_id)
    )
    conn.commit()
    result = dict(conn.execute("SELECT * FROM yarn_colours WHERE id=?", (colour_id,)).fetchone())
    conn.close()
    return result


@app.delete("/api/yarns/{yarn_id}/colours/{colour_id}")
def delete_yarn_colour(yarn_id: str, colour_id: str, current_user: dict = Depends(get_current_user)):
    conn   = get_db()
    colour = conn.execute("SELECT image_path FROM yarn_colours WHERE id=? AND yarn_id=?", (colour_id, yarn_id)).fetchone()
    if not colour:
        conn.close()
        raise HTTPException(status_code=404, detail="Colour not found")
    image_path = colour["image_path"]
    conn.execute("DELETE FROM yarn_colours WHERE id=?", (colour_id,))
    conn.commit()
    conn.close()
    if image_path:
        p = Path(image_path) if Path(image_path).is_absolute() else YARN_DIR / image_path
        p.unlink(missing_ok=True)
    return {"message": "Colour deleted"}


@app.post("/api/yarns/{yarn_id}/colours/{colour_id}/image")
async def upload_colour_image(
    yarn_id:   str,
    colour_id: str,
    file:      UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarn_colours WHERE id=? AND yarn_id=?", (colour_id, yarn_id)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Colour not found")
    colour_dir = YARN_DIR / yarn_id / "colours" / colour_id
    colour_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix.lower()
    if ext not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Only jpg, png, webp images are accepted")
    file_data = await file.read()
    if len(file_data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image file too large (max 20 MB)")
    if not _validate_file_magic(file_data, ext):
        raise HTTPException(status_code=400, detail="File content does not match its extension")
    dest = colour_dir / f"colour{ext}"
    with open(dest, "wb") as f:
        f.write(file_data)
    rel_path = str(dest.relative_to(YARN_DIR))
    conn.execute("UPDATE yarn_colours SET image_path=? WHERE id=?", (rel_path, colour_id))
    conn.commit()
    conn.close()
    return {"image_path": rel_path}


@app.get("/api/yarns/{yarn_id}/colours/{colour_id}/image")
def get_colour_image(yarn_id: str, colour_id: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    conn   = get_db()
    colour = conn.execute("SELECT image_path FROM yarn_colours WHERE id=? AND yarn_id=?", (colour_id, yarn_id)).fetchone()
    conn.close()
    if not colour or not colour["image_path"]:
        raise HTTPException(status_code=404, detail="No image")
    path = YARN_DIR / colour["image_path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")
    ext = path.suffix.lower()
    mt  = "image/jpeg" if ext in (".jpg",".jpeg") else "image/png" if ext == ".png" else "image/webp"
    return FileResponse(str(path), media_type=mt)


@app.post("/api/yarns/{yarn_id}/image")
async def upload_yarn_image(
    yarn_id: str,
    file:    UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarns WHERE id=?", (yarn_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Yarn not found")
    yarn_dir = YARN_DIR / yarn_id
    yarn_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix.lower()
    if ext not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Only jpg, png, webp images are accepted")
    file_data = await file.read()
    if len(file_data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image file too large (max 20 MB)")
    if not _validate_file_magic(file_data, ext):
        raise HTTPException(status_code=400, detail="File content does not match its extension")
    dest = yarn_dir / f"yarn{ext}"
    with open(dest, "wb") as f:
        f.write(file_data)
    rel_path = f"{yarn_id}/yarn{ext}"
    conn.execute("UPDATE yarns SET image_path=? WHERE id=?", (rel_path, yarn_id))
    conn.commit()
    conn.close()
    return {"image_path": rel_path}

# ── Inventory ─────────────────────────────────────────────────────────────────

def _inventory_to_dict(row, conn) -> dict:
    d = dict(row)
    if d.get("type") == "yarn":
        yarn   = conn.execute("SELECT name FROM yarns WHERE id=?", (d["yarn_id"],)).fetchone() if d.get("yarn_id") else None
        colour = conn.execute("SELECT name, image_path FROM yarn_colours WHERE id=?", (d["yarn_colour_id"],)).fetchone() if d.get("yarn_colour_id") else None
        d["yarn_name"]         = yarn["name"]         if yarn   else ""
        d["colour_name"]       = colour["name"]       if colour else ""
        d["colour_image_path"] = colour["image_path"] if colour else ""
    return d


@app.get("/api/inventory")
def list_inventory(
    type:   Optional[str] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    conn   = get_db()
    query  = "SELECT * FROM inventory_items WHERE 1=1"
    params = []
    if type:
        query += " AND type=?"; params.append(type)
    if search:
        like   = f"%{search}%"
        query += " AND (name LIKE ? OR notes LIKE ?)"; params.extend([like, like])
    query += " ORDER BY created_date DESC"
    result = [_inventory_to_dict(r, conn) for r in conn.execute(query, params).fetchall()]
    conn.close()
    return result


@app.get("/api/inventory/{item_id}")
def get_inventory_item(item_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row  = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    result = _inventory_to_dict(row, conn)
    conn.close()
    return result


@app.get("/api/inventory/{item_id}/log")
def get_inventory_log(item_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT l.*, r.title as recipe_title FROM inventory_log l LEFT JOIN recipes r ON l.recipe_id=r.id WHERE l.item_id=? ORDER BY l.created_at DESC",
        (item_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/inventory")
def create_inventory_item(body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    item_id = str(uuid.uuid4())
    qty     = int(body.get("quantity", 0))
    now     = datetime.utcnow().isoformat()
    conn    = get_db()
    conn.execute(
        "INSERT INTO inventory_items (id,type,yarn_id,yarn_colour_id,category,name,quantity,purchase_date,purchase_price,purchase_note,notes,created_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (item_id, body.get("type","yarn"), body.get("yarn_id") or None, body.get("yarn_colour_id") or None,
         body.get("category",""), name, qty, body.get("purchase_date",""), body.get("purchase_price",""),
         body.get("purchase_note",""), body.get("notes",""), now)
    )
    if qty > 0:
        conn.execute(
            "INSERT INTO inventory_log (id,item_id,change,reason,note,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), item_id, qty, "added", "Initial stock", now)
        )
    conn.commit()
    result = _inventory_to_dict(conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone(), conn)
    conn.close()
    return result


@app.put("/api/inventory/{item_id}")
def update_inventory_item(item_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row  = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    conn.execute(
        "UPDATE inventory_items SET category=?,name=?,purchase_date=?,purchase_price=?,purchase_note=?,notes=?,yarn_id=?,yarn_colour_id=? WHERE id=?",
        (body.get("category",       row["category"]),
         (body.get("name",          row["name"]) or "").strip() or row["name"],
         body.get("purchase_date",  row["purchase_date"]),
         body.get("purchase_price", row["purchase_price"]),
         body.get("purchase_note",  row["purchase_note"]),
         body.get("notes",          row["notes"]),
         body.get("yarn_id")        or row["yarn_id"],
         body.get("yarn_colour_id") or row["yarn_colour_id"],
         item_id)
    )
    conn.commit()
    result = _inventory_to_dict(conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone(), conn)
    conn.close()
    return result


@app.post("/api/inventory/{item_id}/adjust")
def adjust_inventory(item_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    conn   = get_db()
    row    = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    change = int(body.get("change", 0))
    if change == 0:
        conn.close()
        raise HTTPException(status_code=400, detail="change cannot be 0")
    now = datetime.utcnow().isoformat()
    conn.execute("UPDATE inventory_items SET quantity=? WHERE id=?", (max(0, row["quantity"] + change), item_id))
    conn.execute(
        "INSERT INTO inventory_log (id,item_id,change,reason,recipe_id,session_id,note,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), item_id, change, body.get("reason","manual"),
         body.get("recipe_id") or None, body.get("session_id") or None, body.get("note",""), now)
    )
    conn.commit()
    result = _inventory_to_dict(conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone(), conn)
    conn.close()
    return result


@app.delete("/api/inventory/{item_id}")
def delete_inventory_item(item_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM inventory_items WHERE id=?", (item_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    conn.execute("DELETE FROM inventory_log   WHERE item_id=?", (item_id,))
    conn.execute("DELETE FROM inventory_items WHERE id=?",      (item_id,))
    conn.commit()
    conn.close()
    return {"message": "Deleted"}

# ── Yarn URL scraper ──────────────────────────────────────────────────────────

@app.post("/api/yarns/scrape")
async def scrape_yarn_url(body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    """Fetch a yarn product page and extract key fields.
    Strategy 1: Shopify JSON API  (fast, structured).
    Strategy 2: HTML scraping fallback."""
    url = (body.get("url") or "").strip()
    if not url or not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Valid http/https URL required")

    # SSRF protection — reject requests to private/internal network addresses
    parsed   = urlparse(url)
    hostname = parsed.hostname or ""
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise HTTPException(status_code=400, detail="URL not allowed")
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(status_code=400, detail="URL not allowed")
    except (socket.gaierror, ValueError):
        pass  # unresolvable hostname — let httpx handle it

    headers = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7",
    }

    label_map = {
        "løpelengde": "yardage",  "run length": "yardage",  "meterage": "yardage",  "yardage": "yardage",
        "veiledende pinner": "needles", "anbefalt pinnestørrelse": "needles",
        "needle size": "needles", "pinner": "needles",
        "strikkefasthet": "tension", "gauge": "tension", "tension": "tension",
        "råvare kommer fra": "origin", "raw material": "origin", "opprinnelse": "origin",
        "sammensetning": "wool_type", "composition": "wool_type",
        "fiber content": "wool_type", "material": "wool_type",
    }

    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip() if s else ""

    def _parse_specs(soup, result: dict):
        for el in soup.find_all(["li", "dt", "dd", "p", "span", "td", "th"]):
            text = _clean(el.get_text())
            if ":" in text:
                k, _, v = text.partition(":")
                for label, field in label_map.items():
                    if label in k.strip().lower() and field not in result and v.strip():
                        result[field] = v.strip()
                        break

    handle      = parsed.path.strip("/").split("/")[-1].split("?")[0]
    shopify_url = f"{parsed.scheme}://{parsed.netloc}/products/{handle}.json"

    # Strategy 1: Shopify JSON API
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            sj = await client.get(shopify_url, headers=headers)
        if sj.status_code == 200:
            product = sj.json().get("product", {})
            if product.get("title"):
                result: dict = {"name": product["title"]}
                if product.get("vendor"):
                    result["seller"] = product["vendor"]
                if product.get("body_html"):
                    soup = BeautifulSoup(product["body_html"], "html.parser")
                    _parse_specs(soup, result)
                    plain = _clean(soup.get_text(" "))
                    if plain:
                        result["product_info"] = plain[:1000]
                images = product.get("images", [])
                if images:
                    src = re.sub(r"_\d+x\d+(\.[a-z]+)$", r"\1", images[0].get("src", ""))
                    if src:
                        result["scraped_image_url"] = src
                return result
    except Exception:
        pass

    # Strategy 2: HTML scraping
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            resp = await client.get(url, headers=headers)
        soup   = BeautifulSoup(resp.text, "html.parser")
        result = {}
        h1     = soup.find("h1")
        if h1:
            result["name"] = _clean(h1.get_text())
        _parse_specs(soup, result)
        meta = soup.find("meta", {"property": "og:image"}) or soup.find("meta", {"name": "og:image"})
        if meta and meta.get("content"):
            result["scraped_image_url"] = meta["content"]
        if not result.get("name"):
            raise HTTPException(status_code=422, detail="Could not extract product name from page")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {e}")

# ── Admin: live logs ──────────────────────────────────────────────────────────

@app.get("/api/admin/logs")
def get_logs(lines: int = 200, source: str = "all", admin: dict = Depends(require_admin)):
    """Return the last N lines from the persistent log files in /logs/.
    source: 'all' | 'uvicorn' | 'nginx' | 'supervisord'
    """
    lines = max(10, min(lines, 1000))

    log_files = {
        "uvicorn":    Path("/logs/uvicorn.log"),
        "nginx":      Path("/logs/nginx.log"),
        "supervisord": Path("/logs/supervisord.log"),
    }

    sources = list(log_files.keys()) if source == "all" else [source]
    collected = []

    for src in sources:
        path = log_files.get(src)
        if not path or not path.exists():
            collected.append(f"[{src}] no log file yet — container may have just started")
            continue
        try:
            with open(path, "r", errors="replace") as f:
                file_lines = f.readlines()
            for line in file_lines:
                stripped = line.rstrip()
                if stripped:
                    collected.append(f"[{src}] {stripped}")
        except Exception as e:
            collected.append(f"[{src}] could not read log: {e}")

    result = collected[-lines:] if len(collected) > lines else collected
    return {"lines": result}

# ── Admin: mail settings ──────────────────────────────────────────────────────

@app.get("/api/admin/mail")
def get_mail_settings(admin: dict = Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'mail_%'").fetchall()
    conn.close()
    settings = {r["key"]: r["value"] for r in rows}
    # Never return the password in plaintext — return a mask if set
    if settings.get("mail_password"):
        settings["mail_password"] = "••••••••"
    return settings


@app.put("/api/admin/mail")
def save_mail_settings(data: dict, admin: dict = Depends(require_admin)):
    allowed = {"mail_host", "mail_port", "mail_username", "mail_password",
               "mail_from", "mail_tls", "mail_enabled"}
    conn = get_db()
    for key, value in data.items():
        if key not in allowed:
            continue
        # Don't overwrite the password if the frontend sends back the mask
        if key == "mail_password" and value == "••••••••":
            continue
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )
    conn.commit()
    conn.close()
    return {"message": "Mail settings saved"}


@app.post("/api/admin/mail/test")
async def test_mail(data: dict, admin: dict = Depends(require_admin)):
    """Send a test email using the stored SMTP settings."""
    import smtplib
    from email.mime.text import MIMEText
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'mail_%'").fetchall()
    conn.close()
    cfg = {r["key"]: r["value"] for r in rows}
    to_addr = data.get("to", "").strip()
    if not to_addr:
        raise HTTPException(status_code=400, detail="Recipient email required")
    host     = cfg.get("mail_host", "")
    port     = int(cfg.get("mail_port", 587))
    username = cfg.get("mail_username", "")
    password = cfg.get("mail_password", "")
    from_addr = cfg.get("mail_from", username)
    use_tls  = cfg.get("mail_tls", "true").lower() == "true"
    if not host or not username or not password:
        raise HTTPException(status_code=400, detail="Mail server not configured")
    try:
        msg = MIMEText("This is a test email from your Knitting Library. Mail is working correctly.")
        msg["Subject"] = "Knitting Library — Test Email"
        msg["From"]    = from_addr
        msg["To"]      = to_addr
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=10)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        server.login(username, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
        return {"message": "Test email sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Mail send failed: {e}")

# ── Admin: 2FA management ─────────────────────────────────────────────────────

@app.get("/api/admin/2fa/status")
def get_2fa_status(admin: dict = Depends(require_admin)):
    """Return 2FA status for every user."""
    conn = get_db()
    users = conn.execute(
        "SELECT id, username, totp_enabled FROM users ORDER BY created_date"
    ).fetchall()
    conn.close()
    return [{"id": u["id"], "username": u["username"], "totp_enabled": bool(u["totp_enabled"])} for u in users]


@app.delete("/api/admin/2fa/{user_id}")
def admin_reset_2fa(user_id: str, admin: dict = Depends(require_admin)):
    """Admin resets a user's 2FA — they will need to set it up again."""
    conn = get_db()
    conn.execute("UPDATE users SET totp_secret=NULL, totp_enabled=0 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"message": "2FA reset"}

# ── User: 2FA setup ───────────────────────────────────────────────────────────

@app.get("/api/auth/2fa/setup")
def setup_2fa(current_user: dict = Depends(get_current_user)):
    """Generate a new TOTP secret and return a QR code URI for the authenticator app."""
    import pyotp, qrcode, base64, io as _io
    secret = pyotp.random_base32()
    totp   = pyotp.TOTP(secret)
    uri    = totp.provisioning_uri(name=current_user["username"], issuer_name="Knitting Library")
    # Generate QR code as base64 PNG
    qr  = qrcode.make(uri)
    buf = _io.BytesIO()
    qr.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    # Store the secret temporarily — it only becomes active after the user verifies
    conn = get_db()
    conn.execute("UPDATE users SET totp_secret=? WHERE id=?", (secret, current_user["id"]))
    conn.commit()
    conn.close()
    return {"secret": secret, "qr_code": f"data:image/png;base64,{qr_b64}"}


@app.post("/api/auth/2fa/verify")
def verify_2fa_setup(data: dict, current_user: dict = Depends(get_current_user)):
    """Confirm the user's authenticator is working, then enable 2FA."""
    import pyotp
    code = data.get("code", "").strip()
    conn = get_db()
    row  = conn.execute("SELECT totp_secret FROM users WHERE id=?", (current_user["id"],)).fetchone()
    if not row or not row["totp_secret"]:
        conn.close()
        raise HTTPException(status_code=400, detail="No 2FA setup in progress")
    totp = pyotp.TOTP(row["totp_secret"])
    if not totp.verify(code, valid_window=1):
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect code — check your authenticator app")
    conn.execute("UPDATE users SET totp_enabled=1 WHERE id=?", (current_user["id"],))
    conn.commit()
    conn.close()
    return {"message": "2FA enabled successfully"}


@app.post("/api/auth/2fa/disable")
def disable_2fa(data: dict, current_user: dict = Depends(get_current_user)):
    """User disables their own 2FA (requires password confirmation)."""
    password = data.get("password", "")
    conn = get_db()
    row  = conn.execute("SELECT password_hash FROM users WHERE id=?", (current_user["id"],)).fetchone()
    stored = row["password_hash"] if row else ""
    ok = (_legacy_hash(password) == stored) if _is_legacy_hash(stored) else _verify_password(password, stored)
    if not ok:
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect password")
    conn.execute("UPDATE users SET totp_secret=NULL, totp_enabled=0 WHERE id=?", (current_user["id"],))
    conn.commit()
    conn.close()
    return {"message": "2FA disabled"}


@app.post("/api/auth/2fa/challenge")
def verify_2fa_login(data: dict):
    """Second step of login when 2FA is enabled.
    The first login step returns needs_2fa=True and a temporary challenge token
    instead of a full session token. This endpoint exchanges the challenge + TOTP
    code for a real session token."""
    import pyotp
    challenge = data.get("challenge_token", "")
    code      = data.get("code", "").strip()
    if not challenge or not code:
        raise HTTPException(status_code=400, detail="challenge_token and code required")
    conn = get_db()
    row  = conn.execute(
        "SELECT u.*, s.expires_at FROM users u JOIN sessions s ON u.id=s.user_id "
        "WHERE s.token=? AND s.is_challenge=1",
        (challenge,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid or expired challenge")
    # Check the challenge token hasn't expired
    if row["expires_at"] and row["expires_at"] < datetime.utcnow().isoformat():
        conn.execute("DELETE FROM sessions WHERE token=?", (challenge,))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=401, detail="Challenge expired — please log in again")
    totp = pyotp.TOTP(row["totp_secret"])
    if not totp.verify(code, valid_window=1):
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect 2FA code")
    # Upgrade the challenge session to a real session with a full expiry
    session_exp = (datetime.utcnow() + timedelta(days=SESSION_LIFETIME_DAYS)).isoformat()
    conn.execute(
        "UPDATE sessions SET is_challenge=0, expires_at=? WHERE token=?",
        (session_exp, challenge)
    )
    conn.commit()
    conn.close()
    return {"token": challenge, "user": _user_dict(dict(row))}
