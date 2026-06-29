"""
Knitting Recipe Library — Backend API
"""

import io
import asyncio
import json
import logging
import logging.handlers
import os
import re
import shutil
import smtplib
import string
import subprocess
import tempfile
import uuid
import zipfile
import hashlib
import secrets
import base64
from difflib import SequenceMatcher
from email.mime.text import MIMEText
import ipaddress
import socket
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin, urlparse

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
    allow_headers=["Content-Type", "X-Session-Token", "X-CSRF-Token"],
)

DATA_DIR   = Path("/data/recipes")
YARN_DIR   = Path("/data/yarns")
DB_PATH    = Path("/data/recipes.db")
STATIC_DIR = Path("/app/frontend/build")

DATA_DIR.mkdir(parents=True, exist_ok=True)
YARN_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
AI_SETTING_KEYS = {
    "ai_enabled",
    "ai_provider",
    "ai_base_url",
    "ai_model",
    "ai_api_key",
    "ai_timeout",
    "ai_max_pages",
    "ai_prompt_mode",
    "ai_custom_prompt",
    "ai_recognition_mode",
    "ocr_enabled",
    "ocr_engine",
    "ocr_languages",
    "ocr_cleanup_enabled",
    "ocr_diagram_enabled",
    "ocr_max_variants",
    "ocr_page_workers",
}

SESSION_COOKIE = "knitting_session"
CSRF_COOKIE = "knitting_csrf"
MAX_SCRAPE_BYTES = 5 * 1024 * 1024
_ai_queue_task: Optional[asyncio.Task] = None
_ai_queue_lock = asyncio.Lock()

def _parse_trusted_proxies() -> list[ipaddress._BaseNetwork]:
    networks = []
    raw = os.environ.get("TRUSTED_PROXIES", "")
    for item in [p.strip() for p in raw.split(",") if p.strip()]:
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            print(f"Ignoring invalid TRUSTED_PROXIES entry: {item}")
    return networks

_TRUSTED_PROXY_NETS = _parse_trusted_proxies()

def _ip_in_networks(ip_text: str, networks: list[ipaddress._BaseNetwork]) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return any(ip in net for net in networks)

def _is_trusted_proxy(request: Request) -> bool:
    if not _TRUSTED_PROXY_NETS or not request.client:
        return False
    return _ip_in_networks(request.client.host, _TRUSTED_PROXY_NETS)

def _get_forwarded_proto(request: Request) -> str:
    if not _is_trusted_proxy(request):
        return request.url.scheme
    proto = request.headers.get("X-Forwarded-Proto", "")
    return proto.split(",")[0].strip().lower() or request.url.scheme

def _is_secure_request(request: Request) -> bool:
    return _get_forwarded_proto(request) == "https"

def _get_client_ip(request: Request) -> str:
    """Extract client IP, trusting X-Forwarded-For only from configured proxies."""
    if _is_trusted_proxy(request):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def _redact_sensitive(text: str) -> str:
    return re.sub(r"(?i)(token|challenge_token)=([^&\s]+)", r"\1=[REDACTED]", text)

@app.middleware("http")
async def redact_request_url_for_logs(request: Request, call_next):
    """Prevent session tokens in legacy URLs from reaching access logs/admin logs."""
    scope = dict(request.scope)
    raw_path = scope.get("raw_path", b"")
    query = scope.get("query_string", b"")
    if query:
        qs = query.decode("latin-1", errors="ignore")
        redacted = _redact_sensitive(qs)
        if redacted != qs:
            scope["query_string"] = redacted.encode("latin-1", errors="ignore")
            scope["raw_path"] = raw_path.split(b"?")[0] + b"?" + scope["query_string"]
            request = Request(scope, request.receive)
    return await call_next(request)

def _blocked_outbound_ip(ip: ipaddress._BaseAddress) -> bool:
    metadata = ipaddress.ip_address("169.254.169.254")
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified or ip == metadata
    )

def _validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Valid http/https URL required")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="URL host could not be resolved")
    addresses = {info[4][0] for info in infos}
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise HTTPException(status_code=400, detail="URL not allowed")
        if _blocked_outbound_ip(ip):
            raise HTTPException(status_code=400, detail="URL not allowed")
    return url

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

def _set_auth_cookies(response: Response, token: str, request: Request) -> None:
    secure = _is_secure_request(request)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_LIFETIME_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=SESSION_LIFETIME_DAYS * 24 * 60 * 60,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )

def _clear_auth_cookies(response: Response, request: Request) -> None:
    secure = _is_secure_request(request)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite="lax")

def _request_session_token(request: Request) -> str:
    return request.headers.get("X-Session-Token", "") or request.cookies.get(SESSION_COOKIE, "")

def _uses_cookie_auth(request: Request) -> bool:
    return bool(request.cookies.get(SESSION_COOKIE)) and not request.headers.get("X-Session-Token")

