"""GitHub release listing, dismissal, and manual sync endpoints."""
from app.core.foundation import *
from app.auth.service import get_current_user, require_admin, _verify_token_param

def list_github_releases(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM github_releases
        WHERE draft=0
        ORDER BY COALESCE(NULLIF(published_at, ''), created_at, synced_at) DESC
        LIMIT 100
        """
    ).fetchall()
    status = _release_sync_status(conn)
    conn.close()
    return {"items": [_release_row_dict(row) for row in rows], **status}


def latest_github_release(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        """
        SELECT * FROM github_releases
        WHERE draft=0
        ORDER BY COALESCE(NULLIF(published_at, ''), created_at, synced_at) DESC
        LIMIT 1
        """
    ).fetchone()
    status = _release_sync_status(conn)
    conn.close()
    return {"release": _release_row_dict(row) if row else None, **status}


def pending_github_releases(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT r.* FROM github_releases r
        WHERE r.draft=0
          AND r.id NOT IN (
              SELECT release_id FROM github_release_reads WHERE user_id=?
          )
        ORDER BY COALESCE(NULLIF(r.published_at, ''), r.created_at, r.synced_at) DESC
        LIMIT 10
        """,
        (current_user["id"],)
    ).fetchall()
    conn.close()
    return [_release_row_dict(row) for row in rows]


def dismiss_github_release(release_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM github_releases WHERE id=?", (release_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Release not found")
    conn.execute(
        "INSERT OR IGNORE INTO github_release_reads (user_id, release_id, read_at) VALUES (?,?,?)",
        (current_user["id"], release_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return {"ok": True}


async def sync_releases_now(admin: dict = Depends(require_admin)):
    return await _sync_github_releases()


# ── Legacy announcements ──────────────────────────────────────────────────────


__all__ = [name for name in globals() if not name.startswith("__")]
