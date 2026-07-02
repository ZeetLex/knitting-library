"""Shared backend foundation: imports, config, security, DB, and auth dependencies."""
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

async def security_headers(request: Request, call_next):
    response = await call_next(request)
    ct = response.headers.get("content-type", "")
    _apply_security_headers(response, is_html="text/html" in ct)
    return response
# ── CORS ──────────────────────────────────────────────────────────────────────
# Same-origin only by default. Set ALLOWED_ORIGINS env var if behind a reverse proxy.
_ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",")
_ALLOWED_ORIGINS = [o.strip() for o in _ALLOWED_ORIGINS if o.strip()]


DATA_DIR   = Path("/data/recipes")
YARN_DIR   = Path("/data/yarns")
DB_PATH    = Path("/data/recipes.db")
STATIC_DIR = Path("/app/frontend/build")

DATA_DIR.mkdir(parents=True, exist_ok=True)
YARN_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
AI_MAX_OUTPUT_TOKENS = int(os.environ.get("AI_MAX_OUTPUT_TOKENS", "32768"))
AI_SETTING_KEYS = {
    "ai_enabled",
    "ai_provider",
    "ai_base_url",
    "ai_model",
    "ai_api_key",
    "ai_timeout",
    "ai_max_pages",
    "ai_max_output_tokens",
    "ai_scan_temperature",
    "ai_cleanup_temperature",
    "ai_prompt_mode",
    "ai_custom_prompt",
    "ai_cleanup_enabled",
    "ai_cleanup_custom_prompt",
}

SESSION_COOKIE = "knitting_session"
CSRF_COOKIE = "knitting_csrf"
MAX_SCRAPE_BYTES = 5 * 1024 * 1024
_ai_queue_task: Optional[asyncio.Task] = None
_ai_queue_lock = asyncio.Lock()
_release_sync_task: Optional[asyncio.Task] = None
_release_sync_lock = asyncio.Lock()
GITHUB_RELEASES_URL = "https://api.github.com/repos/ZeetLex/knitting-library/releases"
GITHUB_RELEASES_HTML = "https://github.com/ZeetLex/knitting-library/releases"
RELEASE_SYNC_INTERVAL_SECONDS = 6 * 60 * 60