@app.middleware("http")
async def csrf_cookie_guard(request: Request, call_next):
    csrf_exempt = {
        "/api/auth/login",
        "/api/auth/2fa/challenge",
        "/api/auth/forgot-password",
        "/api/setup/admin",
    }
    if (
        request.method.upper() in {"POST", "PUT", "DELETE"}
        and request.url.path not in csrf_exempt
        and _uses_cookie_auth(request)
    ):
        cookie_token = request.cookies.get(CSRF_COOKIE, "")
        header_token = request.headers.get("X-CSRF-Token", "")
        if not cookie_token or not secrets.compare_digest(cookie_token, header_token):
            return JSONResponse({"detail": "CSRF token missing or invalid"}, status_code=403)
    return await call_next(request)


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
        "background":   u["background"]   or "floral",
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
    if "ai_text_jobs" in tables:
        job_cols = [r["name"] for r in conn.execute("PRAGMA table_info(ai_text_jobs)").fetchall()]
        if "dismissed" not in job_cols:
            conn.execute("ALTER TABLE ai_text_jobs ADD COLUMN dismissed INTEGER NOT NULL DEFAULT 0")
            conn.commit()
    if "users" in tables:
        user_cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "email" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
            conn.commit()
        if "background" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN background TEXT NOT NULL DEFAULT 'floral'")
            conn.commit()
    if "annotations" in tables:
        annotation_cols = [r["name"] for r in conn.execute("PRAGMA table_info(annotations)").fetchall()]
        if "user_id" not in annotation_cols:
            fallback_user = conn.execute(
                "SELECT id FROM users ORDER BY is_admin DESC, created_date ASC LIMIT 1"
            ).fetchone() if "users" in tables else None
            fallback_user_id = fallback_user["id"] if fallback_user else ""
            conn.execute("ALTER TABLE annotations RENAME TO annotations_legacy_user_migration")
            conn.execute("""
                CREATE TABLE annotations (
                    recipe_id TEXT NOT NULL,
                    page_key  TEXT NOT NULL,
                    user_id   TEXT NOT NULL DEFAULT '',
                    data      TEXT NOT NULL DEFAULT '[]',
                    updated   TEXT NOT NULL,
                    PRIMARY KEY (recipe_id, page_key, user_id)
                )
            """)
            conn.execute(
                "INSERT INTO annotations (recipe_id,page_key,user_id,data,updated) "
                "SELECT recipe_id,page_key,?,data,updated FROM annotations_legacy_user_migration",
                (fallback_user_id,)
            )
            conn.execute("DROP TABLE annotations_legacy_user_migration")
            conn.commit()
    if "recipe_text_versions" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recipe_text_versions (
                recipe_id          TEXT PRIMARY KEY,
                content_markdown   TEXT NOT NULL DEFAULT '',
                status             TEXT NOT NULL DEFAULT 'ready',
                language           TEXT NOT NULL DEFAULT '',
                prompt             TEXT NOT NULL DEFAULT '',
                provider           TEXT NOT NULL DEFAULT '',
                model              TEXT NOT NULL DEFAULT '',
                source_fingerprint TEXT NOT NULL DEFAULT '',
                generated_by       TEXT NOT NULL DEFAULT '',
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            )
        """)
        conn.commit()
    if "recipe_text_generation_audits" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recipe_text_generation_audits (
                recipe_id                 TEXT PRIMARY KEY,
                job_id                    TEXT NOT NULL DEFAULT '',
                workflow                  TEXT NOT NULL DEFAULT '',
                engine                    TEXT NOT NULL DEFAULT '',
                provider                  TEXT NOT NULL DEFAULT '',
                model                     TEXT NOT NULL DEFAULT '',
                steps_json                TEXT NOT NULL DEFAULT '[]',
                warnings_json             TEXT NOT NULL DEFAULT '[]',
                pages_processed           INTEGER NOT NULL DEFAULT 0,
                ocr_chars                 INTEGER NOT NULL DEFAULT 0,
                ocr_words                 INTEGER NOT NULL DEFAULT 0,
                output_chars              INTEGER NOT NULL DEFAULT 0,
                output_words              INTEGER NOT NULL DEFAULT 0,
                provider_prompt_tokens    INTEGER,
                provider_completion_tokens INTEGER,
                provider_total_tokens     INTEGER,
                estimated_input_tokens    INTEGER,
                estimated_image_tokens    INTEGER,
                duration_seconds          REAL,
                token_report_note         TEXT NOT NULL DEFAULT '',
                created_at                TEXT NOT NULL
            )
        """)
        conn.commit()
    if "ai_text_jobs" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_text_jobs (
                id                    TEXT PRIMARY KEY,
                recipe_id             TEXT NOT NULL,
                recipe_title          TEXT NOT NULL DEFAULT '',
                status                TEXT NOT NULL DEFAULT 'queued',
                progress_stage        TEXT NOT NULL DEFAULT 'queued',
                error                 TEXT NOT NULL DEFAULT '',
                language              TEXT NOT NULL DEFAULT '',
                provider              TEXT NOT NULL DEFAULT '',
                model                 TEXT NOT NULL DEFAULT '',
                generated_by          TEXT NOT NULL DEFAULT '',
                pages_sent            INTEGER NOT NULL DEFAULT 0,
                result_text_chars     INTEGER NOT NULL DEFAULT 0,
                duration_seconds      REAL,
                created_at            TEXT NOT NULL,
                started_at            TEXT NOT NULL DEFAULT '',
                finished_at           TEXT NOT NULL DEFAULT '',
                dismissed             INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_usage_events (
                id                 TEXT PRIMARY KEY,
                job_id             TEXT NOT NULL,
                recipe_id          TEXT NOT NULL,
                provider           TEXT NOT NULL DEFAULT '',
                model              TEXT NOT NULL DEFAULT '',
                prompt_tokens      INTEGER,
                completion_tokens  INTEGER,
                total_tokens       INTEGER,
                generated_chars    INTEGER NOT NULL DEFAULT 0,
                generated_words    INTEGER NOT NULL DEFAULT 0,
                pages_sent         INTEGER NOT NULL DEFAULT 0,
                duration_seconds   REAL,
                success            INTEGER NOT NULL DEFAULT 0,
                created_at         TEXT NOT NULL
            )
        """)
        conn.commit()
    if "recipe_charts" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recipe_charts (
                id                 TEXT PRIMARY KEY,
                recipe_id          TEXT NOT NULL,
                page_key           TEXT NOT NULL DEFAULT '',
                title              TEXT NOT NULL DEFAULT '',
                source_bbox_json   TEXT NOT NULL DEFAULT '[]',
                rows               INTEGER NOT NULL DEFAULT 0,
                columns            INTEGER NOT NULL DEFAULT 0,
                palette_json       TEXT NOT NULL DEFAULT '[]',
                cells_json         TEXT NOT NULL DEFAULT '[]',
                chart_code         TEXT NOT NULL DEFAULT '',
                repeat_count       INTEGER,
                confidence         REAL NOT NULL DEFAULT 0,
                generated_by       TEXT NOT NULL DEFAULT 'detector',
                source_fingerprint TEXT NOT NULL DEFAULT '',
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recipe_charts_recipe ON recipe_charts (recipe_id, page_key)")
        conn.commit()
    if "recipe_review_sessions" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS recipe_review_sessions (
                id                 TEXT PRIMARY KEY,
                recipe_id          TEXT NOT NULL,
                job_id             TEXT NOT NULL DEFAULT '',
                status             TEXT NOT NULL DEFAULT 'ready_to_review',
                language           TEXT NOT NULL DEFAULT '',
                source_fingerprint TEXT NOT NULL DEFAULT '',
                current_page_order INTEGER NOT NULL DEFAULT 1,
                created_by         TEXT NOT NULL DEFAULT '',
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL,
                completed_at       TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (recipe_id) REFERENCES recipes(id)
            );
            CREATE TABLE IF NOT EXISTS recipe_review_pages (
                id            TEXT PRIMARY KEY,
                session_id    TEXT NOT NULL,
                recipe_id     TEXT NOT NULL,
                page_key      TEXT NOT NULL,
                page_order    INTEGER NOT NULL,
                status        TEXT NOT NULL DEFAULT 'draft',
                ocr_text      TEXT NOT NULL DEFAULT '',
                reviewed_text TEXT NOT NULL DEFAULT '',
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES recipe_review_sessions(id)
            );
            CREATE TABLE IF NOT EXISTS recipe_review_diagrams (
                id            TEXT PRIMARY KEY,
                session_id    TEXT NOT NULL,
                page_id       TEXT NOT NULL,
                recipe_id     TEXT NOT NULL,
                page_key      TEXT NOT NULL,
                title         TEXT NOT NULL DEFAULT '',
                image_path    TEXT NOT NULL DEFAULT '',
                crop_json     TEXT NOT NULL DEFAULT '{}',
                grid_columns  INTEGER NOT NULL DEFAULT 0,
                grid_rows     INTEGER NOT NULL DEFAULT 0,
                rotation      REAL NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES recipe_review_sessions(id)
            );
            CREATE TABLE IF NOT EXISTS recipe_review_legends (
                id            TEXT PRIMARY KEY,
                session_id    TEXT NOT NULL,
                page_id       TEXT NOT NULL,
                recipe_id     TEXT NOT NULL,
                page_key      TEXT NOT NULL,
                title         TEXT NOT NULL DEFAULT '',
                image_path    TEXT NOT NULL DEFAULT '',
                crop_json     TEXT NOT NULL DEFAULT '{}',
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES recipe_review_sessions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_review_sessions_recipe ON recipe_review_sessions (recipe_id, status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_review_pages_session ON recipe_review_pages (session_id, page_order);
            CREATE INDEX IF NOT EXISTS idx_review_diagrams_session ON recipe_review_diagrams (session_id, page_id);
            CREATE INDEX IF NOT EXISTS idx_review_legends_session ON recipe_review_legends (session_id, page_id);
        """)
        conn.commit()
    if "ai_stats_resets" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_stats_resets (
                scope    TEXT PRIMARY KEY,
                reset_at TEXT NOT NULL,
                reset_by TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.commit()
    return conn


def _cleanup_stale_import_queue(conn) -> None:
    """Hide staged import rows whose draft recipe no longer exists."""
    conn.execute("""
        UPDATE import_queue SET status='discarded'
        WHERE status='staged'
        AND recipe_id NOT IN (SELECT id FROM recipes)
    """)


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
            background    TEXT NOT NULL DEFAULT 'floral',
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
            user_id   TEXT NOT NULL DEFAULT '',
            data      TEXT NOT NULL DEFAULT '[]',
            updated   TEXT NOT NULL,
            PRIMARY KEY (recipe_id, page_key, user_id)
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
        CREATE TABLE IF NOT EXISTS recipe_text_versions (
            recipe_id          TEXT PRIMARY KEY,
            content_markdown   TEXT NOT NULL DEFAULT '',
            status             TEXT NOT NULL DEFAULT 'ready',
            language           TEXT NOT NULL DEFAULT '',
            prompt             TEXT NOT NULL DEFAULT '',
            provider           TEXT NOT NULL DEFAULT '',
            model              TEXT NOT NULL DEFAULT '',
            source_fingerprint TEXT NOT NULL DEFAULT '',
            generated_by       TEXT NOT NULL DEFAULT '',
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recipe_text_generation_audits (
            recipe_id                 TEXT PRIMARY KEY,
            job_id                    TEXT NOT NULL DEFAULT '',
            workflow                  TEXT NOT NULL DEFAULT '',
            engine                    TEXT NOT NULL DEFAULT '',
            provider                  TEXT NOT NULL DEFAULT '',
            model                     TEXT NOT NULL DEFAULT '',
            steps_json                TEXT NOT NULL DEFAULT '[]',
            warnings_json             TEXT NOT NULL DEFAULT '[]',
            pages_processed           INTEGER NOT NULL DEFAULT 0,
            ocr_chars                 INTEGER NOT NULL DEFAULT 0,
            ocr_words                 INTEGER NOT NULL DEFAULT 0,
            output_chars              INTEGER NOT NULL DEFAULT 0,
            output_words              INTEGER NOT NULL DEFAULT 0,
            provider_prompt_tokens    INTEGER,
            provider_completion_tokens INTEGER,
            provider_total_tokens     INTEGER,
            estimated_input_tokens    INTEGER,
            estimated_image_tokens    INTEGER,
            duration_seconds          REAL,
            token_report_note         TEXT NOT NULL DEFAULT '',
            created_at                TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recipe_charts (
            id                 TEXT PRIMARY KEY,
            recipe_id          TEXT NOT NULL,
            page_key           TEXT NOT NULL DEFAULT '',
            title              TEXT NOT NULL DEFAULT '',
            source_bbox_json   TEXT NOT NULL DEFAULT '[]',
            rows               INTEGER NOT NULL DEFAULT 0,
            columns            INTEGER NOT NULL DEFAULT 0,
            palette_json       TEXT NOT NULL DEFAULT '[]',
            cells_json         TEXT NOT NULL DEFAULT '[]',
            chart_code         TEXT NOT NULL DEFAULT '',
            repeat_count       INTEGER,
            confidence         REAL NOT NULL DEFAULT 0,
            generated_by       TEXT NOT NULL DEFAULT 'detector',
            source_fingerprint TEXT NOT NULL DEFAULT '',
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL,
            FOREIGN KEY (recipe_id) REFERENCES recipes(id)
        );
        CREATE TABLE IF NOT EXISTS recipe_review_sessions (
            id                 TEXT PRIMARY KEY,
            recipe_id          TEXT NOT NULL,
            job_id             TEXT NOT NULL DEFAULT '',
            status             TEXT NOT NULL DEFAULT 'ready_to_review',
            language           TEXT NOT NULL DEFAULT '',
            source_fingerprint TEXT NOT NULL DEFAULT '',
            current_page_order INTEGER NOT NULL DEFAULT 1,
            created_by         TEXT NOT NULL DEFAULT '',
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL,
            completed_at       TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (recipe_id) REFERENCES recipes(id)
        );
        CREATE TABLE IF NOT EXISTS recipe_review_pages (
            id            TEXT PRIMARY KEY,
            session_id    TEXT NOT NULL,
            recipe_id     TEXT NOT NULL,
            page_key      TEXT NOT NULL,
            page_order    INTEGER NOT NULL,
            status        TEXT NOT NULL DEFAULT 'draft',
            ocr_text      TEXT NOT NULL DEFAULT '',
            reviewed_text TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES recipe_review_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS recipe_review_diagrams (
            id            TEXT PRIMARY KEY,
            session_id    TEXT NOT NULL,
            page_id       TEXT NOT NULL,
            recipe_id     TEXT NOT NULL,
            page_key      TEXT NOT NULL,
            title         TEXT NOT NULL DEFAULT '',
            image_path    TEXT NOT NULL DEFAULT '',
            crop_json     TEXT NOT NULL DEFAULT '{}',
            grid_columns  INTEGER NOT NULL DEFAULT 0,
            grid_rows     INTEGER NOT NULL DEFAULT 0,
            rotation      REAL NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES recipe_review_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS recipe_review_legends (
            id            TEXT PRIMARY KEY,
            session_id    TEXT NOT NULL,
            page_id       TEXT NOT NULL,
            recipe_id     TEXT NOT NULL,
            page_key      TEXT NOT NULL,
            title         TEXT NOT NULL DEFAULT '',
            image_path    TEXT NOT NULL DEFAULT '',
            crop_json     TEXT NOT NULL DEFAULT '{}',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES recipe_review_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS ai_text_jobs (
            id                    TEXT PRIMARY KEY,
            recipe_id             TEXT NOT NULL,
            recipe_title          TEXT NOT NULL DEFAULT '',
            status                TEXT NOT NULL DEFAULT 'queued',
            progress_stage        TEXT NOT NULL DEFAULT 'queued',
            error                 TEXT NOT NULL DEFAULT '',
            language              TEXT NOT NULL DEFAULT '',
            provider              TEXT NOT NULL DEFAULT '',
            model                 TEXT NOT NULL DEFAULT '',
            generated_by          TEXT NOT NULL DEFAULT '',
            pages_sent            INTEGER NOT NULL DEFAULT 0,
            result_text_chars     INTEGER NOT NULL DEFAULT 0,
            duration_seconds      REAL,
            created_at            TEXT NOT NULL,
            started_at            TEXT NOT NULL DEFAULT '',
            finished_at           TEXT NOT NULL DEFAULT '',
            dismissed             INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ai_usage_events (
            id                 TEXT PRIMARY KEY,
            job_id             TEXT NOT NULL,
            recipe_id          TEXT NOT NULL,
            provider           TEXT NOT NULL DEFAULT '',
            model              TEXT NOT NULL DEFAULT '',
            prompt_tokens      INTEGER,
            completion_tokens  INTEGER,
            total_tokens       INTEGER,
            generated_chars    INTEGER NOT NULL DEFAULT 0,
            generated_words    INTEGER NOT NULL DEFAULT 0,
            pages_sent         INTEGER NOT NULL DEFAULT 0,
            duration_seconds   REAL,
            success            INTEGER NOT NULL DEFAULT 0,
            created_at         TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_stats_resets (
            scope    TEXT PRIMARY KEY,
            reset_at TEXT NOT NULL,
            reset_by TEXT NOT NULL DEFAULT ''
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
        CREATE INDEX IF NOT EXISTS idx_ai_text_jobs_status    ON ai_text_jobs (status, dismissed, created_at);
        CREATE INDEX IF NOT EXISTS idx_ai_usage_events_job    ON ai_usage_events (job_id);
        CREATE INDEX IF NOT EXISTS idx_ai_usage_events_created ON ai_usage_events (created_at);
        CREATE INDEX IF NOT EXISTS idx_recipe_text_generation_audits_created ON recipe_text_generation_audits (created_at);
        CREATE INDEX IF NOT EXISTS idx_recipe_charts_recipe ON recipe_charts (recipe_id, page_key);
        CREATE INDEX IF NOT EXISTS idx_review_sessions_recipe ON recipe_review_sessions (recipe_id, status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_review_pages_session ON recipe_review_pages (session_id, page_order);
        CREATE INDEX IF NOT EXISTS idx_review_diagrams_session ON recipe_review_diagrams (session_id, page_id);
        CREATE INDEX IF NOT EXISTS idx_review_legends_session ON recipe_review_legends (session_id, page_id);
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

    # Clean up orphaned import_queue entries left by older interrupted imports.
    # Valid staged drafts intentionally still have rows in recipes; keep those
    # resumable so "Stop for now" survives restarts.
    _cleanup_stale_import_queue(conn)
    # Background AI work is in-process. If the container stopped mid-generation,
    # put those jobs back in line so they do not remain stuck as running.
    conn.execute("""
        UPDATE ai_text_jobs
        SET status='queued', progress_stage='queued', started_at='', error=''
        WHERE status='running'
    """)

    conn.commit()
    conn.close()


init_db()

# ── Auth middleware ───────────────────────────────────────────────────────────

@app.get("/api/setup/status")
def setup_status():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return {"setup_required": count == 0}


@app.post("/api/setup/admin")
def setup_admin(data: dict, request: Request):
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if len(password) < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters")
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] != 0:
        conn.close()
        raise HTTPException(status_code=409, detail="Setup has already been completed")
    uid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    token = secrets.token_hex(32)
    session_exp = (datetime.utcnow() + timedelta(days=SESSION_LIFETIME_DAYS)).isoformat()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, is_admin, created_date) VALUES (?,?,?,1,?)",
        (uid, username, _hash_password(password), now)
    )
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_date, expires_at, is_challenge) VALUES (?,?,?,?,0)",
        (token, uid, now, session_exp)
    )
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    response = JSONResponse({"token": token, "user": _user_dict(dict(user))})
    _set_auth_cookies(response, token, request)
    _auth_ok(request, username)
    return response

def get_current_user(request: Request) -> dict:
    token = _request_session_token(request)
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
    t = token or _request_session_token(request)
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
    ip = _get_client_ip(request)
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
    response = JSONResponse({"token": token, "user": _user_dict(dict(user))})
    _set_auth_cookies(response, token, request)
    return response


@app.post("/api/auth/logout")
def logout(request: Request):
    token = _request_session_token(request)
    if token:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
        conn.close()
    response = JSONResponse({"message": "Logged out"})
    _clear_auth_cookies(response, request)
    return response


@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return _user_dict(current_user)


@app.put("/api/auth/settings")
def update_settings(data: dict, current_user: dict = Depends(get_current_user)):
    theme        = data.get("theme",        current_user.get("theme", "light"))
    language     = data.get("language",     current_user.get("language", "en"))
    currency     = data.get("currency",     current_user.get("currency", "NOK"))
    colour_theme = data.get("colour_theme", current_user.get("colour_theme", "terracotta"))
    background   = data.get("background",   current_user.get("background", "floral"))
    if theme not in ("light", "dark"):
        raise HTTPException(status_code=400, detail="Invalid theme")
    if not isinstance(language, str) or not LANGUAGE_CODE_RE.fullmatch(language):
        raise HTTPException(status_code=400, detail="Invalid language")
    if currency not in ("NOK", "USD", "GBP", "HUF", "EUR"):
        raise HTTPException(status_code=400, detail="Invalid currency")
    if colour_theme not in ("terracotta", "rose", "lavender", "sage", "berry", "ocean", "willow"):
        raise HTTPException(status_code=400, detail="Invalid colour theme")
    if background not in ("floral", "default", "plain-white", "cotton", "soft-paper", "warm-linen"):
        raise HTTPException(status_code=400, detail="Invalid background")
    conn = get_db()
    conn.execute(
        "UPDATE users SET theme=?, language=?, currency=?, colour_theme=?, background=? WHERE id=?",
        (theme, language, currency, colour_theme, background, current_user["id"])
    )
    conn.commit()
    conn.close()
    return {"theme": theme, "language": language, "currency": currency, "colour_theme": colour_theme, "background": background}


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


def _ai_settings(conn, reveal_secret: bool = False) -> dict:
    rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'ai_%' OR key LIKE 'ocr_%'").fetchall()
    cfg = {r["key"]: r["value"] for r in rows}
    defaults = {
        "ai_enabled": "false",
        "ai_provider": "openai_compatible",
        "ai_base_url": "http://host.docker.internal:11434/v1",
        "ai_model": "",
        "ai_api_key": "",
        "ai_timeout": "600",
        "ai_max_pages": "8",
        "ai_prompt_mode": "default",
        "ai_custom_prompt": "",
        "ai_recognition_mode": "ocr_first",
        "ocr_enabled": "true",
        "ocr_engine": "tesseract",
        "ocr_languages": "",
        "ocr_cleanup_enabled": "true",
        "ocr_diagram_enabled": "true",
        "ocr_max_variants": os.environ.get("OCR_MAX_VARIANTS", "4"),
        "ocr_page_workers": os.environ.get("OCR_PAGE_WORKERS", "2"),
    }
    defaults.update(cfg)
    if defaults.get("ai_api_key") and not reveal_secret:
        defaults["ai_api_key"] = "••••••••"
    return defaults


def _default_ocr_prompt(language: str = "en") -> str:
    prompts = {
        "no": (
            "Svar kun med den ferdige transkripsjonen i Markdown. Ikke inkluder analyse, tankegang, forklaring, kommentarer eller interne kanaler. "
            "Du transkriberer strikkeoppskrifter fra bilder. Behold originalspråket i oppskriften. "
            "Skriv resultatet som ryddig Markdown med overskrifter og punktlister der det passer. "
            "Bevar størrelser, masketall, parenteser, forkortelser, pinne-/garninformasjon og omgang-/radtekst nøyaktig. "
            "Ikke finn på manglende tekst. Marker usikker tekst som [uklart]. "
            "Hopp over rene foto-/forsider uten nyttig oppskriftstekst."
        ),
        "hu": (
            "Csak a kész Markdown átírást add vissza. Ne írj elemzést, gondolatmenetet, magyarázatot, kommentárt vagy belső csatornákat. "
            "Kötésmintákat írsz át képekről. Őrizd meg a minta eredeti nyelvét. "
            "Az eredményt tiszta Markdown formában add vissza címsorokkal és listákkal, ahol hasznos. "
            "Pontosan őrizd meg a méreteket, szemszámokat, zárójeleket, rövidítéseket, tű-/fonaladatokat és sor/kör utasításokat. "
            "Ne találj ki hiányzó szöveget. A bizonytalan részeket jelöld így: [unclear]. "
            "Hagyd ki a pusztán dekoratív fotókat vagy borítóoldalakat, ha nincs rajtuk hasznos mintaszöveg."
        ),
    }
    return prompts.get(language, (
        "Return only the final Markdown transcription. Do not include analysis, chain of thought, commentary, explanations, or internal channel markers. "
        "You transcribe knitting patterns from recipe images. Preserve the original recipe language. "
        "Return clean Markdown with headings and lists where helpful. Preserve sizes, stitch counts, parentheses, abbreviations, needle/yarn information, and row/round wording exactly. "
        "Do not invent missing text. Mark uncertain words as [unclear]. Skip purely decorative cover/photo-only pages unless they contain useful pattern text."
    ))


def _clean_ai_transcription(content: str) -> str:
    content = (content or "").strip()
    content = re.sub(r"(?is)<\|channel\>.*?(?=<\|channel\>|$)", "", content).strip()
    content = re.sub(r"(?is)<think>.*?</think>", "", content).strip()
    content = re.sub(r"(?is)^```(?:markdown|md|text)?\s*", "", content).strip()
    content = re.sub(r"(?is)\s*```$", "", content).strip()
    content = re.sub(r"(?is)^(?:final answer|transcription|markdown)\s*:\s*", "", content).strip()
    return content


def _collect_recipe_image_paths(recipe_id: str, conn, max_pages: int) -> list[Path]:
    recipe = _get_recipe_full(recipe_id, conn)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    recipe_dir = DATA_DIR / recipe_id
    if recipe["file_type"] == "pdf":
        pages = sorted(recipe_dir.glob("page-*.jpg"))
        if not pages and (recipe_dir / "recipe.pdf").exists():
            _convert_pdf_to_pages(recipe_dir)
            pages = sorted(recipe_dir.glob("page-*.jpg"))
        paths = pages
    else:
        paths = [recipe_dir / name for name in recipe["images"]]
    paths = [p for p in paths if p.exists() and p.suffix.lower() in IMAGE_EXTS][:max(1, max_pages)]
    if not paths:
        raise HTTPException(status_code=400, detail="No recipe images available for text generation")
    return paths


def _collect_recipe_image_payloads(recipe_id: str, conn, max_pages: int) -> list[dict]:
    paths = _collect_recipe_image_paths(recipe_id, conn, max_pages)
    payloads = []
    for path in paths:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        mime = "image/png" if path.suffix.lower() == ".png" else "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
        payloads.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{data}"},
        })
    return payloads


def _normalise_recognition_mode(value: str) -> str:
    value = (value or "ocr_first").strip().lower()
    return value if value in {"ocr_first", "ocr_only", "ai_vision_only"} else "ocr_first"


def _ocr_languages_for(language: str, cfg: dict) -> str:
    configured = (cfg.get("ocr_languages") or "").strip()
    if configured:
        return re.sub(r"[^A-Za-z0-9_+.-]", "", configured) or "eng"
    return "nor+eng" if (language or "").lower().startswith("no") else "eng+nor"


def _ocr_engine_for(cfg: dict) -> str:
    engine = (cfg.get("ocr_engine") or "tesseract").strip().lower()
    return engine if engine in {"tesseract", "paddleocr"} else "tesseract"


def _is_truthy(value: str, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _ocr_preprocess_image(path: Path):
    from PIL import Image, ImageOps, ImageFilter

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("L")
    img = ImageOps.autocontrast(img)
    if img.width < 1400:
        scale = min(3, max(2, int(1600 / max(1, img.width))))
        img = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)
    img = img.filter(ImageFilter.SHARPEN)
    threshold = 185
    img = img.point(lambda p: 255 if p > threshold else 0, mode="1").convert("L")
    return ImageOps.expand(img, border=24, fill=255)


def _ocr_preprocess_grayscale(path: Path):
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("L")
    img = ImageOps.autocontrast(img)
    img = ImageEnhance.Contrast(img).enhance(1.35)
    if img.width < 1400:
        scale = min(3, max(2, int(1600 / max(1, img.width))))
        img = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)
    img = img.filter(ImageFilter.SHARPEN)
    return ImageOps.expand(img, border=24, fill=255)


def _run_tesseract_image(img, languages: str, psm: int = 6, timeout: int = 120, config: Optional[list[str]] = None) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        img.save(tmp_path)
        cmd = ["tesseract", tmp_path, "stdout", "-l", languages, "--oem", "1", "--psm", str(psm)]
        if config:
            cmd.extend(config)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        if res.returncode != 0:
            detail = (res.stderr or res.stdout or "tesseract failed").strip()
            raise RuntimeError(detail[:500])
        return res.stdout or ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _run_tesseract_tsv_image(img, languages: str, psm: int = 6, timeout: int = 120, config: Optional[list[str]] = None) -> list[dict]:
    text = _run_tesseract_image(img, languages, psm=psm, timeout=timeout, config=[*(config or []), "tsv"])
    fields = ["level", "page_num", "block_num", "par_num", "line_num", "word_num", "left", "top", "width", "height", "conf", "text"]
    rows = []
    for raw in (text or "").splitlines()[1:]:
        parts = raw.split("\t", 11)
        if len(parts) != len(fields):
            continue
        rows.append(dict(zip(fields, parts)))
    return rows


_OCR_KNITTING_TERMS = {
    "arbeid", "arbeidet", "begynn", "diagram", "fell", "felling", "garn", "garnforbruk",
    "garnforslag", "gjenta", "glattstrikk", "icord", "kant", "kantmaske", "kast", "legg",
    "maske", "masker", "mkrets", "mnd", "nakken", "nyfødt", "omg", "omgang",
    "omkrets", "oppleggskanten", "pinne", "pinnen", "plukk",
    "prematur", "rett", "rettsiden", "rundt", "sammen", "sett", "size", "sizes",
    "skein", "stitch", "stitches", "strikk", "strikkefasthet", "struktur", "størrelser",
    "teknikker", "tråd", "veiledende", "vrang", "vrangsiden", "yarn",
}


_OCR_KNITTING_STEMS = (
    "arbeid", "blokk", "bryt", "diagram", "fell", "fest", "forkort", "garn", "gjenta",
    "glattstrikk", "icord", "kant", "legg", "mask", "mål", "mnd", "nakke", "nyfødt",
    "omg", "omkrets", "opplegg", "pinn", "plukk", "prematur", "rett", "sammen",
    "sett", "size", "skein", "snurp", "stitch", "strikk", "struktur", "størrelse",
    "teknikk", "tråd", "vask", "veiled", "vrang", "yarn",
)


def _ocr_line_has_recipe_signal(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return False
    lower = text.lower()
    words = re.findall(r"[A-Za-zÆØÅæøå]{1,}", lower)
    if any(word in _OCR_KNITTING_TERMS for word in words):
        return True
    if any(any(word.startswith(stem) for stem in _OCR_KNITTING_STEMS) for word in words):
        return True
    if re.search(r"\d+\s*(?:cm|g|mnd|mm)\b", lower):
        return True
    if re.search(r"\b(?:r|vr|km|ssk|smn)\b", lower) and re.search(r"\d", lower):
        return True
    if re.search(r"\d+\s*(?:\([^)]+\)\s*){2,}\d+", lower):
        return True
    return False


def _ocr_line_quality(line: str) -> float:
    text = (line or "").strip()
    if not text:
        return 0.0
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return 0.0
    alpha = sum(1 for ch in chars if ch.isalpha())
    digits = sum(1 for ch in chars if ch.isdigit())
    symbols = sum(1 for ch in chars if not ch.isalnum() and ch not in ".,;:()/-+%")
    words = re.findall(r"[A-Za-zÆØÅæøå]{2,}", text)
    lower_words = {w.lower() for w in words}
    term_hits = len(lower_words & _OCR_KNITTING_TERMS)
    number_patterns = len(re.findall(r"\d+\s*(?:\([^)]+\)\s*)*\d*|\d+\s*(?:cm|g|mnd|mm)", text, re.I))
    useful_punctuation = len(re.findall(r"[*(),.:/-]", text))
    symbol_ratio = symbols / max(1, len(chars))
    alpha_ratio = alpha / max(1, len(chars))
    long_letter_runs = len(re.findall(r"[A-ZÆØÅ]{5,}", text))

    short_words = sum(1 for word in words if len(word) <= 2)
    short_word_ratio = short_words / max(1, len(words))
    score = alpha * 0.14 + digits * 0.35 + len(words) * 1.1
    score += term_hits * 10.0 + number_patterns * 4.0 + min(useful_punctuation, 8) * 0.5
    if len(text) <= 2 and not digits:
        score -= 8.0
    if not _ocr_line_has_recipe_signal(text):
        score -= 10.0
    if symbol_ratio > 0.28 and term_hits == 0:
        score -= 18.0 * symbol_ratio
    if alpha_ratio < 0.35 and not _ocr_line_has_recipe_signal(text):
        score -= 7.0
    if long_letter_runs >= 2 and term_hits == 0:
        score -= 6.0 * long_letter_runs
    if short_word_ratio > 0.42 and term_hits == 0:
        score -= 9.0
    if len(words) >= 2 and term_hits == 0:
        vowel_words = sum(1 for word in words if re.search(r"[aeiouyæøåAEIOUYÆØÅ]", word))
        if vowel_words / max(1, len(words)) < 0.45:
            score -= 10.0
    return score


def _ocr_candidate_score(text: str) -> float:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return 0.0
    line_scores = [_ocr_line_quality(line) for line in lines]
    useful_lines = sum(1 for score in line_scores if score >= 4.0)
    weak_lines = sum(1 for score in line_scores if score < 1.0)
    words = re.findall(r"\S+", text)
    return sum(line_scores) + useful_lines * 5.0 + len(words) * 0.35 - weak_lines * 2.5


def _ocr_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _ocr_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _ocr_words_to_lines(rows: list[dict], source: str, image_size: tuple[int, int]) -> list[dict]:
    grouped: dict[tuple[int, int, int, int], list[dict]] = defaultdict(list)
    for row in rows:
        text = re.sub(r"\s+", " ", str(row.get("text") or "")).strip()
        conf = _ocr_float(row.get("conf"), -1.0)
        if not text or conf < 0:
            continue
        key = (
            _ocr_int(row.get("page_num"), 1),
            _ocr_int(row.get("block_num"), 0),
            _ocr_int(row.get("par_num"), 0),
            _ocr_int(row.get("line_num"), 0),
        )
        grouped[key].append({
            "text": text,
            "conf": conf,
            "left": _ocr_int(row.get("left")),
            "top": _ocr_int(row.get("top")),
            "width": _ocr_int(row.get("width")),
            "height": _ocr_int(row.get("height")),
            "word_num": _ocr_int(row.get("word_num")),
        })

    lines = []
    image_width, image_height = image_size
    for key, words in grouped.items():
        words.sort(key=lambda item: (item["word_num"], item["left"]))
        text = " ".join(word["text"] for word in words).strip()
        if not text:
            continue
        left = min(word["left"] for word in words)
        top = min(word["top"] for word in words)
        right = max(word["left"] + word["width"] for word in words)
        bottom = max(word["top"] + word["height"] for word in words)
        weighted = sum(word["conf"] * max(1, len(word["text"])) for word in words)
        weight = sum(max(1, len(word["text"])) for word in words)
        conf = weighted / max(1, weight)
        quality = _ocr_line_quality(text)
        width_ratio = (right - left) / max(1, image_width)
        height_ratio = (bottom - top) / max(1, image_height)
        lines.append({
            "key": key,
            "source": source,
            "text": text,
            "conf": conf,
            "quality": quality,
            "score": quality + max(0.0, conf - 45.0) * 0.35,
            "bbox": (left, top, right, bottom),
            "width_ratio": width_ratio,
            "height_ratio": height_ratio,
        })
    lines.sort(key=lambda item: (item["bbox"][1], item["bbox"][0], item["key"]))
    return lines


def _ocr_text_fingerprint(text: str) -> str:
    return re.sub(r"[^0-9a-zæøå]+", "", (text or "").lower())


def _ocr_lines_similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) < 12:
        return a == b
    if shorter in longer and len(shorter) / max(1, len(longer)) >= 0.58:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.82


def _dedupe_ocr_lines(lines: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    order = []
    for line in lines:
        key = _ocr_text_fingerprint(line.get("text", ""))
        if len(key) < 4:
            continue
        matched_key = next((existing for existing in order if _ocr_lines_similar(key, existing)), None)
        if matched_key is None:
            order.append(key)
            best[key] = line
            continue
        if line.get("score", 0) > best[matched_key].get("score", 0):
            best[matched_key] = line
    return [best[key] for key in order]


def _ocr_line_bucket(line: dict, page_height: int) -> str:
    text = line.get("text", "")
    conf = float(line.get("conf", 0.0))
    quality = float(line.get("quality", 0.0))
    top = line.get("bbox", (0, 0, 0, 0))[1]
    lower = text.lower()
    has_signal = _ocr_line_has_recipe_signal(text)
    words = re.findall(r"[A-Za-zÆØÅæøå]{2,}", text)
    chars = [ch for ch in text if not ch.isspace()]
    symbols = sum(1 for ch in chars if not ch.isalnum() and ch not in ".,;:()/-+%*")
    symbol_ratio = symbols / max(1, len(chars))

    if re.search(r"\bdiagram\b", lower):
        return "diagram"
    if conf < 35 or quality < 3:
        return "uncertain" if has_signal else "rejected"
    if symbol_ratio > 0.34 and not has_signal:
        return "rejected"
    if not has_signal and conf < 70:
        return "uncertain" if len(words) >= 3 else "rejected"
    if top < page_height * 0.14 and (conf >= 55 or has_signal):
        return "header"
    if re.search(r"\d+\s*(?:\([^)]+\)\s*){1,}\d+|\d+\s*(?:cm|g|mnd|mm)\b", lower):
        return "counts"
    return "body" if has_signal or conf >= 74 else "uncertain"


def _format_ocr_evidence_page(page_no: int, path: Path, buckets: dict[str, list[dict]], metrics: dict, diagram_md: str = "") -> str:
    sections = [
        f"## OCR evidence page {page_no}: {path.name}",
        f"Quality: avg_conf={metrics.get('avg_conf', 0):.1f}, accepted_lines={metrics.get('accepted_lines', 0)}, uncertain_lines={metrics.get('uncertain_lines', 0)}, rejected_lines={metrics.get('rejected_lines', 0)}",
    ]
    if diagram_md:
        sections.extend(["", "### Diagram evidence", diagram_md])
    labels = [
        ("header", "Header/title candidates"),
        ("counts", "Sizes/counts/material lines"),
        ("body", "Instruction/body lines"),
        ("diagram", "Diagram/legend text"),
        ("uncertain", "Low-confidence but possibly useful lines"),
    ]
    for key, title in labels:
        lines = buckets.get(key) or []
        if not lines:
            continue
        sections.extend(["", f"### {title}"])
        for line in lines[:80]:
            bbox = line.get("bbox", (0, 0, 0, 0))
            sections.append(f"- conf {line.get('conf', 0):.0f}, y {bbox[1]}: {line.get('text', '')}")
    rejected = buckets.get("rejected") or []
    if rejected:
        samples = "; ".join(line.get("text", "")[:70] for line in rejected[:8])
        sections.extend(["", f"Rejected noise summary: {len(rejected)} lines hidden. Samples: {samples}"])
    return "\n".join(sections).strip()


def _format_ocr_final_text(page_no: int, path: Path, buckets: dict[str, list[dict]], diagram_md: str = "") -> str:
    lines = [f"<!-- Page {page_no}: {path.name} -->"]
    ordered = []
    for key in ("header", "counts", "body", "diagram", "uncertain"):
        ordered.extend(buckets.get(key) or [])
    ordered.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    last_y = None
    for line in ordered:
        y = line["bbox"][1]
        if last_y is not None and y - last_y > 52 and lines[-1] != "":
            lines.append("")
        lines.append(line["text"])
        last_y = y
    if diagram_md:
        if lines[-1] != "":
            lines.append("")
        lines.append(diagram_md)
    return "\n".join(lines).strip()


def _strip_page_marker(text: str) -> str:
    return re.sub(r"(?m)^\s*<!--\s*Page\s+\d+:\s*.*?-->\s*$\n?", "", text or "").strip()


def _normalise_for_loss_check(text: str) -> set[str]:
    words = re.findall(r"[0-9A-Za-zÆØÅæøå]{2,}", (text or "").lower())
    return {word for word in words if len(word) > 2 or any(ch.isdigit() for ch in word)}


def _ai_cleanup_looks_lossy(source: str, cleaned: str) -> bool:
    source_words = re.findall(r"\S+", _strip_page_marker(source))
    cleaned_words = re.findall(r"\S+", _strip_page_marker(cleaned))
    if len(source_words) >= 35 and len(cleaned_words) < max(18, int(len(source_words) * 0.62)):
        return True
    source_terms = _normalise_for_loss_check(source)
    cleaned_terms = _normalise_for_loss_check(cleaned)
    if len(source_terms) >= 24:
        retained = len(source_terms & cleaned_terms) / max(1, len(source_terms))
        if retained < 0.50:
            return True
    return False


def _cleanup_ocr_markdown(text: str, unclear_marker: str = "[unclear]") -> str:
    lines = []
    for raw in (text or "").splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        # Keep OCR conservative: only strip repeated decoration, never rewrite knitting tokens.
        line = re.sub(r"^[|:;,.·•\-\s]+$", "", line).strip()
        if line:
            chars = [ch for ch in line if not ch.isspace()]
            alnum = sum(1 for ch in chars if ch.isalnum())
            symbols = sum(1 for ch in chars if not ch.isalnum() and ch not in ".,;:()/-+%*")
            symbol_ratio = symbols / max(1, len(chars))
            quality = _ocr_line_quality(line)
            if len(line) <= 2 and not any(ch.isdigit() for ch in line):
                continue
            if symbol_ratio > 0.38 and quality < 5.0:
                continue
            if alnum <= 2 and quality < 4.0:
                continue
            if not _ocr_line_has_recipe_signal(line):
                continue
            if quality < 4.0:
                continue
            if quality < -4.0:
                continue
        if line:
            lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()


def _line_groups(active_indexes: list[int], max_gap: int = 2) -> list[tuple[int, int]]:
    if not active_indexes:
        return []
    groups = []
    start = prev = active_indexes[0]
    for idx in active_indexes[1:]:
        if idx - prev <= max_gap:
            prev = idx
            continue
        groups.append((start, prev))
        start = prev = idx
    groups.append((start, prev))
    return groups


def _group_centres(groups: list[tuple[int, int]]) -> list[int]:
    return [int(round((a + b) / 2)) for a, b in groups]


def _regular_line_sequence(centres: list[int], min_lines: int) -> list[int]:
    centres = sorted({int(c) for c in centres})
    if len(centres) < min_lines:
        return []
    best: list[int] = []
    for i, start in enumerate(centres):
        for j in range(i + 1, min(len(centres), i + 8)):
            spacing = centres[j] - start
            if spacing < 20 or spacing > 130:
                continue
            seq = [start, centres[j]]
            expected = centres[j] + spacing
            tolerance = max(4, int(spacing * 0.32))
            while True:
                match = min((c for c in centres if c > seq[-1]), key=lambda c: abs(c - expected), default=None)
                if match is None or abs(match - expected) > tolerance:
                    break
                seq.append(match)
                expected = match + spacing
            if len(seq) > len(best):
                best = seq
    return best if len(best) >= min_lines else []


def _edge_line_centres(pixels, x1: int, y1: int, x2: int, y2: int, axis: str) -> list[int]:
    if axis == "x":
        span = max(1, y2 - y1)
        threshold = max(8, int(span * 0.15))
        active = [x for x in range(x1, x2) if sum(1 for y in range(y1, y2) if pixels[x, y] == 0) >= threshold]
        margin = max(8, int((x2 - x1) * 0.015))
        centres = _group_centres(_line_groups(active, max_gap=3))
        return [x for x in centres if x1 + margin <= x <= x2 - margin]
    else:
        span = max(1, x2 - x1)
        threshold = max(8, int(span * 0.15))
        active = [y for y in range(y1, y2) if sum(1 for x in range(x1, x2) if pixels[x, y] == 0) >= threshold]
        margin = max(8, int((y2 - y1) * 0.015))
        centres = _group_centres(_line_groups(active, max_gap=3))
        return [y for y in centres if y1 + margin <= y <= y2 - margin]


def _detect_light_chart_regions(path: Path, existing: list[dict]) -> list[dict]:
    from PIL import Image, ImageOps, ImageFilter

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("L")
    small = img
    max_dim = 900
    scale = 1.0
    if max(img.size) > max_dim:
        scale = max_dim / max(img.size)
        small = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.BILINEAR)
    edge = ImageOps.autocontrast(small.filter(ImageFilter.FIND_EDGES))
    width, height = edge.size
    candidates: list[dict] = []
    existing_boxes = [chart.get("bbox") or [] for chart in existing]

    def overlaps_existing(box: list[int]) -> bool:
        x1, y1, x2, y2 = box
        for raw in existing_boxes:
            if len(raw) != 4:
                continue
            ex1, ey1, ex2, ey2 = [int(v * scale) for v in raw]
            ix = max(0, min(x2, ex2) - max(x1, ex1))
            iy = max(0, min(y2, ey2) - max(y1, ey1))
            if ix * iy > 0.35 * min(max(1, (x2 - x1) * (y2 - y1)), max(1, (ex2 - ex1) * (ey2 - ey1))):
                return True
        return False

    for threshold in (32, 46):
        bw = edge.point(lambda p: 0 if p > threshold else 255, mode="L")
        pixels = bw.load()
        for band_h in (180, 260, 380, 520):
            if band_h > height + 80:
                continue
            step_y = max(55, band_h // 4)
            for y1 in range(0, max(1, height - band_h + 1), step_y):
                y2 = min(height, y1 + band_h)
                x_centres = _regular_line_sequence(_edge_line_centres(pixels, 0, y1, width, y2, "x"), 5)
                if len(x_centres) < 5:
                    continue
                spacing_x = int(round((max(x_centres) - min(x_centres)) / max(1, len(x_centres) - 1)))
                x1 = max(0, min(x_centres) - max(8, spacing_x // 2))
                x2 = min(width, max(x_centres) + max(8, spacing_x // 2))
                y_centres = _regular_line_sequence(_edge_line_centres(pixels, x1, y1, x2, y2, "y"), 4)
                if len(y_centres) < 4:
                    continue
                box = [min(x_centres), min(y_centres), max(x_centres), max(y_centres)]
                grid_w = box[2] - box[0]
                grid_h = box[3] - box[1]
                if grid_w < 90 or grid_h < 80:
                    continue
                if overlaps_existing(box):
                    continue
                score = len(x_centres) * len(y_centres) + min(grid_w, grid_h) * 0.02
                candidates.append({
                    "score": score,
                    "x_lines": x_centres,
                    "y_lines": y_centres,
                    "bbox": box,
                })

    candidates.sort(key=lambda item: item["score"], reverse=True)
    accepted: list[dict] = []
    for candidate in candidates:
        x1, y1, x2, y2 = candidate["bbox"]
        duplicate = False
        for other in accepted:
            ox1, oy1, ox2, oy2 = other["bbox"]
            ix = max(0, min(x2, ox2) - max(x1, ox1))
            iy = max(0, min(y2, oy2) - max(y1, oy1))
            if ix * iy > 0.45 * min((x2 - x1) * (y2 - y1), (ox2 - ox1) * (oy2 - oy1)):
                duplicate = True
                break
        if duplicate:
            continue
        accepted.append(candidate)
        if len(accepted) >= 2:
            break
    return [{
        "x_lines": [int(round(x / scale)) for x in item["x_lines"]],
        "y_lines": [int(round(y / scale)) for y in item["y_lines"]],
        "bbox": [int(round(v / scale)) for v in item["bbox"]],
        "light_grid": True,
    } for item in accepted]


def _detect_chart_regions(path: Path) -> list[dict]:
    from PIL import Image, ImageOps

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("L")
    small = img
    max_dim = 1800
    scale = 1.0
    if max(img.size) > max_dim:
        scale = max_dim / max(img.size)
        small = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.BILINEAR)
    bw = ImageOps.autocontrast(small).point(lambda p: 0 if p < 155 else 255, mode="L")
    width, height = bw.size
    pixels = bw.load()

    full_col_counts = []
    for x in range(width):
        full_col_counts.append(sum(1 for y in range(height) if pixels[x, y] == 0))
    active_full_cols = [i for i, count in enumerate(full_col_counts) if count >= max(60, int(height * 0.20))]
    full_col_groups = _line_groups(active_full_cols, max_gap=3)
    full_cols = _group_centres(full_col_groups)
    if len(full_cols) < 4:
        return _detect_light_chart_regions(path, [])
    x_scan1 = max(0, min(full_cols) - 8)
    x_scan2 = min(width - 1, max(full_cols) + 8)

    row_counts = []
    for y in range(height):
        row_counts.append(sum(1 for x in range(x_scan1, x_scan2 + 1) if pixels[x, y] == 0))
    scan_width = max(1, x_scan2 - x_scan1 + 1)
    active_rows = [i for i, count in enumerate(row_counts) if count >= max(24, int(scan_width * 0.32))]
    row_groups = _line_groups(active_rows, max_gap=2)
    row_centres = _group_centres(row_groups)

    clusters: list[list[int]] = []
    for y in row_centres:
        if not clusters or y - clusters[-1][-1] > 45:
            clusters.append([y])
        else:
            clusters[-1].append(y)

    charts = []
    for rows in clusters:
        if len(rows) < 4:
            continue
        y1 = max(0, rows[0] - 6)
        y2 = min(height - 1, rows[-1] + 6)
        col_counts = []
        for x in range(width):
            col_counts.append(sum(1 for y in range(y1, y2 + 1) if pixels[x, y] == 0))
        active_cols = [i for i, count in enumerate(col_counts) if count >= max(18, int((y2 - y1) * 0.42))]
        col_groups = _line_groups(active_cols, max_gap=2)
        cols = _group_centres(col_groups)
        if len(cols) < 4:
            continue
        # Keep the densest ruled segment if labels/noise created extra vertical groups.
        col_clusters: list[list[int]] = []
        for x in cols:
            if not col_clusters or x - col_clusters[-1][-1] > 55:
                col_clusters.append([x])
            else:
                col_clusters[-1].append(x)
        cols = max(col_clusters, key=len)
        if len(cols) < 4:
            continue
        x_lines = [int(round(x / scale)) for x in cols]
        y_lines = [int(round(y / scale)) for y in rows]
        charts.append({
            "x_lines": x_lines,
            "y_lines": y_lines,
            "bbox": [min(x_lines), min(y_lines), max(x_lines), max(y_lines)],
        })
    charts.extend(_detect_light_chart_regions(path, charts))
    return charts


def _ocr_chart_title(path: Path, chart: dict, languages: str) -> str:
    from PIL import Image, ImageOps

    try:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img).convert("L")
        x1 = max(0, min(chart["x_lines"]) - 15)
        x2 = min(img.width, max(chart["x_lines"]) + 140)
        y1 = max(0, min(chart["y_lines"]) - 95)
        y2 = max(1, min(chart["y_lines"]) - 8)
        if y2 <= y1:
            return ""
        crop = ImageOps.autocontrast(img.crop((x1, y1, x2, y2)))
        crop = ImageOps.expand(crop, border=12, fill=255)
        title = _run_tesseract_image(crop, languages, psm=7, timeout=45)
        title = re.sub(r"\s+", " ", title).strip(" -:\n\t")
        return title[:80]
    except Exception:
        return ""


def _extract_chart_markdown(path: Path, languages: str) -> str:
    specs = _extract_chart_specs(path, languages)
    blocks = []
    for spec in specs:
        blocks.append(
            "\n".join([
                f"## {spec['title']}",
                "",
                "```klchart-v1",
                spec["chart_code"],
                "```",
                "",
                "_Diagram symbols are detected from the grid image and should be reviewed against the original._",
            ])
        )
    return "\n\n".join(blocks).strip()


def _chart_palette_for_cells(cells: list[list[str]]) -> list[dict]:
    symbols = sorted({cell for row in cells for cell in row if cell and cell != "."})
    defaults = [
        ("A", "#159bd7", "main colour"),
        ("B", "#222222", "dark symbol"),
        ("C", "#d94f45", "accent"),
        ("D", "#5aa86a", "accent 2"),
    ]
    palette = [{"symbol": ".", "label": "empty", "color": "#ffffff"}]
    for symbol in symbols:
        match = next((item for item in defaults if item[0] == symbol), None)
        palette.append({
            "symbol": symbol,
            "label": match[2] if match else f"symbol {symbol}",
            "color": match[1] if match else "#777777",
        })
    return palette


def _chart_code(title: str, columns: int, rows: int, cells: list[list[str]], repeat_count: Optional[int] = None) -> str:
    lines = [
        f'title "{title}"',
        f"size {columns}x{rows}",
    ]
    if repeat_count:
        lines.append(f"repeat {repeat_count}")
    lines.append("legend . empty")
    for entry in _chart_palette_for_cells(cells):
        if entry["symbol"] != ".":
            lines.append(f"legend {entry['symbol']} {entry['label']}")
    # Store row 1 as the bottom knitted row. This is friendlier for knitting charts
    # and keeps visual reconstruction deterministic.
    for row_number, visual_row in enumerate(reversed(cells), start=1):
        lines.append(f"row {row_number}: {''.join(visual_row)}")
    return "\n".join(lines)


def _detect_repeat_count_near_chart(path: Path, chart: dict, languages: str) -> Optional[int]:
    from PIL import Image, ImageOps

    try:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img).convert("L")
        x1 = max(0, min(chart["x_lines"]) - 40)
        x2 = min(img.width, max(chart["x_lines"]) + 40)
        y1 = min(img.height - 1, max(chart["y_lines"]) + 4)
        y2 = min(img.height, max(chart["y_lines"]) + 130)
        if y2 <= y1:
            return None
        crop = ImageOps.expand(ImageOps.autocontrast(img.crop((x1, y1, x2, y2))), border=10, fill=255)
        text = _run_tesseract_image(crop, languages, psm=7, timeout=30)
        match = re.search(r"(?:repeat|gjenta)\s+(\d+)", text, re.I)
        return int(match.group(1)) if match else None
    except Exception:
        return None


def _extract_chart_specs(path: Path, languages: str) -> list[dict]:
    from PIL import Image, ImageOps

    charts = _detect_chart_regions(path)
    if not charts:
        return []
    img = Image.open(path)
    rgb = ImageOps.exif_transpose(img).convert("RGB")
    specs = []
    for index, chart in enumerate(charts, start=1):
        xs = chart["x_lines"]
        ys = chart["y_lines"]
        columns = max(0, len(xs) - 1)
        rows = max(0, len(ys) - 1)
        if columns < 2 or rows < 2:
            continue
        cells: list[list[str]] = []
        filled = 0
        confidence_hits = []
        for visual_row in range(rows):
            row = []
            y_top, y_bottom = ys[visual_row], ys[visual_row + 1]
            for col in range(columns):
                x_left, x_right = xs[col], xs[col + 1]
                pad_x = max(2, int((x_right - x_left) * 0.20))
                pad_y = max(2, int((y_bottom - y_top) * 0.20))
                xa, xb = max(0, x_left + pad_x), min(rgb.width, x_right - pad_x)
                ya, yb = max(0, y_top + pad_y), min(rgb.height, y_bottom - pad_y)
                if xb <= xa or yb <= ya:
                    row.append(".")
                    continue
                total = 0
                blueish = 0
                dark = 0
                saturated = 0
                for y in range(ya, yb):
                    for x in range(xa, xb):
                        r, g, b = rgb.getpixel((x, y))
                        total += 1
                        if b > 115 and b > r + 25 and b > g - 10:
                            blueish += 1
                        if r < 85 and g < 85 and b < 85:
                            dark += 1
                        if max(r, g, b) - min(r, g, b) > 55 and max(r, g, b) < 245:
                            saturated += 1
                ratio = max(blueish, dark, saturated) / max(1, total)
                dark_ratio = dark / max(1, total)
                if ratio > 0.22 and blueish >= dark:
                    row.append("A")
                    filled += 1
                    confidence_hits.append(min(1.0, ratio * 2.8))
                elif ratio > 0.18 or (dark_ratio > 0.025 and dark >= 8):
                    row.append("B")
                    filled += 1
                    confidence_hits.append(min(1.0, max(ratio, dark_ratio) * 2.5))
                else:
                    row.append(".")
            cells.append(row)
        title = "" if chart.get("light_grid") else _ocr_chart_title(path, chart, languages)
        title = title or f"Chart {index}"
        repeat_count = None if chart.get("light_grid") else _detect_repeat_count_near_chart(path, chart, languages)
        confidence = sum(confidence_hits) / max(1, len(confidence_hits)) if filled else 0.0
        if confidence < 0.2:
            continue
        specs.append({
            "title": title,
            "rows": rows,
            "columns": columns,
            "source_bbox": chart.get("bbox") or [min(xs), min(ys), max(xs), max(ys)],
            "palette": _chart_palette_for_cells(cells),
            "cells": cells,
            "chart_code": _chart_code(title, columns, rows, cells, repeat_count),
            "repeat_count": repeat_count,
            "confidence": round(confidence, 3),
        })
    return specs


def _ocr_page_to_result(path: Path, languages: str, diagram_enabled: bool, page_no: int, max_variants: int = 4) -> dict:
    if diagram_enabled:
        diagram_md = _extract_chart_markdown(path, languages)
    else:
        diagram_md = ""
    line_candidates = []
    configs = [
        ["-c", "preserve_interword_spaces=1"],
        ["-c", "preserve_interword_spaces=1", "-c", "textord_heavy_nr=1"],
    ]
    images = [
        ("gray", _ocr_preprocess_grayscale(path)),
        ("binary", _ocr_preprocess_image(path)),
    ]
    variants_run = 0
    for image_label, img in images:
        for psm in (6, 4, 11):
            for config in configs:
                if variants_run >= max(1, max_variants):
                    break
                variants_run += 1
                try:
                    rows = _run_tesseract_tsv_image(img, languages, psm=psm, config=config)
                    lines = _ocr_words_to_lines(rows, f"{image_label}/psm{psm}", img.size)
                    if lines:
                        line_candidates.extend(lines)
                except Exception:
                    continue
            if variants_run >= max(1, max_variants):
                break
        if variants_run >= max(1, max_variants):
            break

    deduped = _dedupe_ocr_lines(line_candidates)
    if not deduped:
        text_candidates = []
        for _, img in images[:1]:
            for psm in (6, 4):
                try:
                    cleaned = _cleanup_ocr_markdown(_run_tesseract_image(img, languages, psm=psm, config=configs[0]))
                except Exception:
                    continue
                if cleaned:
                    text_candidates.append(cleaned)
        text = max(text_candidates, key=_ocr_candidate_score, default="")
        text = text if _ocr_candidate_score(text) >= 6 else ""
        return {
            "text": "\n\n".join(part for part in (f"<!-- Page {page_no}: {path.name} -->\n\n{text}" if text else "", diagram_md) if part).strip(),
            "evidence": f"## OCR evidence page {page_no}: {path.name}\n\n{text or '[no usable OCR lines]'}".strip(),
            "warnings": [f"Page {page_no}: Tesseract returned no structured TSV lines."],
            "metrics": {"avg_conf": 0.0, "accepted_lines": 0, "uncertain_lines": 0, "rejected_lines": 0, "variants_run": variants_run},
        }

    page_height = max(img.height for _, img in images)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for line in deduped:
        buckets[_ocr_line_bucket(line, page_height)].append(line)
    for key in list(buckets.keys()):
        buckets[key].sort(key=lambda item: (item["bbox"][1], item["bbox"][0], -item.get("score", 0)))

    accepted = [line for key in ("header", "counts", "body", "diagram") for line in buckets.get(key, [])]
    avg_conf = sum(float(line.get("conf", 0.0)) for line in accepted) / max(1, len(accepted))
    metrics = {
        "avg_conf": avg_conf,
        "accepted_lines": len(accepted),
        "uncertain_lines": len(buckets.get("uncertain") or []),
        "rejected_lines": len(buckets.get("rejected") or []),
        "variants_run": variants_run,
    }
    warnings = []
    if accepted and avg_conf < 55:
        warnings.append(f"Page {page_no}: OCR confidence is low; review against the original image.")
    if len(buckets.get("rejected") or []) > max(8, len(accepted)):
        warnings.append(f"Page {page_no}: decorative or diagram noise was heavily filtered.")
    if not accepted and buckets.get("uncertain"):
        warnings.append(f"Page {page_no}: only low-confidence OCR lines were found.")

    text = _format_ocr_final_text(page_no, path, buckets, diagram_md=diagram_md)
    evidence = _format_ocr_evidence_page(page_no, path, buckets, metrics, diagram_md=diagram_md)
    return {"text": text, "evidence": evidence, "warnings": warnings, "metrics": metrics}


def _ocr_page_to_markdown(path: Path, languages: str, diagram_enabled: bool) -> str:
    return _ocr_page_to_result(path, languages, diagram_enabled, 1).get("text", "")


def _collect_ocr_markdown_from_paths(
    paths: list[Path],
    language: str,
    cfg: dict,
    progress_job_id: str = "",
) -> tuple[str, str, int, str, str, list[str]]:
    languages = _ocr_languages_for(language, cfg)
    diagram_enabled = _is_truthy(cfg.get("ocr_diagram_enabled"), True)
    engine = _ocr_engine_for(cfg)
    max_variants = int(_clamped_float(cfg.get("ocr_max_variants"), 4, 1, 12))
    page_workers = int(_clamped_float(cfg.get("ocr_page_workers"), 2, 1, 4))
    pages_by_index: dict[int, str] = {}
    evidence_by_index: dict[int, str] = {}
    warnings = []
    def run_one(idx: int, path: Path) -> tuple[int, str, str, list[str], str]:
        page_text = ""
        page_warnings: list[str] = []
        used_engine = engine
        if used_engine == "paddleocr":
            diagram_md = _extract_chart_markdown(path, languages) if diagram_enabled else ""
            try:
                ocr_text = _run_paddleocr_image(path, language)
            except Exception:
                used_engine = "tesseract"
                page_result = _ocr_page_to_result(path, languages, diagram_enabled, idx, max_variants=max_variants)
                page_text = page_result.get("text", "")
                evidence = page_result.get("evidence", "")
                page_warnings.extend(page_result.get("warnings", []))
            else:
                ocr_text = _cleanup_ocr_markdown(ocr_text)
                page_text = "\n\n".join(part for part in (f"<!-- Page {idx}: {path.name} -->", diagram_md, ocr_text) if part).strip()
                evidence = f"## OCR evidence page {idx}: {path.name}\n\nEngine: PaddleOCR\n\n{page_text}".strip()
        else:
            page_result = _ocr_page_to_result(path, languages, diagram_enabled, idx, max_variants=max_variants)
            page_text = page_result.get("text", "")
            evidence = page_result.get("evidence", "")
            page_warnings.extend(page_result.get("warnings", []))
        return idx, page_text, evidence, page_warnings, used_engine

    if page_workers > 1 and len(paths) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if progress_job_id:
            _update_ai_job(progress_job_id, pages_sent=0, progress_stage="ocr_pages")
        with ThreadPoolExecutor(max_workers=min(page_workers, len(paths))) as pool:
            futures = {pool.submit(run_one, idx, path): idx for idx, path in enumerate(paths, start=1)}
            completed = 0
            for future in as_completed(futures):
                if progress_job_id and _ai_job_cancelled(progress_job_id):
                    break
                idx, page_text, evidence, page_warnings, used_engine = future.result()
                if used_engine != "paddleocr":
                    engine = used_engine
                if page_text:
                    pages_by_index[idx] = page_text
                if evidence:
                    evidence_by_index[idx] = evidence
                warnings.extend(page_warnings)
                completed += 1
                if progress_job_id:
                    _update_ai_job(progress_job_id, pages_sent=completed, progress_stage=f"ocr_page_{completed}")
    else:
        for idx, path in enumerate(paths, start=1):
            if progress_job_id:
                _update_ai_job(progress_job_id, pages_sent=idx - 1, progress_stage=f"ocr_page_{idx}")
                if _ai_job_cancelled(progress_job_id):
                    break
            idx, page_text, evidence, page_warnings, used_engine = run_one(idx, path)
            if used_engine != "paddleocr":
                engine = used_engine
            if page_text:
                pages_by_index[idx] = page_text
            if evidence:
                evidence_by_index[idx] = evidence
            warnings.extend(page_warnings)
            if progress_job_id:
                _update_ai_job(progress_job_id, pages_sent=idx, progress_stage=f"ocr_page_{idx}")
    return (
        "\n\n---\n\n".join(pages_by_index[idx] for idx in sorted(pages_by_index)).strip(),
        "\n\n---\n\n".join(evidence_by_index[idx] for idx in sorted(evidence_by_index)).strip(),
        len(paths),
        languages,
        engine,
        warnings,
    )


def _paddle_lang_for(language: str) -> str:
    return "en"


def _run_paddleocr_image(path: Path, language: str) -> str:
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as e:
        raise RuntimeError(f"PaddleOCR is not installed: {e}")

    try:
        engine = PaddleOCR(use_angle_cls=True, lang=_paddle_lang_for(language), show_log=False)
    except TypeError:
        engine = PaddleOCR(use_angle_cls=True, lang=_paddle_lang_for(language))
    result = engine.ocr(str(path), cls=True)
    lines = []
    for page in result or []:
        for item in page or []:
            try:
                text = item[1][0]
                confidence = float(item[1][1])
            except Exception:
                continue
            if text and confidence >= 0.35:
                lines.append(str(text).strip())
    return _cleanup_ocr_markdown("\n".join(lines))


def _collect_ocr_markdown(recipe_id: str, conn, max_pages: int, language: str, cfg: dict) -> tuple[str, str, int, str, str, list[str]]:
    paths = _collect_recipe_image_paths(recipe_id, conn, max_pages)
    return _collect_ocr_markdown_from_paths(paths, language, cfg)


def _ocr_cleanup_prompt(language: str = "en") -> str:
    if (language or "").lower().startswith("no"):
        return (
            "Du får strukturert OCR-bevis fra en strikkeoppskrift. Lag ferdig Markdown-oppskrift fra beviset. "
            "Bruk hovedsakelig linjer under Header/title, Sizes/counts/material og Instruction/body. "
            "Lav-konfidenslinjer kan brukes bare når de tydelig passer med konteksten. Ignorer rejected/noise. "
            "Behold originalspråk, tall, forkortelser, masker, pinner, parenteser og rad-/omgangstekst nøyaktig. "
            "Ikke finn på manglende tekst; skriv [uklart] for uleselige små deler. Behold diagramblokker som faktadata. "
            "Returner kun ferdig Markdown. /no_think"
        )
    return (
        "You receive structured OCR evidence from a knitting pattern. Reconstruct the finished Markdown pattern from it. "
        "Prefer lines under Header/title, Sizes/counts/material, and Instruction/body. Use low-confidence lines only when "
        "they clearly fit the surrounding context. Ignore rejected/noise summaries. Preserve the original language, numbers, "
        "abbreviations, stitch counts, needles, parentheses, and row/round wording exactly. Do not invent missing text; use "
        "[unclear] for small unreadable fragments. Preserve diagram blocks as factual extracted data. Return only Markdown. /no_think"
    )


def _ocr_review_page_cleanup_prompt(language: str = "en") -> str:
    if (language or "").lower().startswith("no"):
        return (
            "Du rydder OCR fra nøyaktig én side i en strikkeoppskrift. Returner kun Markdown for denne ene siden. "
            "Behold all synlig tekst fra OCR så langt det er mulig: overskrifter, forkortelser, tabeller, størrelser, garn, "
            "pinneinfo, rad-/omgangstekst og korte linjer. Ikke oppsummer, ikke forkort, ikke flytt tekst til andre sider, "
            "og ikke legg til tekst som ikke finnes i OCR. Rydd bare åpenbare OCR-feil og linjebrudd. "
            "Behold tall, parenteser, norske strikkeforkortelser og rekkefølge. Marker usikre små deler som [uklart]. "
            "Ikke bruk kodeblokker eller ```markdown. /no_think"
        )
    return (
        "Clean OCR from exactly one page of a knitting pattern. Return only Markdown for this page. Preserve all visible "
        "OCR text as far as possible: headings, abbreviations, tables, sizes, yarn, needle details, row/round instructions, "
        "and short lines. Do not summarize, shorten, merge with other pages, or add text that is not in the OCR. Only fix "
        "obvious OCR errors and line breaks. Preserve numbers, parentheses, knitting abbreviations, and order. Mark small "
        "uncertain fragments as [unclear]. Do not use code fences or ```markdown. /no_think"
    )


async def _call_ai_text_cleanup(cfg: dict, content: str, language: str, timeout: int) -> tuple[str, dict]:
    base_url = cfg.get("ai_base_url", "").rstrip("/")
    model = cfg.get("ai_model", "").strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="AI base URL and model are required")
    messages = [{
        "role": "user",
        "content": f"{_ocr_cleanup_prompt(language)}\n\nOCR input:\n\n{content}",
    }]
    headers = {"Content-Type": "application/json"}
    if cfg.get("ai_api_key"):
        headers["Authorization"] = f"Bearer {cfg['ai_api_key']}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.05,
                "stream": False,
                "max_tokens": 4096,
            },
        )
        res.raise_for_status()
        data = res.json()
    return _clean_ai_transcription(data["choices"][0]["message"]["content"]), data.get("usage") or {}


async def _call_ai_review_page_cleanup(cfg: dict, content: str, language: str, timeout: int) -> tuple[str, dict]:
    base_url = cfg.get("ai_base_url", "").rstrip("/")
    model = cfg.get("ai_model", "").strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="AI base URL and model are required")
    messages = [{
        "role": "user",
        "content": f"{_ocr_review_page_cleanup_prompt(language)}\n\nPage OCR:\n\n{content}",
    }]
    headers = {"Content-Type": "application/json"}
    if cfg.get("ai_api_key"):
        headers["Authorization"] = f"Bearer {cfg['ai_api_key']}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.02,
                "stream": False,
                "max_tokens": 4096,
            },
        )
        res.raise_for_status()
        data = res.json()
    return _clean_ai_transcription(data["choices"][0]["message"]["content"]), data.get("usage") or {}


