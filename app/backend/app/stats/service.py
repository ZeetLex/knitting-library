"""Application and AI usage statistics endpoints."""
from app.core.foundation import *
from app.auth.service import get_current_user, require_admin, _verify_token_param

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
    active_user_rows = conn.execute("""
        SELECT
            COALESCE(NULLIF(username, ''), 'Unknown user') as username,
            user_id,
            COUNT(*) as action_count,
            SUM(CASE WHEN action='project_started' THEN 1 ELSE 0 END) as projects_started,
            SUM(CASE WHEN action='project_finished' THEN 1 ELSE 0 END) as projects_finished,
            SUM(CASE WHEN action='recipe_added' THEN 1 ELSE 0 END) as recipes_added
        FROM user_action_log
        WHERE action IN ('project_started', 'project_finished', 'recipe_added')
        GROUP BY COALESCE(NULLIF(username, ''), 'Unknown user'), user_id
        ORDER BY action_count DESC, username ASC
        LIMIT 5
    """).fetchall()
    most_active_users = [dict(row) for row in active_user_rows]
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
        "most_active_users": most_active_users,
        "ai": ai,
    }



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


__all__ = [name for name in globals() if not name.startswith("__")]
