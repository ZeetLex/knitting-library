"""Admin users, logs, mail, AI settings, 2FA administration, and announcements."""
from app.core.foundation import *
from app.auth.service import get_current_user, require_admin, _verify_token_param

def list_users(admin: dict = Depends(require_admin)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, email, is_admin, theme, language, created_date FROM users ORDER BY created_date"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM users    WHERE id=?",      (user_id,))
    conn.commit()
    conn.close()
    return {"message": "User deleted"}


def reset_password(user_id: str, data: dict, admin: dict = Depends(require_admin)):
    new_pw = data.get("new_password", "")
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    conn = get_db()
    user = conn.execute("SELECT id, username FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash_password(new_pw), user_id))
    _log_user_action(
        conn,
        dict(user),
        "password_updated",
        metadata={"method": "admin_reset", "admin_id": admin["id"], "admin_username": admin["username"]},
    )
    conn.commit()
    conn.close()
    return {"message": "Password reset"}

# ── Shared helpers ────────────────────────────────────────────────────────────



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

def _user_action_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    try:
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
    except Exception:
        data["metadata"] = {}
    return data

def _user_action_log_lines(limit: int) -> list[str]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, user_id, username, action, recipe_id, recipe_title, metadata_json, created_at
        FROM user_action_log
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    conn.close()
    result = []
    for row in reversed(rows):
        bits = [
            f"{row['created_at']} USER_ACTION",
            f"action={row['action']}",
            f"user={row['username'] or row['user_id'] or 'unknown'}",
        ]
        if row["recipe_title"] or row["recipe_id"]:
            bits.append(f"recipe={row['recipe_title'] or row['recipe_id']}")
        result.append(" ".join(str(bit) for bit in bits))
    return result

def get_user_actions(
    limit: int = 200,
    action: str = "",
    user: str = "",
    admin: dict = Depends(require_admin),
):
    limit = max(10, min(limit, 1000))
    query = """
        SELECT id, user_id, username, action, recipe_id, recipe_title, metadata_json, created_at
        FROM user_action_log
        WHERE 1=1
    """
    params: list = []
    if action:
        query += " AND action=?"
        params.append(action)
    if user:
        like = f"%{user.strip()}%"
        query += " AND (username LIKE ? OR user_id LIKE ?)"
        params.extend([like, like])
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    conn = get_db()
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    return {"items": [_user_action_dict(row) for row in rows], "count": len(rows)}

def get_logs(lines: int = 200, source: str = "all", admin: dict = Depends(require_admin)):
    """Return the last N lines from the persistent log files in /logs/.
    source: 'all' | 'uvicorn' | 'supervisord' | 'auth' | 'ai' | 'user_actions'
    """
    lines = max(10, min(lines, 1000))

    log_files = {
        "uvicorn":     Path("/logs/uvicorn.log"),
        "supervisord": Path("/logs/supervisord.log"),
        "auth":        Path("/logs/auth.log"),
    }

    sources = [*log_files.keys(), "ai", "user_actions"] if source == "all" else [source]
    collected = []

    for src in sources:
        if src == "ai":
            for line in _ai_log_lines(lines):
                collected.append(f"[ai] {line}")
            continue
        if src == "user_actions":
            for line in _user_action_log_lines(lines):
                collected.append(f"[user_actions] {line}")
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

def get_mail_settings(admin: dict = Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'mail_%'").fetchall()
    conn.close()
    settings = {r["key"]: r["value"] for r in rows}
    # Never return the password in plaintext — return a mask if set
    if settings.get("mail_password"):
        settings["mail_password"] = "••••••••"
    return settings


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

def get_ai_settings(admin: dict = Depends(require_admin)):
    conn = get_db()
    settings = _ai_settings(conn)
    conn.close()
    return settings


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

# ── Admin: 2FA management ─────────────────────────────────────────────────────

def get_2fa_status(admin: dict = Depends(require_admin)):
    """Return 2FA status for every user."""
    conn = get_db()
    users = conn.execute(
        "SELECT id, username, totp_enabled FROM users ORDER BY created_date"
    ).fetchall()
    conn.close()
    return [{"id": u["id"], "username": u["username"], "totp_enabled": bool(u["totp_enabled"])} for u in users]


def admin_reset_2fa(user_id: str, admin: dict = Depends(require_admin)):
    """Admin resets a user's 2FA — they will need to set it up again."""
    conn = get_db()
    conn.execute("UPDATE users SET totp_secret=NULL, totp_enabled=0 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"message": "2FA reset"}

# ── User: 2FA setup ───────────────────────────────────────────────────────────


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


def list_announcements(admin: dict = Depends(require_admin)):
    """List all announcements, newest first."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM announcements ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


__all__ = [name for name in globals() if not name.startswith("__")]