async def _call_ai_vision_transcription(recipe_id: str, language: str, cfg: dict, conn, max_pages: int, timeout: int) -> tuple[str, dict, int, str]:
    prompt = cfg.get("ai_custom_prompt", "").strip() if cfg.get("ai_prompt_mode") == "custom" else _default_ocr_prompt(language)
    image_payloads = _collect_recipe_image_payloads(recipe_id, conn, max_pages)
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": f"{prompt}\n\nImportant: output only the finished Markdown transcription. Do not output reasoning, thoughts, or channel markers. If this is a Qwen/QwQ-style reasoning model, use /no_think and provide only the final answer.\n/no_think"},
            *image_payloads,
        ],
    }]
    headers = {"Content-Type": "application/json"}
    if cfg.get("ai_api_key"):
        headers["Authorization"] = f"Bearer {cfg['ai_api_key']}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(
            f"{cfg.get('ai_base_url', '').rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": cfg.get("ai_model", "").strip(),
                "messages": messages,
                "temperature": 0.1,
                "stream": False,
                "max_tokens": 4096,
            },
        )
        res.raise_for_status()
        data = res.json()
    return _clean_ai_transcription(data["choices"][0]["message"]["content"]), data.get("usage") or {}, len(image_payloads), prompt


async def _generate_text_content(recipe_id: str, language: str, cfg: dict, conn, timeout: int, max_pages: int, job_id: str = "") -> dict:
    mode = _normalise_recognition_mode(cfg.get("ai_recognition_mode"))
    ai_ready = bool(cfg.get("ai_base_url", "").rstrip("/") and cfg.get("ai_model", "").strip())
    prompt = cfg.get("ai_custom_prompt", "").strip() if cfg.get("ai_prompt_mode") == "custom" else _default_ocr_prompt(language)
    steps = ["load pages"]
    warnings = []
    image_paths: list[Path] = []
    try:
        image_paths = _collect_recipe_image_paths(recipe_id, conn, max_pages)
    except Exception:
        image_paths = []

    if mode == "ai_vision_only":
        if not ai_ready:
            raise HTTPException(status_code=400, detail="AI base URL and model are required")
        content, usage, pages_sent, prompt = await _call_ai_vision_transcription(recipe_id, language, cfg, conn, max_pages, timeout)
        estimated_image_tokens = _estimate_image_tokens(image_paths)
        warnings.append("Provider token totals may exclude or approximate image tokens.")
        return {
            "content": content,
            "usage": usage,
            "pages_sent": pages_sent,
            "provider": cfg.get("ai_provider", "openai_compatible"),
            "model": cfg.get("ai_model", "").strip(),
            "prompt": prompt,
            "workflow": "AI vision only",
            "engine": "ai_vision",
            "steps": [*steps, "AI vision transcription"],
            "warnings": warnings,
            "estimated_input_tokens": estimated_image_tokens + _estimate_text_tokens(prompt),
            "estimated_image_tokens": estimated_image_tokens,
            "token_report_note": "Provider-reported token totals may not match billing when image inputs are used.",
            "ocr_text": "",
        }

    if not _is_truthy(cfg.get("ocr_enabled"), True):
        if mode == "ocr_only":
            raise HTTPException(status_code=400, detail="Local OCR is not enabled")
        if not ai_ready:
            raise HTTPException(status_code=400, detail="Local OCR is disabled and AI base URL/model are not configured")
        content, usage, pages_sent, prompt = await _call_ai_vision_transcription(recipe_id, language, cfg, conn, max_pages, timeout)
        estimated_image_tokens = _estimate_image_tokens(image_paths)
        warnings.append("Local OCR was disabled; AI vision fallback used.")
        warnings.append("Provider token totals may exclude or approximate image tokens.")
        return {
            "content": content,
            "usage": usage,
            "pages_sent": pages_sent,
            "provider": cfg.get("ai_provider", "openai_compatible"),
            "model": cfg.get("ai_model", "").strip(),
            "prompt": prompt,
            "workflow": "AI vision fallback",
            "engine": "ai_vision",
            "steps": [*steps, "AI vision fallback"],
            "warnings": warnings,
            "estimated_input_tokens": estimated_image_tokens + _estimate_text_tokens(prompt),
            "estimated_image_tokens": estimated_image_tokens,
            "token_report_note": "Provider-reported token totals may not match billing when image inputs are used.",
            "ocr_text": "",
        }

    try:
        requested_ocr_engine = _ocr_engine_for(cfg)
        if not image_paths:
            image_paths = _collect_recipe_image_paths(recipe_id, conn, max_pages)
        if job_id:
            _update_ai_job(job_id, progress_stage="preprocess", pages_sent=0)
        content, ocr_evidence, pages_sent, ocr_languages, ocr_engine, ocr_warnings = await asyncio.to_thread(
            _collect_ocr_markdown_from_paths,
            image_paths,
            language,
            cfg,
            job_id,
        )
        warnings.extend(ocr_warnings)
        if requested_ocr_engine == "paddleocr" and ocr_engine != "paddleocr":
            warnings.append("PaddleOCR was requested but unavailable or failed; Tesseract fallback was used.")
        steps.extend(["preprocess images", f"{ocr_engine} OCR", "structured OCR evidence"])
        if _is_truthy(cfg.get("ocr_diagram_enabled"), True):
            steps.append("diagram extraction")
    except Exception as e:
        if mode == "ocr_first" and ai_ready:
            content, usage, pages_sent, prompt = await _call_ai_vision_transcription(recipe_id, language, cfg, conn, max_pages, timeout)
            estimated_image_tokens = _estimate_image_tokens(image_paths)
            warnings.append(f"Local OCR failed; AI vision fallback used: {e}")
            warnings.append("Provider token totals may exclude or approximate image tokens.")
            return {
                "content": content,
                "usage": usage,
                "pages_sent": pages_sent,
                "provider": cfg.get("ai_provider", "openai_compatible"),
                "model": cfg.get("ai_model", "").strip(),
                "prompt": prompt,
                "workflow": "OCR first -> AI vision fallback",
                "engine": "ai_vision",
                "steps": [*steps, "OCR failed", "AI vision fallback"],
                "warnings": warnings,
                "estimated_input_tokens": estimated_image_tokens + _estimate_text_tokens(prompt),
                "estimated_image_tokens": estimated_image_tokens,
                "token_report_note": "Provider-reported token totals may not match billing when image inputs are used.",
                "ocr_text": "",
            }
        raise

    if not content and mode == "ocr_first" and ai_ready:
        content, usage, pages_sent, prompt = await _call_ai_vision_transcription(recipe_id, language, cfg, conn, max_pages, timeout)
        estimated_image_tokens = _estimate_image_tokens(image_paths)
        warnings.append("Local OCR found no useful text; AI vision fallback used.")
        warnings.append("Provider token totals may exclude or approximate image tokens.")
        return {
            "content": content,
            "usage": usage,
            "pages_sent": pages_sent,
            "provider": cfg.get("ai_provider", "openai_compatible"),
            "model": cfg.get("ai_model", "").strip(),
            "prompt": prompt,
            "workflow": "OCR first -> AI vision fallback",
            "engine": "ai_vision",
            "steps": [*steps, "OCR empty", "AI vision fallback"],
            "warnings": warnings,
            "estimated_input_tokens": estimated_image_tokens + _estimate_text_tokens(prompt),
            "estimated_image_tokens": estimated_image_tokens,
            "token_report_note": "Provider-reported token totals may not match billing when image inputs are used.",
            "ocr_text": "",
        }
    if not content:
        content = "_No text was detected by local OCR. Review the original recipe images._"
        warnings.append("Local OCR did not detect useful text.")

    usage = {}
    provider = "local_ocr"
    model = f"{ocr_engine}:{ocr_languages}"
    ocr_text = content
    cleanup_input = ocr_evidence or content
    estimated_input_tokens = _estimate_text_tokens(content)
    token_report_note = "No AI provider tokens were used."
    if mode != "ocr_only" and _is_truthy(cfg.get("ocr_cleanup_enabled"), True) and ai_ready:
        try:
            cleaned, usage = await _call_ai_text_cleanup(cfg, cleanup_input, language, timeout)
            if cleaned.strip():
                content = cleaned
                provider = "local_ocr+ai_cleanup"
                model = f"{ocr_engine}:{ocr_languages}+{cfg.get('ai_model', '').strip()}"
                steps.append("AI cleanup")
                estimated_input_tokens = _estimate_text_tokens(cleanup_input) + _estimate_text_tokens(_ocr_cleanup_prompt(language))
                token_report_note = "Provider-reported token totals are from text cleanup only."
        except Exception as e:
            # OCR output is still useful and far cheaper than failing the job.
            warnings.append(f"AI cleanup failed; raw OCR text was saved: {e}")

    return {
        "content": content,
        "usage": usage,
        "pages_sent": pages_sent,
        "provider": provider,
        "model": model,
        "prompt": "ocr_first" if mode == "ocr_first" else "ocr_only",
        "workflow": f"{ocr_engine} OCR" + (" -> AI cleanup" if provider.endswith("ai_cleanup") else ""),
        "engine": ocr_engine,
        "steps": steps,
        "warnings": warnings,
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_image_tokens": 0,
        "token_report_note": token_report_note,
        "ocr_text": ocr_text,
    }


