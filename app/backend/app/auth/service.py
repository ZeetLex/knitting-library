"""Authentication endpoints and account security workflows."""
from app.core.foundation import *

def setup_status():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return {"setup_required": count == 0}


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


def get_me(current_user: dict = Depends(get_current_user)):
    return _user_dict(current_user)


def get_navigation_progress(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT data_json, updated_at FROM app_navigation_progress WHERE user_id=?",
        (current_user["id"],)
    ).fetchone()
    conn.close()
    if not row:
        return {"exists": False}
    try:
        data = json.loads(row["data_json"] or "{}")
    except json.JSONDecodeError:
        data = {}
    return {"exists": True, "updatedAt": row["updated_at"], **data}


def save_navigation_progress(data: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    allowed_views = {"home", "recipes", "inventory", "yarnDatabase", "settings", "stats", "help"}
    active_view = str(data.get("activeView") or data.get("active_view") or "home")
    if active_view not in allowed_views:
        active_view = "home"
    payload = {
        "activeView": active_view,
        "recipeId": str(data.get("recipeId") or "")[:160],
        "initialViewMode": str(data.get("initialViewMode") or data.get("initial_view_mode") or "original")[:40],
        "yarnId": str(data.get("yarnId") or "")[:160],
        "updatedAt": datetime.utcnow().isoformat(),
    }
    now = payload["updatedAt"]
    conn = get_db()
    conn.execute(
        """
        INSERT INTO app_navigation_progress (user_id,data_json,updated_at)
        VALUES (?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            data_json=excluded.data_json,
            updated_at=excluded.updated_at
        """,
        (current_user["id"], json.dumps(payload), now)
    )
    conn.commit()
    conn.close()
    return {"exists": True, **payload}


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
    if background not in ("floral", "default", "realistic", "plain-white", "cotton", "soft-paper", "warm-linen"):
        raise HTTPException(status_code=400, detail="Invalid background")
    conn = get_db()
    conn.execute(
        "UPDATE users SET theme=?, language=?, currency=?, colour_theme=?, background=? WHERE id=?",
        (theme, language, currency, colour_theme, background, current_user["id"])
    )
    conn.commit()
    conn.close()
    return {"theme": theme, "language": language, "currency": currency, "colour_theme": colour_theme, "background": background}


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
    _log_user_action(conn, current_user, "password_updated", metadata={"method": "self_change"})
    conn.commit()
    conn.close()
    return {"message": "Password changed"}


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
    _log_user_action(
        conn,
        dict(user),
        "password_updated",
        metadata={"method": "forgot_password"},
    )
    conn.commit()
    conn.close()
    return _GENERIC


# ── Admin: user management ────────────────────────────────────────────────────


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

# ── GitHub release notes ──────────────────────────────────────────────────────


__all__ = [name for name in globals() if not name.startswith("__")]
