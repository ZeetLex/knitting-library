"""
Knitting Recipe Library — Backend API
"""

import io
import json
import logging
import logging.handlers
import os
import re
import shutil
import smtplib
import string
import uuid
import zipfile
import hashlib
import secrets
from email.mime.text import MIMEText
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
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
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

# ── Security headers ──────────────────────────────────────────────────────────────────────────────

# CSP for HTML pages: allow own assets + Google Fonts. Strict for API responses.
_CSP_HTML = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'self'; "
    "object-src 'none'; "
    "base-uri 'self'"
)
_CSP_API = "default-src 'none'; frame-ancestors 'none'"

def _apply_security_headers(response, is_html=False):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = _CSP_HTML if is_html else _CSP_API
    response.headers["Server"] = "webserver"
    return response

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    ct = response.headers.get("content-type", "")
    _apply_security_headers(response, is_html="text/html" in ct)
    return response
# ── CORS ──────────────────────────────────────────────────────────────────────
# Same-origin only by default. Set ALLOWED_ORIGINS env var if behind a reverse proxy.
_ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",")
_ALLOWED_ORIGINS = [o.strip() for o in _ALLOWED_ORIGINS if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,   # empty = same-origin only
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Session-Token"],
)

DATA_DIR   = Path("/data/recipes")
YARN_DIR   = Path("/data/yarns")
DB_PATH    = Path("/data/recipes.db")
STATIC_DIR = Path("/app/frontend/build")