async def _generate_text_version(recipe_id: str, language: str, current_user: dict) -> dict:
    start_ts = time.time()
    conn = get_db()
    cfg = _ai_settings(conn, reveal_secret=True)
    if cfg.get("ai_enabled", "false").lower() != "true":
        conn.close()
        raise HTTPException(status_code=400, detail="AI text recognition is not enabled")
    base_url = cfg.get("ai_base_url", "").rstrip("/")
    model = cfg.get("ai_model", "").strip()
    mode = _normalise_recognition_mode(cfg.get("ai_recognition_mode"))
    if mode == "ai_vision_only" and (not base_url or not model):
        conn.close()
        raise HTTPException(status_code=400, detail="AI base URL and model are required")
    timeout = int(_clamped_float(cfg.get("ai_timeout"), 600, 60, 1800))
    timeout = max(300, timeout)
    max_pages = int(_clamped_float(cfg.get("ai_max_pages"), 8, 1, 30))
    fingerprint = _source_fingerprint(recipe_id, conn)
    try:
        result = await _generate_text_content(recipe_id, language, cfg, conn, timeout, max_pages)
    except httpx.ReadTimeout:
        conn.close()
        raise HTTPException(status_code=504, detail=f"AI request timed out after {timeout} seconds. Increase the timeout or use fewer pages/a faster model.")
    except httpx.HTTPError as e:
        conn.close()
        detail = str(e) or e.__class__.__name__
        raise HTTPException(status_code=502, detail=f"AI request failed: {detail}")
    finally:
        if conn:
            conn.close()
    content = result["content"]
    result["duration_seconds"] = time.time() - start_ts

    now = datetime.utcnow().isoformat()
    conn2 = get_db()
    conn2.execute(
        "INSERT INTO recipe_text_versions (recipe_id,content_markdown,status,language,prompt,provider,model,source_fingerprint,generated_by,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(recipe_id) DO UPDATE SET content_markdown=excluded.content_markdown,status=excluded.status,language=excluded.language,prompt=excluded.prompt,provider=excluded.provider,model=excluded.model,source_fingerprint=excluded.source_fingerprint,generated_by=excluded.generated_by,updated_at=excluded.updated_at",
        (recipe_id, content, "ready", language, result["prompt"], result["provider"], result["model"], fingerprint, current_user["username"], now, now)
    )
    conn2.commit()
    _record_generation_audit(recipe_id, result)
    row = conn2.execute("SELECT * FROM recipe_text_versions WHERE recipe_id=?", (recipe_id,)).fetchone()
    audit = conn2.execute("SELECT * FROM recipe_text_generation_audits WHERE recipe_id=?", (recipe_id,)).fetchone()
    conn2.close()
    data = _text_version_dict(row, fingerprint)
    data["generation_audit"] = _audit_dict(audit)
    return data


