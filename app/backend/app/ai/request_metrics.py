"""Content-free per-attempt inference diagnostics and transactional accounting."""
import json
import time
import uuid
from datetime import datetime, timezone
from app.core import foundation


def start(job_id, page_order, stage, model, settings, preparation_seconds):
    attempt = str(uuid.uuid4())
    conn = foundation.get_db()
    try:
        conn.execute("INSERT INTO ai_request_metrics (id,job_id,page_order,stage,model,settings_json,preparation_seconds,outcome,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (attempt, job_id, page_order, stage, model, json.dumps(settings, sort_keys=True), preparation_seconds,
                      "running", datetime.now(timezone.utc).isoformat()))
        conn.execute("UPDATE ai_text_jobs SET provider_usage_json=? WHERE id=?",
                     (json.dumps({key: None for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens", "cached_tokens")}), job_id))
        conn.commit()
    finally:
        conn.close()
    return attempt, time.monotonic()


def finish(attempt, started, result=None, error=None):
    result = result or {}
    usage = result.get("usage") or {}
    details = result.get("token_details") or {}
    metrics = result.get("metrics") or getattr(error, "metrics", {}) or {}
    outcome = "completed" if error is None else getattr(error, "code", "provider_error")
    conn = foundation.get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE ai_request_metrics SET outcome=?, first_text_seconds=?, duration_seconds=?, prompt_tokens=?, completion_tokens=?, total_tokens=?, reasoning_tokens=?, cached_tokens=? WHERE id=?",
            (outcome, metrics.get("first_text_seconds"), time.monotonic() - started,
             usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens"),
             details.get("reasoning_tokens"), details.get("cached_tokens"), attempt))
        job_id = conn.execute("SELECT job_id FROM ai_request_metrics WHERE id=?", (attempt,)).fetchone()[0]
        rows = conn.execute("SELECT * FROM ai_request_metrics WHERE job_id=?", (job_id,)).fetchall()
        totals = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens", "cached_tokens"):
            values = [row[key] for row in rows]
            totals[key] = sum(values) if all(value is not None for value in values) else None
        conn.execute("UPDATE ai_text_jobs SET provider_usage_json=? WHERE id=?", (json.dumps(totals), job_id))
        conn.commit()
    finally:
        conn.close()