def _parse_trusted_proxies() -> list[ipaddress._BaseNetwork]:
    networks = []
    raw = os.environ.get("TRUSTED_PROXIES", "")
    for item in [p.strip() for p in raw.split(",") if p.strip()]:
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            print("Ignoring invalid TRUSTED_PROXIES entry")
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
    if "project_sessions" in tables:
        project_session_cols = [r["name"] for r in conn.execute("PRAGMA table_info(project_sessions)").fetchall()]
        if "user_id" not in project_session_cols:
            conn.execute("ALTER TABLE project_sessions ADD COLUMN user_id TEXT")
            conn.commit()
        if "username" not in project_session_cols:
            conn.execute("ALTER TABLE project_sessions ADD COLUMN username TEXT NOT NULL DEFAULT ''")
            conn.commit()
    if "users" in tables:
        user_cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "email" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
            conn.commit()
        if "background" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN background TEXT NOT NULL DEFAULT 'floral'")
            conn.commit()
    if "project_sessions" in tables and "users" in tables:
        fallback_user = conn.execute(
            "SELECT id, username FROM users ORDER BY is_admin DESC, created_date ASC LIMIT 1"
        ).fetchone()
        if fallback_user:
            conn.execute(
                """
                UPDATE project_sessions
                SET user_id=?,
                    username=CASE WHEN TRIM(COALESCE(username, ''))='' THEN ? ELSE username END
                WHERE user_id IS NULL OR TRIM(user_id)=''
                """,
                (fallback_user["id"], fallback_user["username"]),
            )
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
    if "recipe_viewer_progress" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recipe_viewer_progress (
                recipe_id             TEXT NOT NULL,
                user_id               TEXT NOT NULL,
                view_mode             TEXT NOT NULL DEFAULT 'original',
                image_index           INTEGER NOT NULL DEFAULT 0,
                zoom                  REAL NOT NULL DEFAULT 1,
                scroll_y              INTEGER NOT NULL DEFAULT 0,
                text_scroll_y         INTEGER NOT NULL DEFAULT 0,
                mobile_images_visible INTEGER NOT NULL DEFAULT 0,
                updated_at            TEXT NOT NULL,
                PRIMARY KEY (recipe_id, user_id),
                FOREIGN KEY (recipe_id) REFERENCES recipes(id),
                FOREIGN KEY (user_id)   REFERENCES users(id)
            )
        """)
        conn.commit()
    elif "recipe_viewer_progress" in tables:
        progress_cols = [r["name"] for r in conn.execute("PRAGMA table_info(recipe_viewer_progress)").fetchall()]
        if "text_scroll_y" not in progress_cols:
            conn.execute("ALTER TABLE recipe_viewer_progress ADD COLUMN text_scroll_y INTEGER NOT NULL DEFAULT 0")
            conn.commit()
    if "app_navigation_progress" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_navigation_progress (
                user_id    TEXT PRIMARY KEY,
                data_json  TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()
    if "recipe_knitting_tools" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recipe_knitting_tools (
                recipe_id  TEXT NOT NULL,
                user_id    TEXT NOT NULL,
                data_json  TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (recipe_id, user_id),
                FOREIGN KEY (recipe_id) REFERENCES recipes(id),
                FOREIGN KEY (user_id)   REFERENCES users(id)
            )
        """)
        conn.commit()
    if "user_action_log" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_action_log (
                id            TEXT PRIMARY KEY,
                user_id       TEXT,
                username      TEXT NOT NULL DEFAULT '',
                action        TEXT NOT NULL,
                recipe_id     TEXT,
                recipe_title  TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at    TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_action_log_created ON user_action_log (created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_action_log_action ON user_action_log (action)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_action_log_user ON user_action_log (user_id, username)")
        conn.commit()
    if "github_releases" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS github_releases (
                id             TEXT PRIMARY KEY,
                github_id      INTEGER NOT NULL UNIQUE,
                tag_name       TEXT NOT NULL DEFAULT '',
                name           TEXT NOT NULL DEFAULT '',
                body           TEXT NOT NULL DEFAULT '',
                html_url       TEXT NOT NULL DEFAULT '',
                prerelease     INTEGER NOT NULL DEFAULT 0,
                draft          INTEGER NOT NULL DEFAULT 0,
                published_at   TEXT NOT NULL DEFAULT '',
                created_at     TEXT NOT NULL DEFAULT '',
                synced_at      TEXT NOT NULL
            )
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_github_releases_tag ON github_releases (tag_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_github_releases_published ON github_releases (published_at DESC)")
        conn.commit()
    if "github_release_reads" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS github_release_reads (
                user_id    TEXT NOT NULL,
                release_id TEXT NOT NULL,
                read_at    TEXT NOT NULL,
                PRIMARY KEY (user_id, release_id)
            )
        """)
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
        CREATE TABLE IF NOT EXISTS recipe_viewer_progress (
            recipe_id             TEXT NOT NULL,
            user_id               TEXT NOT NULL,
            view_mode             TEXT NOT NULL DEFAULT 'original',
            image_index           INTEGER NOT NULL DEFAULT 0,
            zoom                  REAL NOT NULL DEFAULT 1,
            scroll_y              INTEGER NOT NULL DEFAULT 0,
            text_scroll_y         INTEGER NOT NULL DEFAULT 0,
            mobile_images_visible INTEGER NOT NULL DEFAULT 0,
            updated_at            TEXT NOT NULL,
            PRIMARY KEY (recipe_id, user_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id),
            FOREIGN KEY (user_id)   REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS app_navigation_progress (
            user_id    TEXT PRIMARY KEY,
            data_json  TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS recipe_knitting_tools (
            recipe_id  TEXT NOT NULL,
            user_id    TEXT NOT NULL,
            data_json  TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (recipe_id, user_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id),
            FOREIGN KEY (user_id)   REFERENCES users(id)
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
            user_id        TEXT,
            username       TEXT NOT NULL DEFAULT '',
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
        CREATE TABLE IF NOT EXISTS user_action_log (
            id            TEXT PRIMARY KEY,
            user_id       TEXT,
            username      TEXT NOT NULL DEFAULT '',
            action        TEXT NOT NULL,
            recipe_id     TEXT,
            recipe_title  TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS github_releases (
            id             TEXT PRIMARY KEY,
            github_id      INTEGER NOT NULL UNIQUE,
            tag_name       TEXT NOT NULL DEFAULT '',
            name           TEXT NOT NULL DEFAULT '',
            body           TEXT NOT NULL DEFAULT '',
            html_url       TEXT NOT NULL DEFAULT '',
            prerelease     INTEGER NOT NULL DEFAULT 0,
            draft          INTEGER NOT NULL DEFAULT 0,
            published_at   TEXT NOT NULL DEFAULT '',
            created_at     TEXT NOT NULL DEFAULT '',
            synced_at      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS github_release_reads (
            user_id    TEXT NOT NULL,
            release_id TEXT NOT NULL,
            read_at    TEXT NOT NULL,
            PRIMARY KEY (user_id, release_id)
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
        CREATE INDEX IF NOT EXISTS idx_project_sessions_user  ON project_sessions (recipe_id, user_id, finished_at);
        CREATE INDEX IF NOT EXISTS idx_project_feedback_rid   ON project_feedback (recipe_id);
        CREATE INDEX IF NOT EXISTS idx_project_feedback_sid   ON project_feedback (session_id);
        CREATE INDEX IF NOT EXISTS idx_yarns_name             ON yarns (name);
        CREATE INDEX IF NOT EXISTS idx_yarn_colours_yarn_id   ON yarn_colours (yarn_id);
        CREATE INDEX IF NOT EXISTS idx_inventory_items_type   ON inventory_items (type);
        CREATE INDEX IF NOT EXISTS idx_inventory_log_item_id  ON inventory_log (item_id);
        CREATE INDEX IF NOT EXISTS idx_user_action_log_created ON user_action_log (created_at);
        CREATE INDEX IF NOT EXISTS idx_user_action_log_action  ON user_action_log (action);
        CREATE INDEX IF NOT EXISTS idx_user_action_log_user    ON user_action_log (user_id, username);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_github_releases_tag ON github_releases (tag_name);
        CREATE INDEX IF NOT EXISTS idx_github_releases_published ON github_releases (published_at DESC);
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

def _log_user_action(
    conn,
    user: Optional[dict],
    action: str,
    recipe_id: Optional[str] = None,
    recipe_title: str = "",
    metadata: Optional[dict] = None,
) -> None:
    user_id = user.get("id") if user else None
    username = user.get("username", "") if user else ""
    try:
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        metadata_json = "{}"
    conn.execute(
        """
        INSERT INTO user_action_log
            (id, user_id, username, action, recipe_id, recipe_title, metadata_json, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            user_id,
            username or "",
            action,
            recipe_id,
            recipe_title or "",
            metadata_json,
            datetime.utcnow().isoformat(),
        )
    )

def _release_row_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "github_id": row["github_id"],
        "tag_name": row["tag_name"],
        "name": row["name"] or row["tag_name"],
        "title": row["name"] or row["tag_name"],
        "body": row["body"] or "",
        "html_url": row["html_url"] or GITHUB_RELEASES_HTML,
        "prerelease": bool(row["prerelease"]),
        "draft": bool(row["draft"]),
        "published_at": row["published_at"],
        "created_at": row["published_at"] or row["created_at"] or row["synced_at"],
        "synced_at": row["synced_at"],
        "source": "github",
    }

def _release_sync_status(conn) -> dict:
    rows = conn.execute(
        "SELECT key, value FROM app_settings WHERE key IN ('github_releases_last_sync_at','github_releases_last_sync_error')"
    ).fetchall()
    values = {row["key"]: row["value"] for row in rows}
    return {
        "last_sync_at": values.get("github_releases_last_sync_at", ""),
        "last_sync_error": values.get("github_releases_last_sync_error", ""),
        "source_url": GITHUB_RELEASES_HTML,
    }

async def _sync_github_releases() -> dict:
    async with _release_sync_lock:
        now = datetime.utcnow().isoformat()
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                response = await client.get(
                    GITHUB_RELEASES_URL,
                    headers={
                        "Accept": "application/vnd.github+json",
                        "User-Agent": "Knitting-Library",
                    },
                    params={"per_page": 100},
                )
                response.raise_for_status()
                releases = response.json()
            if not isinstance(releases, list):
                raise ValueError("GitHub returned an unexpected release payload")

            conn = get_db()
            inserted = 0
            updated = 0
            try:
                for item in releases:
                    if not isinstance(item, dict):
                        continue
                    github_id = item.get("id")
                    tag_name = str(item.get("tag_name") or "").strip()
                    if not github_id or not tag_name:
                        continue
                    release_id = f"github-{github_id}"
                    existing = conn.execute(
                        "SELECT id FROM github_releases WHERE github_id=? OR tag_name=?",
                        (github_id, tag_name)
                    ).fetchone()
                    if existing:
                        updated += 1
                        conn.execute(
                            """
                            UPDATE github_releases SET
                                github_id=?,
                                tag_name=?,
                                name=?,
                                body=?,
                                html_url=?,
                                prerelease=?,
                                draft=?,
                                published_at=?,
                                created_at=?,
                                synced_at=?
                            WHERE id=?
                            """,
                            (
                                int(github_id),
                                tag_name,
                                str(item.get("name") or tag_name),
                                str(item.get("body") or ""),
                                str(item.get("html_url") or GITHUB_RELEASES_HTML),
                                1 if item.get("prerelease") else 0,
                                1 if item.get("draft") else 0,
                                str(item.get("published_at") or item.get("created_at") or ""),
                                str(item.get("created_at") or ""),
                                now,
                                existing["id"],
                            )
                        )
                    else:
                        inserted += 1
                        conn.execute(
                            """
                            INSERT INTO github_releases
                                (id, github_id, tag_name, name, body, html_url, prerelease, draft, published_at, created_at, synced_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                release_id,
                                int(github_id),
                                tag_name,
                                str(item.get("name") or tag_name),
                                str(item.get("body") or ""),
                                str(item.get("html_url") or GITHUB_RELEASES_HTML),
                                1 if item.get("prerelease") else 0,
                                1 if item.get("draft") else 0,
                                str(item.get("published_at") or item.get("created_at") or ""),
                                str(item.get("created_at") or ""),
                                now,
                            )
                        )
                conn.execute(
                    "INSERT INTO app_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("github_releases_last_sync_at", now)
                )
                conn.execute(
                    "INSERT INTO app_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("github_releases_last_sync_error", "")
                )
                conn.commit()
            finally:
                conn.close()
            return {"ok": True, "inserted": inserted, "updated": updated, "synced_at": now}
        except Exception as e:
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO app_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("github_releases_last_sync_error", str(e))
                )
                conn.commit()
            finally:
                conn.close()
            return {"ok": False, "inserted": 0, "updated": 0, "synced_at": now, "error": str(e)}

async def _release_sync_loop() -> None:
    while True:
        await _sync_github_releases()
        await asyncio.sleep(RELEASE_SYNC_INTERVAL_SECONDS)

def _ensure_release_sync_processor() -> None:
    global _release_sync_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _release_sync_task is None or _release_sync_task.done():
        _release_sync_task = loop.create_task(_release_sync_loop())

# ── Auth middleware ───────────────────────────────────────────────────────────


__all__ = [name for name in globals() if not name.startswith("__")]