def _job_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("pages_sent", "result_text_chars", "dismissed"):
        data[key] = int(data.get(key) or 0)
    data["dismissed"] = bool(data["dismissed"])
    if data.get("duration_seconds") is not None:
        data["duration_seconds"] = round(float(data["duration_seconds"]), 1)
    return data


def _update_ai_job(job_id: str, **fields) -> None:
    if not fields:
        return
    allowed = {
        "status", "progress_stage", "error", "provider", "model", "pages_sent",
        "result_text_chars", "duration_seconds", "started_at", "finished_at",
        "dismissed",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    conn = get_db()
    assignments = ", ".join(f"{key}=?" for key in updates)
    conn.execute(f"UPDATE ai_text_jobs SET {assignments} WHERE id=?", (*updates.values(), job_id))
    conn.commit()
    conn.close()


def _ai_job_cancelled(job_id: str) -> bool:
    conn = get_db()
    row = conn.execute("SELECT status FROM ai_text_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    return bool(row and row["status"] == "cancelled")


def _record_ai_usage(
    job_id: str,
    recipe_id: str,
    provider: str,
    model: str,
    usage: dict,
    content: str,
    pages_sent: int,
    duration: float,
    success: bool,
) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO ai_usage_events (id,job_id,recipe_id,provider,model,prompt_tokens,completion_tokens,total_tokens,generated_chars,generated_words,pages_sent,duration_seconds,success,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            job_id,
            recipe_id,
            provider,
            model,
            usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            usage.get("completion_tokens") if isinstance(usage, dict) else None,
            usage.get("total_tokens") if isinstance(usage, dict) else None,
            len(content or ""),
            len(re.findall(r"\S+", content or "")),
            pages_sent,
            duration,
            1 if success else 0,
            datetime.utcnow().isoformat(),
        )
    )
    conn.commit()
    conn.close()


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _estimate_text_tokens(text: str) -> int:
    return max(0, int((len(text or "") + 3) / 4))


def _estimate_image_tokens(paths: list[Path]) -> int:
    from PIL import Image

    total = 0
    for path in paths:
        try:
            with Image.open(path) as img:
                width, height = img.size
            tiles = max(1, ((width + 511) // 512) * ((height + 511) // 512))
            total += 85 + tiles * 170
        except Exception:
            total += 765
    return total


def _record_generation_audit(recipe_id: str, audit: dict, job_id: str = "") -> None:
    now = datetime.utcnow().isoformat()
    usage = audit.get("usage") or {}
    content = audit.get("content") or ""
    ocr_text = audit.get("ocr_text") or ""
    conn = get_db()
    conn.execute(
        """
        INSERT INTO recipe_text_generation_audits (
            recipe_id, job_id, workflow, engine, provider, model, steps_json, warnings_json,
            pages_processed, ocr_chars, ocr_words, output_chars, output_words,
            provider_prompt_tokens, provider_completion_tokens, provider_total_tokens,
            estimated_input_tokens, estimated_image_tokens, duration_seconds, token_report_note, created_at
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(recipe_id) DO UPDATE SET
            job_id=excluded.job_id,
            workflow=excluded.workflow,
            engine=excluded.engine,
            provider=excluded.provider,
            model=excluded.model,
            steps_json=excluded.steps_json,
            warnings_json=excluded.warnings_json,
            pages_processed=excluded.pages_processed,
            ocr_chars=excluded.ocr_chars,
            ocr_words=excluded.ocr_words,
            output_chars=excluded.output_chars,
            output_words=excluded.output_words,
            provider_prompt_tokens=excluded.provider_prompt_tokens,
            provider_completion_tokens=excluded.provider_completion_tokens,
            provider_total_tokens=excluded.provider_total_tokens,
            estimated_input_tokens=excluded.estimated_input_tokens,
            estimated_image_tokens=excluded.estimated_image_tokens,
            duration_seconds=excluded.duration_seconds,
            token_report_note=excluded.token_report_note,
            created_at=excluded.created_at
        """,
        (
            recipe_id,
            job_id,
            audit.get("workflow", ""),
            audit.get("engine", ""),
            audit.get("provider", ""),
            audit.get("model", ""),
            json.dumps(audit.get("steps") or [], ensure_ascii=False),
            json.dumps(audit.get("warnings") or [], ensure_ascii=False),
            int(audit.get("pages_sent") or audit.get("pages_processed") or 0),
            len(ocr_text),
            _word_count(ocr_text),
            len(content),
            _word_count(content),
            usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            usage.get("completion_tokens") if isinstance(usage, dict) else None,
            usage.get("total_tokens") if isinstance(usage, dict) else None,
            audit.get("estimated_input_tokens"),
            audit.get("estimated_image_tokens"),
            audit.get("duration_seconds"),
            audit.get("token_report_note", ""),
            now,
        )
    )
    conn.commit()
    conn.close()


def _chart_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("source_bbox_json", "palette_json", "cells_json"):
        out_key = key.replace("_json", "")
        try:
            data[out_key] = json.loads(data.get(key) or "[]")
        except Exception:
            data[out_key] = []
        data.pop(key, None)
    data["rows"] = int(data.get("rows") or 0)
    data["columns"] = int(data.get("columns") or 0)
    data["confidence"] = float(data.get("confidence") or 0)
    if data.get("repeat_count") is not None:
        data["repeat_count"] = int(data["repeat_count"])
    return data


def _chart_source_for_recipe(recipe_id: str, page_key: str, conn) -> Path:
    recipe = _get_recipe_full(recipe_id, conn)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    recipe_dir = DATA_DIR / recipe_id
    if recipe["file_type"] == "pdf":
        path = recipe_dir / page_key
        if not path.exists():
            _convert_pdf_to_pages(recipe_dir)
        if not path.exists():
            raise HTTPException(status_code=404, detail="PDF page image not found")
        return path
    safe_name = Path(page_key).name
    path = recipe_dir / safe_name
    if not path.exists() or safe_name not in set(recipe.get("images") or []):
        raise HTTPException(status_code=404, detail="Image not found")
    return path


def _collect_recipe_chart_sources(recipe_id: str, conn, max_pages: int) -> list[tuple[str, Path]]:
    recipe = _get_recipe_full(recipe_id, conn)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    paths = _collect_recipe_image_paths(recipe_id, conn, max_pages)
    if recipe["file_type"] == "images":
        return [(path.name, path) for path in paths]
    return [(path.name, path) for path in paths]


def _refresh_recipe_charts(recipe_id: str, language: str, cfg: dict, current_user: dict, max_pages: Optional[int] = None) -> list[dict]:
    conn = get_db()
    fingerprint = _source_fingerprint(recipe_id, conn)
    limit = max_pages if max_pages is not None else int(_clamped_float(cfg.get("ai_max_pages"), 8, 1, 30))
    languages = _ocr_languages_for(language, cfg)
    sources = _collect_recipe_chart_sources(recipe_id, conn, limit)
    now = datetime.utcnow().isoformat()
    conn.execute("DELETE FROM recipe_charts WHERE recipe_id=? AND generated_by='detector'", (recipe_id,))
    for page_key, path in sources:
        for spec in _extract_chart_specs(path, languages):
            conn.execute(
                """
                INSERT INTO recipe_charts (
                    id, recipe_id, page_key, title, source_bbox_json, rows, columns,
                    palette_json, cells_json, chart_code, repeat_count, confidence,
                    generated_by, source_fingerprint, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    recipe_id,
                    page_key,
                    spec["title"],
                    json.dumps(spec["source_bbox"], ensure_ascii=False),
                    spec["rows"],
                    spec["columns"],
                    json.dumps(spec["palette"], ensure_ascii=False),
                    json.dumps(spec["cells"], ensure_ascii=False),
                    spec["chart_code"],
                    spec.get("repeat_count"),
                    spec.get("confidence", 0),
                    "detector",
                    fingerprint,
                    now,
                    now,
                )
            )
    conn.commit()
    rows = conn.execute("SELECT * FROM recipe_charts WHERE recipe_id=? ORDER BY page_key, created_at", (recipe_id,)).fetchall()
    conn.close()
    return [_chart_dict(row) for row in rows]


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


def _make_review_asset(
    recipe_id: str,
    session_id: str,
    page_path: Path,
    crop: dict,
    title: str = "",
    grid_columns: int = 0,
    grid_rows: int = 0,
    rotation: float = 0.0,
    kind: str = "diagram",
) -> str:
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter, ImageDraw, ImageFont

    img = ImageOps.exif_transpose(Image.open(page_path)).convert("RGB")
    box = _review_crop_box(crop, img.size)
    crop_img = img.crop(box)
    if rotation:
        crop_img = crop_img.rotate(float(rotation), expand=True, fillcolor=(246, 246, 242), resample=Image.Resampling.BICUBIC)
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
            for col in range(grid_columns + 1):
                x = round(col * crop_img.width / grid_columns)
                draw.line((x, grid_top, x, grid_top + crop_img.height), fill=line_color, width=1)
            for row in range(grid_rows + 1):
                y = grid_top + round(row * crop_img.height / grid_rows)
                draw.line((0, y, crop_img.width, y), fill=line_color, width=1)
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


async def _create_review_session_from_ocr(
    recipe_id: str,
    language: str,
    cfg: dict,
    username: str,
    job_id: str = "",
) -> dict:
    conn = get_db()
    fingerprint = _source_fingerprint(recipe_id, conn)
    max_pages = int(_clamped_float(cfg.get("ai_max_pages"), 8, 1, 30))
    paths = _collect_recipe_image_paths(recipe_id, conn, max_pages)
    languages = _ocr_languages_for(language, cfg)
    max_variants = int(_clamped_float(cfg.get("ocr_max_variants"), 4, 1, 12))
    ai_ready = bool(cfg.get("ai_base_url", "").rstrip("/") and cfg.get("ai_model", "").strip())
    timeout = int(_clamped_float(cfg.get("ai_timeout"), 600, 60, 1800))
    timeout = max(300, timeout)
    conn.close()

    page_results = []
    for idx, path in enumerate(paths, start=1):
        result = await asyncio.to_thread(_ocr_page_to_result, path, languages, False, idx, max_variants)
        ocr_text = result.get("text", "").strip() or "_No text was detected on this page._"
        reviewed_text = _clean_ai_transcription(ocr_text)
        if _is_truthy(cfg.get("ocr_cleanup_enabled"), True) and ai_ready:
            try:
                cleaned, _usage = await _call_ai_review_page_cleanup(cfg, ocr_text, language, timeout)
                cleaned = cleaned.strip()
                if cleaned and not _ai_cleanup_looks_lossy(ocr_text, cleaned):
                    reviewed_text = cleaned
            except Exception:
                pass
        page_results.append((idx, path.name, ocr_text, reviewed_text))

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
    for idx, page_key, ocr_text, reviewed_text in page_results:
        conn.execute(
            "INSERT INTO recipe_review_pages (id,session_id,recipe_id,page_key,page_order,status,ocr_text,reviewed_text,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), session_id, recipe_id, page_key, idx, "draft", ocr_text, reviewed_text, now, now)
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
        (recipe_id, content, "ready", session["language"], "review_session", "reviewed_ocr", "", fingerprint, username, now, now)
    )
    conn.execute("UPDATE recipe_review_sessions SET status='completed', completed_at=?, updated_at=? WHERE id=?", (now, now, session_id))
    conn.commit()
    row = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    data = _review_session_dict(conn, row)
    conn.close()
    return data


async def _run_ai_text_job(job_id: str) -> None:
    conn = get_db()
    row = conn.execute("SELECT * FROM ai_text_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row or row["status"] == "cancelled":
        return
    start_ts = time.time()
    started_at = datetime.utcnow().isoformat()
    _update_ai_job(job_id, status="running", progress_stage="loading", started_at=started_at, error="")
    recipe_id = row["recipe_id"]
    language = row["language"] or "en"
    provider = ""
    model = ""
    pages_sent = 0
    content = ""
    usage = {}
    try:
        conn = get_db()
        cfg = _ai_settings(conn, reveal_secret=True)
        if cfg.get("ai_enabled", "false").lower() != "true":
            raise HTTPException(status_code=400, detail="AI text recognition is not enabled")
        mode = _normalise_recognition_mode(cfg.get("ai_recognition_mode"))
        base_url = cfg.get("ai_base_url", "").rstrip("/")
        model = cfg.get("ai_model", "").strip()
        provider = "local_ocr" if mode != "ai_vision_only" else cfg.get("ai_provider", "openai_compatible")
        display_model = "tesseract" if mode != "ai_vision_only" else model
        _update_ai_job(job_id, provider=provider, model=display_model)
        if mode == "ai_vision_only" and (not base_url or not model):
            raise HTTPException(status_code=400, detail="AI base URL and model are required")
        timeout = int(_clamped_float(cfg.get("ai_timeout"), 600, 60, 1800))
        timeout = max(300, timeout)
        max_pages = int(_clamped_float(cfg.get("ai_max_pages"), 8, 1, 30))
        try:
            result = await _create_review_session_from_ocr(recipe_id, language, cfg, row["generated_by"], job_id=job_id)
        finally:
            conn.close()
        content = "\n\n".join((page.get("reviewed_text") or page.get("ocr_text") or "") for page in result.get("pages", []))
        usage = {}
        pages_sent = result.get("page_count") or len(result.get("pages", []))
        provider = "local_ocr_review"
        model = "tesseract"
        _update_ai_job(job_id, provider=provider, model=model, pages_sent=pages_sent, progress_stage="ready_to_review")
        duration = time.time() - start_ts
        _record_ai_usage(job_id, recipe_id, provider, model, usage, content, pages_sent, duration, True)

        if _ai_job_cancelled(job_id):
            _update_ai_job(job_id, progress_stage="cancelled", finished_at=datetime.utcnow().isoformat(), duration_seconds=duration)
            return

        _update_ai_job(
            job_id,
            status="ready_to_review",
            progress_stage="ready_to_review",
            result_text_chars=len(content),
            duration_seconds=duration,
            finished_at=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        duration = time.time() - start_ts
        if not content:
            _record_ai_usage(job_id, recipe_id, provider, model, usage or {}, "", pages_sent, duration, False)
        detail = getattr(e, "detail", None) or str(e) or e.__class__.__name__
        if not _ai_job_cancelled(job_id):
            _update_ai_job(
                job_id,
                status="failed",
                progress_stage="failed",
                error=str(detail),
                duration_seconds=duration,
                finished_at=datetime.utcnow().isoformat(),
            )


async def _process_ai_text_queue() -> None:
    global _ai_queue_task
    try:
        async with _ai_queue_lock:
            while True:
                conn = get_db()
                row = conn.execute(
                    "SELECT * FROM ai_text_jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
                ).fetchone()
                conn.close()
                if not row:
                    break
                await _run_ai_text_job(row["id"])
    finally:
        _ai_queue_task = None


def _ensure_ai_queue_processor() -> None:
    global _ai_queue_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _ai_queue_task is None or _ai_queue_task.done():
        _ai_queue_task = loop.create_task(_process_ai_text_queue())


@app.on_event("startup")
async def _resume_ai_queue_on_startup():
    _ensure_ai_queue_processor()

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


@app.put("/api/recipes/bulk-update")
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


@app.post("/api/recipes/{recipe_id}/add-images")
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


@app.post("/api/recipes/{recipe_id}/images/{filename}/adjust")
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


@app.post("/api/recipes/{recipe_id}/images/{filename}/restore-original")
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


@app.get("/api/recipes/{recipe_id}/text-version")
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


@app.put("/api/recipes/{recipe_id}/text-version")
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


@app.post("/api/recipes/{recipe_id}/text-version/generate")
async def generate_recipe_text_version(recipe_id: str, data: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    language = str(data.get("language", "") or current_user.get("language", "en"))
    return await _generate_text_version(recipe_id, language, current_user)


@app.post("/api/recipes/{recipe_id}/text-version/jobs")
async def create_recipe_text_job(
    recipe_id: str,
    data: dict = Body(default={}),
    current_user: dict = Depends(get_current_user),
):
    language = str(data.get("language", "") or current_user.get("language", "en"))
    conn = get_db()
    recipe = conn.execute("SELECT id, title FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    if not recipe:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    existing = conn.execute(
        "SELECT * FROM ai_text_jobs WHERE recipe_id=? AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1",
        (recipe_id,)
    ).fetchone()
    if existing:
        conn.close()
        return {"job": _job_dict(existing)}
    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    cfg = _ai_settings(conn, reveal_secret=False)
    mode = _normalise_recognition_mode(cfg.get("ai_recognition_mode"))
    conn.execute(
        "INSERT INTO ai_text_jobs (id,recipe_id,recipe_title,status,progress_stage,language,provider,model,generated_by,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            job_id,
            recipe_id,
            recipe["title"],
            "queued",
            "queued",
            language,
            "local_ocr" if mode != "ai_vision_only" else cfg.get("ai_provider", "openai_compatible"),
            "tesseract" if mode != "ai_vision_only" else cfg.get("ai_model", ""),
            current_user["username"],
            now,
        )
    )
    conn.commit()
    row = conn.execute("SELECT * FROM ai_text_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    _ensure_ai_queue_processor()
    return {"job": _job_dict(row)}


@app.get("/api/recipes/{recipe_id}/review-session")
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


@app.post("/api/recipes/{recipe_id}/review-session")
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
    session = await _create_review_session_from_ocr(recipe_id, language, cfg, current_user["username"])
    session["exists"] = True
    return session


@app.put("/api/review-sessions/{session_id}/pages/{page_id}")
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


@app.post("/api/review-sessions/{session_id}/pause")
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


@app.post("/api/review-sessions/{session_id}/cancel")
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


@app.post("/api/review-sessions/{session_id}/complete")
def complete_review_session(session_id: str, current_user: dict = Depends(get_current_user)):
    data = _complete_review_session(session_id, current_user["username"])
    data["exists"] = True
    return data


@app.post("/api/review-sessions/{session_id}/pages/{page_id}/diagrams")
def create_review_diagram(session_id: str, page_id: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)):
    title = str(data.get("title") or "Diagram").strip()[:120] or "Diagram"
    crop = data.get("crop") if isinstance(data.get("crop"), dict) else {}
    grid_columns = int(_clamped_float(data.get("grid_columns"), 10, 1, 200))
    grid_rows = int(_clamped_float(data.get("grid_rows"), 10, 1, 200))
    rotation = float(_clamped_float(data.get("rotation"), 0, -45, 45))
    now = datetime.utcnow().isoformat()
    conn = get_db()
    session = conn.execute("SELECT * FROM recipe_review_sessions WHERE id=?", (session_id,)).fetchone()
    page = conn.execute("SELECT * FROM recipe_review_pages WHERE id=? AND session_id=?", (page_id, session_id)).fetchone()
    if not session or not page:
        conn.close()
        raise HTTPException(status_code=404, detail="Review session/page not found")
    page_path = _review_page_source(session["recipe_id"], page["page_key"], conn)
    rel_path = _make_review_asset(session["recipe_id"], session_id, page_path, crop, title, grid_columns, grid_rows, rotation, "diagram")
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


@app.post("/api/review-sessions/{session_id}/pages/{page_id}/legends")
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
    rel_path = _make_review_asset(session["recipe_id"], session_id, page_path, crop, title, 0, 0, 0, "legend")
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


@app.get("/api/recipes/{recipe_id}/review-assets/{asset_path:path}")
def get_review_asset(recipe_id: str, asset_path: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    path = _review_image_path(recipe_id, asset_path)
    return FileResponse(str(path), media_type="image/jpeg")


@app.get("/api/recipes/{recipe_id}/charts")
def get_recipe_charts(recipe_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    rows = conn.execute("SELECT * FROM recipe_charts WHERE recipe_id=? ORDER BY page_key, created_at", (recipe_id,)).fetchall()
    conn.close()
    return {"charts": [_chart_dict(row) for row in rows]}


@app.post("/api/recipes/{recipe_id}/charts/extract")
def extract_recipe_charts(recipe_id: str, data: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    language = str(data.get("language", "") or current_user.get("language", "en"))
    conn = get_db()
    if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    cfg = _ai_settings(conn, reveal_secret=True)
    conn.close()
    max_pages = int(_clamped_float(data.get("max_pages") or cfg.get("ai_max_pages"), 8, 1, 30))
    charts = _refresh_recipe_charts(recipe_id, language, cfg, current_user, max_pages=max_pages)
    return {"charts": charts}


@app.put("/api/recipes/{recipe_id}/charts/{chart_id}")
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


@app.get("/api/recipes/{recipe_id}/charts/{chart_id}/source")
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


@app.get("/api/work-queue")
def get_work_queue(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    _cleanup_stale_import_queue(conn)
    conn.commit()
    job_rows = conn.execute(
        "SELECT * FROM ai_text_jobs "
        "WHERE dismissed=0 AND (status IN ('queued','running') OR finished_at > datetime('now', '-7 days')) "
        "ORDER BY CASE status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 WHEN 'failed' THEN 2 WHEN 'finished' THEN 3 ELSE 4 END, "
        "CASE WHEN status IN ('running','queued') THEN created_at END ASC, created_at DESC"
    ).fetchall()
    import_rows = conn.execute(
        "SELECT iq.recipe_id, iq.group_name, r.title, r.file_type "
        "FROM import_queue iq JOIN recipes r ON r.id=iq.recipe_id "
        "WHERE iq.status='staged' ORDER BY iq.rowid"
    ).fetchall()
    conn.close()
    ai_jobs = []
    queue_position = 1
    for row in job_rows:
        job = _job_dict(row)
        if job["status"] in ("running", "queued"):
            job["queue_position"] = queue_position
            queue_position += 1
        else:
            job["queue_position"] = None
        ai_jobs.append(job)
    return {
        "ai_jobs": ai_jobs,
        "imports": {
            "count": len(import_rows),
            "items": [dict(row) for row in import_rows[:8]],
        },
    }


@app.post("/api/work-queue/ai/{job_id}/cancel")
def cancel_ai_job(job_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT * FROM ai_text_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] in ("finished", "failed"):
        conn.close()
        return {"job": _job_dict(row)}
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE ai_text_jobs SET status='cancelled', progress_stage='cancelled', finished_at=?, dismissed=0 WHERE id=?",
        (now, job_id)
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM ai_text_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    return {"job": _job_dict(updated)}


@app.post("/api/work-queue/ai/{job_id}/dismiss")
def dismiss_ai_job(job_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT * FROM ai_text_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] in ("queued", "running"):
        conn.close()
        raise HTTPException(status_code=400, detail="Only completed jobs can be dismissed")
    conn.execute("UPDATE ai_text_jobs SET dismissed=1 WHERE id=?", (job_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


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
    row  = conn.execute(
        "SELECT data FROM annotations WHERE recipe_id=? AND page_key=? AND user_id=?",
        (recipe_id, page_key, current_user["id"])
    ).fetchone()
    conn.close()
    return {"strokes": json.loads(row["data"]) if row else []}


@app.put("/api/recipes/{recipe_id}/annotations/{page_key}")
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


@app.delete("/api/recipes/{recipe_id}/annotations/{page_key}")
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
async def create_yarn(
    name:            str            = Form(...),
    colour:          str            = Form(""),
    wool_type:       str            = Form(""),
    yardage:         str            = Form(""),
    needles:         str            = Form(""),
    tension:         str            = Form(""),
    origin:          str            = Form(""),
    seller:          str            = Form(""),
    price_per_skein: str            = Form(""),
    product_info:    str            = Form(""),
    image:           Optional[UploadFile] = File(None),
    current_user:    dict           = Depends(get_current_user)
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    yarn_id  = str(uuid.uuid4())
    img_path = ""
    if image and image.filename:
        ext = Path(image.filename).suffix.lower()
        if ext not in IMAGE_EXTS:
            raise HTTPException(status_code=400, detail="Only jpg, png, webp images are accepted")
        file_data = await image.read()
        if len(file_data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image file too large (max 20 MB)")
        if not _validate_file_magic(file_data, ext):
            raise HTTPException(status_code=400, detail="File content does not match its extension")
        yarn_dir = YARN_DIR / yarn_id
        yarn_dir.mkdir(parents=True, exist_ok=True)
        dest = yarn_dir / f"yarn{ext}"
        with open(dest, "wb") as fh:
            fh.write(file_data)
        img_path = f"{yarn_id}/yarn{ext}"
    conn = get_db()
    conn.execute(
        "INSERT INTO yarns (id,name,colour,wool_type,yardage,needles,tension,origin,seller,price_per_skein,product_info,image_path,created_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (yarn_id, name, colour, wool_type, yardage, needles, tension, origin,
         seller, price_per_skein, product_info, img_path, datetime.utcnow().isoformat())
    )
    conn.commit()
    result = _yarn_to_dict(conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone(), conn)
    conn.close()
    return result


@app.put("/api/yarns/{yarn_id}")
async def update_yarn(
    yarn_id:         str,
    name:            str            = Form(""),
    colour:          str            = Form(""),
    wool_type:       str            = Form(""),
    yardage:         str            = Form(""),
    needles:         str            = Form(""),
    tension:         str            = Form(""),
    origin:          str            = Form(""),
    seller:          str            = Form(""),
    price_per_skein: str            = Form(""),
    product_info:    str            = Form(""),
    image:           Optional[UploadFile] = File(None),
    current_user:    dict           = Depends(get_current_user)
):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarns WHERE id=?", (yarn_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Yarn not found")
    if image and image.filename:
        ext = Path(image.filename).suffix.lower()
        if ext not in IMAGE_EXTS:
            conn.close()
            raise HTTPException(status_code=400, detail="Only jpg, png, webp images are accepted")
        file_data = await image.read()
        if len(file_data) > MAX_IMAGE_BYTES:
            conn.close()
            raise HTTPException(status_code=413, detail="Image file too large (max 20 MB)")
        if not _validate_file_magic(file_data, ext):
            conn.close()
            raise HTTPException(status_code=400, detail="File content does not match its extension")
        yarn_dir = YARN_DIR / yarn_id
        yarn_dir.mkdir(parents=True, exist_ok=True)
        dest = yarn_dir / f"yarn{ext}"
        with open(dest, "wb") as fh:
            fh.write(file_data)
        img_path = f"{yarn_id}/yarn{ext}"
        conn.execute(
            "UPDATE yarns SET name=?,colour=?,wool_type=?,yardage=?,needles=?,tension=?,origin=?,seller=?,price_per_skein=?,product_info=?,image_path=? WHERE id=?",
            (name, colour, wool_type, yardage, needles, tension, origin, seller,
             price_per_skein, product_info, img_path, yarn_id)
        )
    else:
        conn.execute(
            "UPDATE yarns SET name=?,colour=?,wool_type=?,yardage=?,needles=?,tension=?,origin=?,seller=?,price_per_skein=?,product_info=? WHERE id=?",
            (name, colour, wool_type, yardage, needles, tension, origin, seller,
             price_per_skein, product_info, yarn_id)
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
    url = _validate_public_url(url)
    parsed = urlparse(url)

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

    async def _safe_get(client: httpx.AsyncClient, start_url: str, expected: tuple[str, ...]):
        current = _validate_public_url(start_url)
        for _ in range(4):
            resp = await client.get(current, headers=headers)
            if resp.is_redirect:
                location = resp.headers.get("location", "")
                if not location:
                    raise HTTPException(status_code=502, detail="Redirect missing location")
                current = _validate_public_url(urljoin(current, location))
                continue
            ctype = resp.headers.get("content-type", "").lower()
            if expected and not any(kind in ctype for kind in expected):
                raise HTTPException(status_code=415, detail="Unsupported response type")
            if len(resp.content) > MAX_SCRAPE_BYTES:
                raise HTTPException(status_code=413, detail="Response too large")
            return resp
        raise HTTPException(status_code=400, detail="Too many redirects")

    handle      = parsed.path.strip("/").split("/")[-1].split("?")[0]
    shopify_url = f"{parsed.scheme}://{parsed.netloc}/products/{handle}.json"

    # Strategy 1: Shopify JSON API
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
            sj = await _safe_get(client, shopify_url, ("application/json", "text/json"))
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
                        result["image_url"] = src
                return result
    except Exception:
        pass

    # Strategy 2: HTML scraping
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
            resp = await _safe_get(client, url, ("text/html", "application/xhtml+xml"))
        soup   = BeautifulSoup(resp.text, "html.parser")
        result = {}
        h1     = soup.find("h1")
        if h1:
            result["name"] = _clean(h1.get_text())
        _parse_specs(soup, result)
        meta = soup.find("meta", {"property": "og:image"}) or soup.find("meta", {"name": "og:image"})
        if meta and meta.get("content"):
            result["scraped_image_url"] = meta["content"]
            result["image_url"] = meta["content"]
        if not result.get("name"):
            raise HTTPException(status_code=422, detail="Could not extract product name from page")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {e}")

# ── Admin: live logs ──────────────────────────────────────────────────────────

def _ai_log_lines(limit: int) -> list[str]:
    conn = get_db()
    rows = conn.execute("""
        SELECT
            j.id, j.recipe_title, j.status, j.progress_stage, j.error, j.provider, j.model,
            j.generated_by, j.pages_sent, j.result_text_chars, j.duration_seconds,
            j.created_at, j.started_at, j.finished_at,
            u.prompt_tokens, u.completion_tokens, u.total_tokens, u.generated_words, u.success
        FROM ai_text_jobs j
        LEFT JOIN ai_usage_events u ON u.job_id=j.id
        ORDER BY COALESCE(NULLIF(j.finished_at, ''), NULLIF(j.started_at, ''), j.created_at) DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    result = []
    for row in reversed(rows):
        ts = row["finished_at"] or row["started_at"] or row["created_at"]
        model = " / ".join(part for part in (row["provider"], row["model"]) if part) or "unknown-model"
        bits = [
            f"{ts} AI_JOB",
            f"status={row['status']}",
            f"recipe={row['recipe_title'] or row['id']}",
            f"model={model}",
            f"pages={row['pages_sent'] or 0}",
        ]
        if row["duration_seconds"] is not None:
            bits.append(f"duration={round(float(row['duration_seconds']), 1)}s")
        if row["total_tokens"] is not None:
            bits.append(f"tokens={row['total_tokens']}")
            bits.append(f"prompt={row['prompt_tokens'] or 0}")
            bits.append(f"completion={row['completion_tokens'] or 0}")
        if row["generated_words"]:
            bits.append(f"words={row['generated_words']}")
        if row["generated_by"]:
            bits.append(f"user={row['generated_by']}")
        if row["error"]:
            bits.append(f"error={row['error']}")
        result.append(" ".join(str(bit) for bit in bits))
    return result

@app.get("/api/admin/logs")
def get_logs(lines: int = 200, source: str = "all", admin: dict = Depends(require_admin)):
    """Return the last N lines from the persistent log files in /logs/.
    source: 'all' | 'uvicorn' | 'supervisord' | 'auth' | 'ai'
    """
    lines = max(10, min(lines, 1000))

    log_files = {
        "uvicorn":     Path("/logs/uvicorn.log"),
        "supervisord": Path("/logs/supervisord.log"),
        "auth":        Path("/logs/auth.log"),
    }

    sources = [*log_files.keys(), "ai"] if source == "all" else [source]
    collected = []

    for src in sources:
        if src == "ai":
            for line in _ai_log_lines(lines):
                collected.append(f"[ai] {line}")
            continue
        path = log_files.get(src)
        if not path or not path.exists():
            collected.append(f"[{src}] no log file yet — container may have just started")
            continue
        try:
            with open(path, "r", errors="replace") as f:
                file_lines = f.readlines()
            for line in file_lines:
                stripped = _redact_sensitive(line.rstrip())
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


# ── Admin: AI text recognition settings ─────────────────────────────────────

@app.get("/api/admin/ai")
def get_ai_settings(admin: dict = Depends(require_admin)):
    conn = get_db()
    settings = _ai_settings(conn)
    conn.close()
    return settings


@app.put("/api/admin/ai")
def save_ai_settings(data: dict, admin: dict = Depends(require_admin)):
    conn = get_db()
    existing = _ai_settings(conn, reveal_secret=True)
    for key in AI_SETTING_KEYS:
        if key not in data:
            continue
        value = str(data.get(key, ""))
        if key == "ai_api_key" and value == "••••••••":
            value = existing.get("ai_api_key", "")
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )
    conn.commit()
    conn.close()
    return {"message": "AI settings saved"}


@app.post("/api/admin/ai/models")
async def list_ai_models(data: dict = Body(default={}), admin: dict = Depends(require_admin)):
    conn = get_db()
    saved = _ai_settings(conn, reveal_secret=True)
    conn.close()
    cfg = {**saved, **{k: str(v) for k, v in data.items() if k in AI_SETTING_KEYS}}
    if cfg.get("ai_api_key") == "••••••••":
        cfg["ai_api_key"] = saved.get("ai_api_key", "")
    base_url = cfg.get("ai_base_url", "").rstrip("/")
    if not base_url:
        raise HTTPException(status_code=400, detail="Base URL is required")
    headers = {}
    if cfg.get("ai_api_key"):
        headers["Authorization"] = f"Bearer {cfg['ai_api_key']}"
    timeout = int(_clamped_float(cfg.get("ai_timeout"), 60, 10, 300))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.get(f"{base_url}/models", headers=headers)
            if res.status_code == 404 and base_url.endswith("/v1"):
                ollama_base = base_url[:-3].rstrip("/")
                res = await client.get(f"{ollama_base}/api/tags", headers=headers)
            res.raise_for_status()
            payload = res.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Model fetch failed: {e}")

    models = []
    if isinstance(payload.get("data"), list):
        models = [m.get("id") for m in payload["data"] if isinstance(m, dict) and m.get("id")]
    elif isinstance(payload.get("models"), list):
        models = [m.get("name") or m.get("model") for m in payload["models"] if isinstance(m, dict)]
    models = sorted({m for m in models if m})
    return {"models": models}


@app.post("/api/admin/ai/test")
async def test_ai_settings(data: dict = Body(default={}), admin: dict = Depends(require_admin)):
    conn = get_db()
    saved = _ai_settings(conn, reveal_secret=True)
    conn.close()
    cfg = {**saved, **{k: str(v) for k, v in data.items() if k in AI_SETTING_KEYS}}
    if cfg.get("ai_api_key") == "••••••••":
        cfg["ai_api_key"] = saved.get("ai_api_key", "")
    base_url = cfg.get("ai_base_url", "").rstrip("/")
    model = cfg.get("ai_model", "").strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="Base URL and model are required")
    headers = {"Content-Type": "application/json"}
    if cfg.get("ai_api_key"):
        headers["Authorization"] = f"Bearer {cfg['ai_api_key']}"
    timeout = int(_clamped_float(cfg.get("ai_timeout"), 60, 10, 300))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "temperature": 0,
                    "max_tokens": 8,
                },
            )
            res.raise_for_status()
            payload = res.json()
            text = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"AI test failed: {e}")
    return {"message": "AI test succeeded", "response": text}