DATA_DIR.mkdir(parents=True, exist_ok=True)
YARN_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# ── Auth log — fail2ban and admin audit ──────────────────────────────────────
# Writes AUTH_FAIL / AUTH_OK events to /logs/auth.log (mounted volume).
_auth_log = logging.getLogger("knitting.auth")
_auth_log.setLevel(logging.INFO)
_auth_log.propagate = False          # don't bubble up to the root logger
try:
    _auth_handler = logging.handlers.RotatingFileHandler(
        "/logs/auth.log",
        maxBytes=5 * 1024 * 1024,   # 5 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    _auth_handler.setFormatter(
        logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    _auth_log.addHandler(_auth_handler)
except OSError:
    # /logs not mounted (e.g. local dev without the volume) — log to stderr instead
    _auth_log.addHandler(logging.StreamHandler())

def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, accounting for X-Forwarded-For from reverse proxies."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )

def _auth_fail(request: Request, reason: str, username: str = "") -> None:
    """Write one AUTH_FAIL line to auth.log. Extracts the real client IP."""
    ip = _get_client_ip(request)
    user_part = f" user={username}" if username else ""
    _auth_log.warning(f"AUTH_FAIL ip={ip}{user_part} reason={reason}")

def _auth_ok(request: Request, username: str) -> None:
    """Write one AUTH_OK line to auth.log on successful login."""
    ip = _get_client_ip(request)
    _auth_log.info(f"AUTH_OK   ip={ip} user={username}")

# Maximum file upload sizes
MAX_PDF_BYTES   = 50  * 1024 * 1024   # 50 MB
MAX_IMAGE_BYTES = 20  * 1024 * 1024   # 20 MB

# ── File magic-byte validation ─────────────────────────────────────────────────

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
# 10 failed attempts per IP per 15 minutes. Resets on container restart.

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
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def _verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time bcrypt comparison."""
    try:
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    except Exception:
        return False


def _is_legacy_hash(stored: str) -> bool:
    """SHA-256 hex hash from before bcrypt migration (64 hex chars)."""
    return bool(re.fullmatch(r"[0-9a-f]{64}", stored))

def _legacy_hash(password: str) -> str:
    """Legacy SHA-256 hash — used only to verify and then migrate old accounts."""
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
    conn.execute("PRAGMA journal_mode=WAL")   # required for Windows Docker bind mounts
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    # Column migrations — run on every connection, skipped on fresh installs
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "recipes" in tables:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(recipes)").fetchall()]
        if "content_hash" not in cols:
            conn.execute("ALTER TABLE recipes ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''")
            conn.commit()
        if "thumbnail_version" not in cols:
            conn.execute("ALTER TABLE recipes ADD COLUMN thumbnail_version INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        if "image_order" not in cols:
            conn.execute("ALTER TABLE recipes ADD COLUMN image_order TEXT NOT NULL DEFAULT ''")
            conn.commit()
    if "users" in tables:
        user_cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "email" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
            conn.commit()
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS recipes (
            id                TEXT PRIMARY KEY,
            title             TEXT NOT NULL,
            description       TEXT NOT NULL DEFAULT '',
            file_type         TEXT NOT NULL,
            thumbnail_path    TEXT NOT NULL DEFAULT '',
            content_hash      TEXT NOT NULL DEFAULT '',
            thumbnail_version INTEGER NOT NULL DEFAULT 0,
            image_order       TEXT NOT NULL DEFAULT '',
            created_date      TEXT NOT NULL
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
            email         TEXT NOT NULL DEFAULT '',
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
        CREATE TABLE IF NOT EXISTS announcements (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            body        TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            created_by  TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS announcement_reads (
            user_id         TEXT NOT NULL,
            announcement_id TEXT NOT NULL,
            read_at         TEXT NOT NULL,
            PRIMARY KEY (user_id, announcement_id)
        );

        -- Indexes: speed up the most common queries as the library grows
        CREATE INDEX IF NOT EXISTS idx_recipes_created_date   ON recipes (created_date DESC);
        CREATE INDEX IF NOT EXISTS idx_recipes_title          ON recipes (title);
        CREATE INDEX IF NOT EXISTS idx_recipe_categories_rid  ON recipe_categories (recipe_id);
        CREATE INDEX IF NOT EXISTS idx_recipe_categories_cid  ON recipe_categories (category_id);
        CREATE INDEX IF NOT EXISTS idx_recipe_tags_rid        ON recipe_tags (recipe_id);
        CREATE INDEX IF NOT EXISTS idx_recipe_tags_tid        ON recipe_tags (tag_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id       ON sessions (user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_expires_at    ON sessions (expires_at);
        CREATE INDEX IF NOT EXISTS idx_project_sessions_rid   ON project_sessions (recipe_id);
        CREATE INDEX IF NOT EXISTS idx_project_feedback_rid   ON project_feedback (recipe_id);
        CREATE INDEX IF NOT EXISTS idx_project_feedback_sid   ON project_feedback (session_id);
        CREATE INDEX IF NOT EXISTS idx_yarns_name             ON yarns (name);
        CREATE INDEX IF NOT EXISTS idx_yarn_colours_yarn_id   ON yarn_colours (yarn_id);
        CREATE INDEX IF NOT EXISTS idx_inventory_items_type   ON inventory_items (type);
        CREATE INDEX IF NOT EXISTS idx_inventory_log_item_id  ON inventory_log (item_id);
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

    # Clean up stale import_queue entries: if a recipe was already confirmed
    # (exists in the recipes table) but its queue entry is still 'staged',
    # mark it done. This can happen if the container restarted mid-confirm.
    conn.execute("""
        UPDATE import_queue SET status='done'
        WHERE status='staged'
        AND recipe_id IN (SELECT id FROM recipes)
    """)

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
    try:
        _check_rate_limit(ip)
    except HTTPException:
        _auth_fail(request, reason="rate_limited")
        raise

    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

    if not user:
        # Record failure even for unknown usernames (prevents username enumeration via timing)
        _record_failed_attempt(ip)
        _auth_fail(request, reason="unknown_user", username=username)
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    stored = user["password_hash"]

    # Migration path: if this user still has the old SHA-256 hash, verify with
    # the legacy scheme and then silently upgrade to bcrypt.
    if _is_legacy_hash(stored):
        if _legacy_hash(password) != stored:
            _record_failed_attempt(ip)
            _auth_fail(request, reason="bad_password", username=username)
            conn.close()
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        # Upgrade hash in-place
        new_hash = _hash_password(password)
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user["id"]))
        conn.commit()
    else:
        if not _verify_password(password, stored):
            _record_failed_attempt(ip)
            _auth_fail(request, reason="bad_password", username=username)
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
    _auth_ok(request, username)
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


@app.post("/api/auth/forgot-password")
def forgot_password(data: dict, request: Request):
    """Generate a temporary password and email it. Always returns the same response
    to avoid leaking whether an account exists."""
    username_or_email = data.get("username_or_email", "").strip().lower()
    if not username_or_email:
        raise HTTPException(status_code=400, detail="Username or email required")
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, email FROM users "
        "WHERE lower(username)=? OR (email != '' AND lower(email)=?)",
        (username_or_email, username_or_email)
    ).fetchone()
    _GENERIC = {"message": "If an account with that username or email exists and has an address on file, a new password has been sent."}
    if not user or not user["email"]:
        conn.close()
        return _GENERIC
    # Build email before committing the DB change so a send failure leaves the password intact
    temp_pw  = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    base_url = str(request.base_url).rstrip("/")
    cfg_rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'mail_tmpl_%'").fetchall()
    cfg      = {r["key"]: r["value"] for r in cfg_rows}
    subject  = cfg.get("mail_tmpl_forgot_subject", _DEFAULT_FORGOT_SUBJECT)
    body     = cfg.get("mail_tmpl_forgot_body",    _DEFAULT_FORGOT_BODY)
    tokens   = {"USERNAME": user["username"], "PASSWORD": temp_pw, "APP_URL": base_url}
    try:
        _send_app_mail(user["email"], _render_template(subject, tokens), _render_template(body, tokens))
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"Could not send email: {e}")
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash_password(temp_pw), user["id"]))
    conn.commit()
    conn.close()
    return _GENERIC


# ── Admin: user management ────────────────────────────────────────────────────

@app.get("/api/admin/users")
def list_users(admin: dict = Depends(require_admin)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, email, is_admin, theme, language, created_date FROM users ORDER BY created_date"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/admin/users")
def create_user(data: dict, admin: dict = Depends(require_admin)):
    username = data.get("username", "").strip()
    password = data.get("password", "")
    email    = data.get("email", "").strip().lower()
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
        "INSERT INTO users (id, username, password_hash, is_admin, email, created_date) VALUES (?,?,?,?,?,?)",
        (uid, username, _hash_password(password), 1 if data.get("is_admin") else 0, email, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return {"id": uid, "username": username, "email": email, "is_admin": bool(data.get("is_admin"))}


@app.put("/api/admin/users/{user_id}/email")
def update_user_email(user_id: str, data: dict, admin: dict = Depends(require_admin)):
    email = data.get("email", "").strip().lower()
    conn = get_db()
    if not conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    conn.execute("UPDATE users SET email=? WHERE id=?", (email, user_id))
    conn.commit()
    conn.close()
    return {"message": "Email updated"}


@app.post("/api/admin/users/{user_id}/welcome-mail")
def send_welcome_mail(user_id: str, data: dict, request: Request, admin: dict = Depends(require_admin)):
    conn = get_db()
    user = conn.execute("SELECT username, email FROM users WHERE id=?", (user_id,)).fetchone()
    if not user or not user["email"]:
        conn.close()
        raise HTTPException(status_code=400, detail="User has no email address")
    cfg_rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'mail_tmpl_%'").fetchall()
    conn.close()
    cfg = {r["key"]: r["value"] for r in cfg_rows}
    base_url = str(request.base_url).rstrip("/")
    subject  = cfg.get("mail_tmpl_welcome_subject", _DEFAULT_WELCOME_SUBJECT)
    body     = cfg.get("mail_tmpl_welcome_body",    _DEFAULT_WELCOME_BODY)
    password = data.get("password", "(see administrator)")
    tokens   = {"USERNAME": user["username"], "PASSWORD": password, "APP_URL": base_url}
    try:
        _send_app_mail(user["email"], _render_template(subject, tokens), _render_template(body, tokens))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not send email: {e}")
    return {"message": "Welcome email sent"}


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
    """Delete categories that are no longer associated with any recipe."""
    conn.execute(
        "DELETE FROM categories WHERE id NOT IN (SELECT category_id FROM recipe_categories)"
    )


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

def _get_recipes_summary(conn, ids: list[str]) -> list[dict]:
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

    # 4. Project status — latest session per recipe, plus feedback averages
    for row in conn.execute(
        f"""SELECT recipe_id,
                   MAX(CASE WHEN finished_at IS NULL THEN id END) as active_id,
                   MAX(CASE WHEN finished_at IS NULL THEN started_at END) as active_started,
                   COUNT(id) as session_count
            FROM project_sessions
            WHERE recipe_id IN ({placeholders})
            GROUP BY recipe_id""",
        ids
    ).fetchall():
        rid = row["recipe_id"]
        if rid not in by_id:
            continue
        if row["active_id"]:
            by_id[rid]["project_status"]    = "active"
            by_id[rid]["active_session_id"] = row["active_id"]
            by_id[rid]["active_started_at"] = row["active_started"]
        elif row["session_count"] > 0:
            by_id[rid]["project_status"] = "finished"

    # 5. Feedback averages in one query
    for row in conn.execute(
        f"""SELECT recipe_id,
                   ROUND(AVG((rating_recipe + rating_difficulty + rating_result) / 3.0), 1) as avg_score,
                   COUNT(*) as feedback_count
            FROM project_feedback
            WHERE recipe_id IN ({placeholders})
            GROUP BY recipe_id""",
        ids
    ).fetchall():
        rid = row["recipe_id"]
        if rid in by_id:
            by_id[rid]["avg_score"]      = row["avg_score"]
            by_id[rid]["feedback_count"] = row["feedback_count"]

    # Return in the original order
    return [by_id[i] for i in ids if i in by_id]


_RECIPES_PER_PAGE = 60   # default page size for the recipe grid

@app.get("/api/recipes")
def list_recipes(
    search:   Optional[str] = None,
    category: Optional[str] = None,
    tags:     Optional[str] = None,
    status:   Optional[str] = None,
    page:     int = 1,
    per_page: int = _RECIPES_PER_PAGE,
    current_user: dict = Depends(get_current_user)
):
    # Clamp per_page to a safe range so one request can't load the whole DB
    per_page = max(1, min(per_page, 200))
    page     = max(1, page)

    conn = get_db()

    # Build the filtered ID list with a single query
    id_query = """
        SELECT DISTINCT r.id, r.created_date
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
            SELECT recipe_id FROM project_sessions WHERE finished_at IS NULL
        )"""
    elif status == "finished":
        id_query += """ AND r.id NOT IN (
            SELECT recipe_id FROM project_sessions WHERE finished_at IS NULL
        ) AND r.id IN (
            SELECT recipe_id FROM project_sessions
        )"""

    # Sort: active projects first, then by newest
    id_query += """
        ORDER BY
            CASE WHEN r.id IN (SELECT recipe_id FROM project_sessions WHERE finished_at IS NULL) THEN 0
                 WHEN r.id IN (SELECT recipe_id FROM project_sessions) THEN 1
                 ELSE 2 END,
            r.created_date DESC
    """

    all_ids = [row["id"] for row in conn.execute(id_query, params).fetchall()]
    total   = len(all_ids)

    # Paginate — slice the ID list, then bulk-fetch only those recipes
    offset   = (page - 1) * per_page
    page_ids = all_ids[offset : offset + per_page]

    result = _get_recipes_summary(conn, page_ids)
    conn.close()

    return {
        "recipes":  result,
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    max(1, (total + per_page - 1) // per_page),
    }


@app.get("/api/recipes/{recipe_id}")
def get_recipe(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn   = get_db()
    recipe = _get_recipe_full(recipe_id, conn)
    conn.close()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@app.post("/api/recipes/check-duplicate")
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


@app.post("/api/recipes")
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
    _prune_orphan_categories(conn)
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
    _prune_orphan_categories(conn)
    conn.commit()
    conn.close()
    recipe_dir = DATA_DIR / recipe_id
    if recipe_dir.exists():
        shutil.rmtree(recipe_dir)
    return {"message": "Recipe deleted"}


@app.get("/api/categories")
def list_categories(all: bool = False, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if all:
        # Return every category (used by management UI — includes unassigned ones)
        rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    else:
        # Only return categories assigned to at least one recipe (used by filter pills)
        rows = conn.execute(
            "SELECT DISTINCT c.name FROM categories c "
            "JOIN recipe_categories rc ON c.id = rc.category_id "
            "ORDER BY c.name"
        ).fetchall()
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


@app.post("/api/recipes/{recipe_id}/set-thumbnail")
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


@app.put("/api/recipes/{recipe_id}/image-order")
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


@app.delete("/api/recipes/{recipe_id}/images/{filename}")
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


@app.post("/api/recipes/{recipe_id}/rotate-image")
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


@app.post("/api/recipes/{recipe_id}/images/{filename}/crop")
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


@app.get("/api/recipes/{recipe_id}/download")
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


@app.get("/api/import/check-duplicate/{recipe_id}")
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


@app.post("/api/import/confirm/{recipe_id}")
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
    conn.commit()
    conn.close()
    return {"status": "confirmed", "recipe_id": new_id}


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
    source: 'all' | 'uvicorn' | 'supervisord' | 'auth'
    """
    lines = max(10, min(lines, 1000))

    log_files = {
        "uvicorn":     Path("/logs/uvicorn.log"),
        "supervisord": Path("/logs/supervisord.log"),
        "auth":        Path("/logs/auth.log"),
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

# ── Mail helpers ──────────────────────────────────────────────────────────────

_DEFAULT_FORGOT_SUBJECT = "Your new Knitting Library password"
_DEFAULT_FORGOT_BODY = (
    "Hi {USERNAME},\n\n"
    "We received a password reset request for your Knitting Library account. "
    "A temporary password has been generated for you.\n\n"
    "────────────────────────────\n"
    "  Temporary password: {PASSWORD}\n"
    "────────────────────────────\n\n"
    "To get back in:\n"
    "  1. Log in with your temporary password\n"
    "  2. Go to Settings → Account → Change Password\n"
    "  3. Set a new password you will remember\n\n"
    "If you did not request a password reset, you can safely ignore this email — "
    "your existing password has not been changed.\n\n"
    "Happy knitting,\n"
    "Knitting Library"
)

_DEFAULT_WELCOME_SUBJECT = "Welcome to your Knitting Library!"
_DEFAULT_WELCOME_BODY = (
    "Hi {USERNAME},\n\n"
    "Your Knitting Library account is ready. Here are your login details:\n\n"
    "────────────────────────────\n"
    "  Username: {USERNAME}\n"
    "  Password: {PASSWORD}\n"
    "  App URL:  {APP_URL}\n"
    "────────────────────────────\n\n"
    "Once you are logged in, we recommend changing your password right away. "
    "You can do this under Settings → Account → Change Password.\n\n"
    "Knitting Library lets you store and organise your patterns, track your projects, "
    "and keep an inventory of your yarn stash — all in one place.\n\n"
    "Happy knitting,\n"
    "Knitting Library"
)

def _render_template(text: str, tokens: dict) -> str:
    """Substitute {TOKEN} placeholders in a template string."""
    for key, value in tokens.items():
        text = text.replace("{" + key + "}", value)
    return text

def _send_app_mail(to: str, subject: str, body: str) -> None:
    """Send a plain-text email using the stored SMTP settings. Raises on failure."""
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'mail_%'").fetchall()
    conn.close()
    cfg = {r["key"]: r["value"] for r in rows}
    if cfg.get("mail_enabled", "false").lower() != "true":
        raise ValueError("Mail is not enabled")
    host      = cfg.get("mail_host", "")
    port      = int(cfg.get("mail_port", 587))
    username  = cfg.get("mail_username", "")
    password  = cfg.get("mail_password", "")
    from_addr = cfg.get("mail_from", username)
    use_tls   = cfg.get("mail_tls", "true").lower() == "true"
    if not host or not username or not password:
        raise ValueError("Mail server not configured")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to
    if use_tls:
        server = smtplib.SMTP(host, port, timeout=10)
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(host, port, timeout=10)
    server.login(username, password)
    server.sendmail(from_addr, [to], msg.as_string())
    server.quit()


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
    allowed = {
        "mail_host", "mail_port", "mail_username", "mail_password",
        "mail_from", "mail_tls", "mail_enabled", "mail_announcements_enabled",
        "mail_tmpl_forgot_subject", "mail_tmpl_forgot_body",
        "mail_tmpl_welcome_subject", "mail_tmpl_welcome_body",
    }
    conn = get_db()
    for key, value in data.items():
        if key not in allowed:
            continue
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
def test_mail(data: dict, admin: dict = Depends(require_admin)):
    """Send a plain test email using the stored SMTP settings."""
    to_addr = data.get("to", "").strip()
    if not to_addr:
        raise HTTPException(status_code=400, detail="Recipient email required")
    try:
        _send_app_mail(to_addr, "Knitting Library — Test Email",
                       "This is a test email from your Knitting Library. Mail is working correctly.")
        return {"message": "Test email sent successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Mail send failed: {e}")


@app.post("/api/admin/mail/templates/test")
def test_mail_template(data: dict, request: Request, admin: dict = Depends(require_admin)):
    """Send a test email with a template, substituting mock values for all tokens."""
    to_addr  = data.get("to", "").strip()
    subject  = data.get("subject", "Test template")
    body     = data.get("body", "")
    if not to_addr:
        raise HTTPException(status_code=400, detail="Test recipient required")
    base_url = str(request.base_url).rstrip("/")
    tokens   = {"USERNAME": "TestUser", "PASSWORD": "TempPass123!", "APP_URL": base_url}
    try:
        _send_app_mail(to_addr, _render_template(subject, tokens), _render_template(body, tokens))
        return {"message": "Test email sent successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Mail send failed: {e}")

# ── Statistics ───────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats(current_user: dict = Depends(get_current_user)):
    """Return high-level library statistics."""
    conn = get_db()
    recipes = conn.execute("SELECT COUNT(*) as count FROM recipes").fetchone()["count"]
    yarns  = conn.execute("SELECT COUNT(*) as count FROM yarns").fetchone()["count"]
    users  = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
    active = conn.execute("SELECT COUNT(*) as count FROM project_sessions WHERE finished_at IS NULL").fetchone()["count"]
    finished = conn.execute("SELECT COUNT(*) as count FROM project_sessions WHERE finished_at IS NOT NULL").fetchone()["count"]
    categories = conn.execute("SELECT COUNT(*) as count FROM categories").fetchone()["count"]
    tags = conn.execute("SELECT COUNT(*) as count FROM tags").fetchone()["count"]
    items = conn.execute("SELECT COUNT(*) as count FROM inventory_items").fetchone()["count"]
    conn.close()
    return {
        "recipes": recipes,
        "yarns": yarns,
        "users": users,
        "active_projects": active,
        "finished_projects": finished,
        "categories": categories,
        "tags": tags,
        "inventory_items": items,
        "total_sessions": active + finished,
    }


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
def verify_2fa_login(data: dict, request: Request):
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
        _auth_fail(request, reason="invalid_2fa_challenge")
        raise HTTPException(status_code=401, detail="Invalid or expired challenge")
    # Check the challenge token hasn't expired
    if row["expires_at"] and row["expires_at"] < datetime.utcnow().isoformat():
        conn.execute("DELETE FROM sessions WHERE token=?", (challenge,))
        conn.commit()
        conn.close()
        _auth_fail(request, reason="2fa_challenge_expired", username=row["username"])
        raise HTTPException(status_code=401, detail="Challenge expired — please log in again")
    totp = pyotp.TOTP(row["totp_secret"])
    if not totp.verify(code, valid_window=1):
        conn.close()
        _auth_fail(request, reason="bad_2fa_code", username=row["username"])
        raise HTTPException(status_code=401, detail="Incorrect 2FA code")
    # Upgrade the challenge session to a real session with a full expiry
    session_exp = (datetime.utcnow() + timedelta(days=SESSION_LIFETIME_DAYS)).isoformat()
    conn.execute(
        "UPDATE sessions SET is_challenge=0, expires_at=? WHERE token=?",
        (session_exp, challenge)
    )
    conn.commit()
    conn.close()
    _auth_ok(request, row["username"])
    return {"token": challenge, "user": _user_dict(dict(row))}

# ── Announcements ─────────────────────────────────────────────────────────────

@app.post("/api/admin/announcements")
def create_announcement(data: dict, background_tasks: BackgroundTasks, admin: dict = Depends(require_admin)):
    """Admin pushes a new update note / patch note to all users."""
    title = data.get("title", "").strip()
    body  = data.get("body",  "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    ann_id = str(uuid.uuid4())
    now    = datetime.utcnow().isoformat()
    conn   = get_db()
    conn.execute(
        "INSERT INTO announcements (id, title, body, created_at, created_by) VALUES (?,?,?,?,?)",
        (ann_id, title, body, now, admin["username"])
    )
    conn.commit()
    # Email users if announcement emails are enabled
    enabled_row = conn.execute(
        "SELECT value FROM app_settings WHERE key='mail_announcements_enabled'"
    ).fetchone()
    if enabled_row and enabled_row["value"] == "true":
        recipients = [r["email"] for r in conn.execute(
            "SELECT email FROM users WHERE email != ''"
        ).fetchall()]
        if recipients:
            mail_subject = f"Knitting Library — {title}"
            mail_body    = (body + "\n\n— Knitting Library") if body else f"{title}\n\n— Knitting Library"
            def _send_all(addresses, subj, msg):
                for addr in addresses:
                    try:
                        _send_app_mail(addr, subj, msg)
                    except Exception:
                        pass
            background_tasks.add_task(_send_all, recipients, mail_subject, mail_body)
    conn.close()
    return {"id": ann_id, "title": title, "body": body, "created_at": now, "created_by": admin["username"]}


@app.get("/api/admin/announcements")
def list_announcements(admin: dict = Depends(require_admin)):
    """List all announcements, newest first."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM announcements ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/announcements/pending")
def get_pending_announcements(current_user: dict = Depends(get_current_user)):
    """Return announcements this user has not yet dismissed, newest first."""
    conn = get_db()
    rows = conn.execute(
        """SELECT a.* FROM announcements a
           WHERE a.id NOT IN (
               SELECT announcement_id FROM announcement_reads WHERE user_id = ?
           )
           ORDER BY a.created_at DESC""",
        (current_user["id"],)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/announcements/{ann_id}/dismiss")
def dismiss_announcement(ann_id: str, current_user: dict = Depends(get_current_user)):
    """Mark a single announcement as read for the current user."""
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO announcement_reads (user_id, announcement_id, read_at) VALUES (?,?,?)",
        (current_user["id"], ann_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return {"ok": True}


# ── Static file serving (replaces nginx) ─────────────────────────────────────
# Mount the compiled React build so FastAPI serves the frontend directly.
# This eliminates nginx entirely — one process, no permission issues.
# The SPA catch-all must be registered LAST so /api/ routes take priority.

# ── SPA middleware: serves React frontend without blocking /api/ routes ───────
# Problem: StaticFiles mounted at "/" intercepts ALL requests including /api/.
# Solution: custom middleware that only serves static files for non-API paths.
# Any path starting with /api/ or /data/ is passed through to FastAPI's router.

_static_app = StaticFiles(directory=str(STATIC_DIR)) if STATIC_DIR.exists() else None

@app.middleware("http")
async def spa_static_middleware(request: Request, call_next):
    path = request.url.path

    # Always pass API and data requests to FastAPI's router
    if path.startswith("/api/") or path.startswith("/data/"):
        return await call_next(request)

    # Try to serve as a static file
    if _static_app is not None:
        static_path = path.lstrip("/") or "index.html"
        candidate = STATIC_DIR / static_path
        if candidate.is_file():
            resp = FileResponse(str(candidate))
            ct = resp.media_type or ""
            return _apply_security_headers(resp, is_html="text/html" in ct)

    # SPA fallback: return index.html for all other paths (React Router handles routing)
    index = STATIC_DIR / "index.html"
    if index.exists():
        resp = FileResponse(str(index), media_type="text/html")
        return _apply_security_headers(resp, is_html=True)

    return await call_next(request)