# ── Statistics ───────────────────────────────────────────────────────────────────

AI_STATS_RANGES = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}


def _normalise_ai_stats_range(value: str) -> str:
    value = (value or "all").lower()
    if value in ("7days", "7_day", "7-day"):
        value = "7d"
    if value in ("30days", "30_day", "30-day"):
        value = "30d"
    return value if value in AI_STATS_RANGES else "all"


def _ai_range_start(scope: str) -> str:
    delta = AI_STATS_RANGES.get(scope)
    return (datetime.utcnow() - delta).isoformat() if delta else ""


def _effective_ai_stats_start(conn, scope: str) -> str:
    starts = [_ai_range_start(scope)]
    row = conn.execute(
        "SELECT reset_at FROM ai_stats_resets WHERE scope=?",
        (scope,)
    ).fetchone()
    if row and row["reset_at"]:
        starts.append(row["reset_at"])
    return max((start for start in starts if start), default="")


def _ai_event_where(start_at: str, success_only: bool = False) -> tuple[str, tuple]:
    clauses = []
    params = []
    if start_at:
        clauses.append("created_at >= ?")
        params.append(start_at)
    if success_only:
        clauses.append("success=1")
    return (f" WHERE {' AND '.join(clauses)}" if clauses else "", tuple(params))


def _ai_usage_stats(conn, scope: str = "all") -> dict:
    scope = _normalise_ai_stats_range(scope)
    start_at = _effective_ai_stats_start(conn, scope)

    def scalar(sql: str, params: tuple = ()):
        return conn.execute(sql, params).fetchone()["value"]

    where, params = _ai_event_where(start_at)
    success_where, success_params = _ai_event_where(start_at, success_only=True)
    ai_total_jobs = scalar(f"SELECT COUNT(*) as value FROM ai_usage_events{where}", params)
    ai_finished_jobs = scalar(f"SELECT COUNT(*) as value FROM ai_usage_events{success_where}", success_params)
    ai_failed_jobs = scalar(f"SELECT COUNT(*) as value FROM ai_usage_events WHERE success=0{' AND created_at >= ?' if start_at else ''}", (start_at,) if start_at else ())
    ai_prompt_tokens = scalar(f"SELECT COALESCE(SUM(prompt_tokens), 0) as value FROM ai_usage_events{where}", params)
    ai_completion_tokens = scalar(f"SELECT COALESCE(SUM(completion_tokens), 0) as value FROM ai_usage_events{where}", params)
    ai_total_tokens = scalar(f"SELECT COALESCE(SUM(total_tokens), 0) as value FROM ai_usage_events{where}", params)
    ai_generated_chars = scalar(f"SELECT COALESCE(SUM(generated_chars), 0) as value FROM ai_usage_events{success_where}", success_params)
    ai_generated_words = scalar(f"SELECT COALESCE(SUM(generated_words), 0) as value FROM ai_usage_events{success_where}", success_params)
    ai_pages_processed = scalar(f"SELECT COALESCE(SUM(pages_sent), 0) as value FROM ai_usage_events{where}", params)
    ai_avg_duration = scalar(f"SELECT COALESCE(AVG(duration_seconds), 0) as value FROM ai_usage_events{success_where}", success_params)
    ai_model_row = conn.execute(f"""
        SELECT provider, model, COUNT(*) as count
        FROM ai_usage_events
        {success_where}
        {"AND" if success_where else "WHERE"} (provider!='' OR model!='')
        GROUP BY provider, model
        ORDER BY count DESC
        LIMIT 1
    """, success_params).fetchone()

    return {
        "range": scope,
        "effective_start_at": start_at,
        "total_jobs": ai_total_jobs,
        "finished_jobs": ai_finished_jobs,
        "failed_jobs": ai_failed_jobs,
        "cancelled_jobs": 0,
        "success_rate": round((ai_finished_jobs / ai_total_jobs) * 100) if ai_total_jobs else 0,
        "prompt_tokens": ai_prompt_tokens,
        "completion_tokens": ai_completion_tokens,
        "total_tokens": ai_total_tokens,
        "generated_chars": ai_generated_chars,
        "generated_words": ai_generated_words,
        "pages_processed": ai_pages_processed,
        "avg_duration_seconds": round(float(ai_avg_duration), 1),
        "top_provider": ai_model_row["provider"] if ai_model_row else "",
        "top_model": ai_model_row["model"] if ai_model_row else "",
    }


@app.get("/api/stats")
def get_stats(ai_range: str = "all", current_user: dict = Depends(get_current_user)):
    """Return high-level library statistics."""
    conn = get_db()
    def scalar(sql: str, params: tuple = ()):
        return conn.execute(sql, params).fetchone()["value"]

    recipes = scalar("SELECT COUNT(*) as value FROM recipes")
    yarns  = scalar("SELECT COUNT(*) as value FROM yarns")
    users  = scalar("SELECT COUNT(*) as value FROM users")
    active = scalar("SELECT COUNT(*) as value FROM project_sessions WHERE finished_at IS NULL")
    finished = scalar("SELECT COUNT(*) as value FROM project_sessions WHERE finished_at IS NOT NULL")
    categories = scalar("SELECT COUNT(*) as value FROM categories")
    tags = scalar("SELECT COUNT(*) as value FROM tags")
    items = scalar("SELECT COUNT(*) as value FROM inventory_items")
    recipes_with_categories = scalar(
        "SELECT COUNT(DISTINCT recipe_id) as value FROM recipe_categories"
    )
    recipes_with_tags = scalar(
        "SELECT COUNT(DISTINCT recipe_id) as value FROM recipe_tags"
    )
    yarn_colours = scalar("SELECT COUNT(*) as value FROM yarn_colours")
    inventory_yarn_items = scalar(
        "SELECT COUNT(*) as value FROM inventory_items WHERE type='yarn'"
    )
    inventory_tool_items = scalar(
        "SELECT COUNT(*) as value FROM inventory_items WHERE type='tool'"
    )
    inventory_total_quantity = scalar(
        "SELECT COALESCE(SUM(quantity), 0) as value FROM inventory_items"
    )
    inventory_low_stock = scalar(
        "SELECT COUNT(*) as value FROM inventory_items WHERE quantity <= 1"
    )
    inventory_value_estimate = scalar("""
        SELECT COALESCE(SUM(
            CASE
                WHEN TRIM(purchase_price) = '' THEN 0
                ELSE CAST(REPLACE(REPLACE(purchase_price, ',', '.'), ' ', '') AS REAL) * quantity
            END
        ), 0) as value
        FROM inventory_items
    """)
    tool_category_rows = conn.execute("""
        SELECT COALESCE(NULLIF(category, ''), 'other') as category, COUNT(*) as count
        FROM inventory_items
        WHERE type='tool'
        GROUP BY COALESCE(NULLIF(category, ''), 'other')
    """).fetchall()
    tool_categories = {row["category"]: row["count"] for row in tool_category_rows}
    ai = _ai_usage_stats(conn, ai_range)
    total_sessions = active + finished
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
        "total_sessions": total_sessions,
        "recipes_with_categories": recipes_with_categories,
        "recipes_with_tags": recipes_with_tags,
        "uncategorized_recipes": max(0, recipes - recipes_with_categories),
        "untagged_recipes": max(0, recipes - recipes_with_tags),
        "completion_rate": round((finished / total_sessions) * 100) if total_sessions else 0,
        "category_coverage": round((recipes_with_categories / recipes) * 100) if recipes else 0,
        "tag_coverage": round((recipes_with_tags / recipes) * 100) if recipes else 0,
        "yarn_colours": yarn_colours,
        "inventory_yarn_items": inventory_yarn_items,
        "inventory_tool_items": inventory_tool_items,
        "inventory_total_quantity": inventory_total_quantity,
        "inventory_low_stock": inventory_low_stock,
        "inventory_value_estimate": round(float(inventory_value_estimate), 2),
        "tool_categories": {
            "needle": tool_categories.get("needle", 0),
            "tool": tool_categories.get("tool", 0),
            "notion": tool_categories.get("notion", 0),
            "other": tool_categories.get("other", 0),
        },
        "ai": ai,
    }


@app.post("/api/stats/ai/reset")
def reset_ai_stats(data: dict = Body(default={}), admin: dict = Depends(require_admin)):
    scope = _normalise_ai_stats_range(data.get("range", "all"))
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute("""
        INSERT INTO ai_stats_resets (scope, reset_at, reset_by)
        VALUES (?, ?, ?)
        ON CONFLICT(scope) DO UPDATE SET reset_at=excluded.reset_at, reset_by=excluded.reset_by
    """, (scope, now, admin["username"]))
    conn.commit()
    ai = _ai_usage_stats(conn, scope)
    conn.close()
    return {"message": "AI stats reset", "range": scope, "reset_at": now, "ai": ai}


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
    response = JSONResponse({"token": challenge, "user": _user_dict(dict(row))})
    _set_auth_cookies(response, challenge, request)
    return response

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
