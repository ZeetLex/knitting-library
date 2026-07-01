"""AI settings, generation, audit, queue, and work-queue endpoints."""
from app.core.foundation import *
from app.auth.service import get_current_user, require_admin, _verify_token_param
from app.ai.prompts import *
from app.ai.ocr import *

def _ai_settings(conn, reveal_secret: bool = False) -> dict:
    rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'ai_%'").fetchall()
    cfg = {r["key"]: r["value"] for r in rows}
    defaults = {
        "ai_enabled": "false",
        "ai_provider": "openai_compatible",
        "ai_base_url": "http://host.docker.internal:11434/v1",
        "ai_model": "",
        "ai_api_key": "",
        "ai_timeout": "600",
        "ai_max_pages": "8",
        "ai_max_output_tokens": str(AI_MAX_OUTPUT_TOKENS),
        "ai_scan_temperature": "0.02",
        "ai_cleanup_temperature": "0.05",
        "ai_prompt_mode": "default",
        "ai_custom_prompt": "",
        "ai_cleanup_enabled": "false",
        "ai_cleanup_custom_prompt": "",
    }
    defaults.update(cfg)
    if defaults.get("ai_api_key") and not reveal_secret:
        defaults["ai_api_key"] = "••••••••"
    return defaults



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


def _image_payload_for_path(path: Path) -> dict:
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    mime = "image/png" if path.suffix.lower() == ".png" else "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{data}"},
    }


def _ai_scan_prompt(language: str, cfg: dict) -> str:
    return cfg.get("ai_custom_prompt", "").strip() if cfg.get("ai_prompt_mode") == "custom" else _default_ai_scan_prompt(language)


def _ai_cleanup_prompt(language: str, cfg: dict) -> str:
    return (cfg.get("ai_cleanup_custom_prompt") or "").strip() or _default_ai_cleanup_prompt(language)


def _require_ai_vision_config(cfg: dict) -> tuple[str, str]:
    base_url = cfg.get("ai_base_url", "").rstrip("/")
    model = cfg.get("ai_model", "").strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="AI base URL and model are required")
    return base_url, model


def _ai_max_output_tokens(cfg: dict) -> int:
    return int(_clamped_float(cfg.get("ai_max_output_tokens"), AI_MAX_OUTPUT_TOKENS, 64, 131072))


def _ai_temperature(cfg: dict, key: str, default: float) -> float:
    return round(_clamped_float(cfg.get(key), default, 0, 2), 3)


async def _call_ai_vision_page_scan(path: Path, page_no: int, page_count: int, language: str, cfg: dict, timeout: int) -> tuple[str, dict, str]:
    base_url, model = _require_ai_vision_config(cfg)
    prompt = _ai_scan_prompt(language, cfg)
    messages = [{
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": (
                    f"{prompt}\n\n"
                    f"Page {page_no}/{page_count}. Transcribe only this image. Return only the text."
                ),
            },
            _image_payload_for_path(path),
        ],
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
                "temperature": _ai_temperature(cfg, "ai_scan_temperature", 0.02),
                "stream": False,
                "max_tokens": _ai_max_output_tokens(cfg),
            },
        )
        res.raise_for_status()
        data = res.json()
    return _clean_ai_transcription(data["choices"][0]["message"]["content"]), data.get("usage") or {}, prompt


async def _call_ai_page_cleanup(text: str, page_no: int, page_count: int, language: str, cfg: dict, timeout: int) -> tuple[str, dict, str]:
    base_url, model = _require_ai_vision_config(cfg)
    prompt = _ai_cleanup_prompt(language, cfg)
    messages = [{
        "role": "user",
        "content": f"{prompt}\n\nPage {page_no}/{page_count} raw text:\n\n{text}",
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
                "temperature": _ai_temperature(cfg, "ai_cleanup_temperature", 0.05),
                "stream": False,
                "max_tokens": _ai_max_output_tokens(cfg),
            },
        )
        res.raise_for_status()
        data = res.json()
    return _clean_ai_transcription(data["choices"][0]["message"]["content"]), data.get("usage") or {}, prompt


async def _scan_recipe_pages_with_ai(
    recipe_id: str,
    language: str,
    cfg: dict,
    conn,
    max_pages: int,
    timeout: int,
    job_id: str = "",
) -> tuple[list[dict], dict, str]:
    paths = _collect_recipe_image_paths(recipe_id, conn, max_pages)
    page_count = len(paths)
    usage_totals: dict[str, int] = {}
    prompt = _ai_scan_prompt(language, cfg)
    cleanup_enabled = _is_truthy(cfg.get("ai_cleanup_enabled"), False)
    cleanup_prompt = _ai_cleanup_prompt(language, cfg) if cleanup_enabled else ""
    results: list[dict] = []

    def add_usage(usage: dict, prefix: str = "") -> None:
        for key, value in (usage or {}).items():
            if isinstance(value, (int, float)):
                usage_totals[f"{prefix}{key}"] = usage_totals.get(f"{prefix}{key}", 0) + int(value)

    for idx, path in enumerate(paths, start=1):
        if job_id:
            _update_ai_job(job_id, pages_sent=idx - 1, progress_stage=f"ai_scan_page_{idx}_of_{page_count}")
        text, usage, _prompt = await _call_ai_vision_page_scan(path, idx, page_count, language, cfg, timeout)
        add_usage(usage)
        source_text = text.strip() or "_No useful text was detected on this page._"
        reviewed_text = _clean_ai_transcription(text) or source_text
        results.append({
            "page_order": idx,
            "page_key": path.name,
            "source_text": source_text,
            "reviewed_text": reviewed_text,
            "path": path,
        })
        if job_id:
            _update_ai_job(job_id, pages_sent=idx, progress_stage=f"ai_scanned_{idx}_of_{page_count}")

    if cleanup_enabled:
        for idx, page in enumerate(results, start=1):
            reviewed_text = _clean_ai_transcription(page["reviewed_text"])
            if not reviewed_text.strip():
                continue
            if job_id:
                _update_ai_job(job_id, pages_sent=page_count, progress_stage=f"ai_cleanup_page_{idx}_of_{page_count}")
            try:
                cleaned, cleanup_usage, _cleanup_prompt = await _call_ai_page_cleanup(reviewed_text, idx, page_count, language, cfg, timeout)
                add_usage(cleanup_usage, "cleanup_")
                if cleaned.strip():
                    page["reviewed_text"] = cleaned.strip()
            except Exception:
                pass
        if job_id:
            _update_ai_job(job_id, pages_sent=page_count, progress_stage=f"ai_cleanup_done_{page_count}_of_{page_count}")

    workflow_prompt = prompt if not cleanup_enabled else f"{prompt}\n\n--- Cleanup prompt ---\n\n{cleanup_prompt}"
    return sorted(results, key=lambda page: page["page_order"]), usage_totals, workflow_prompt



async def _generate_text_content(recipe_id: str, language: str, cfg: dict, conn, timeout: int, max_pages: int, job_id: str = "") -> dict:
    _require_ai_vision_config(cfg)
    if job_id:
        _update_ai_job(job_id, progress_stage="ai_pages", pages_sent=0)
    pages, usage, prompt = await _scan_recipe_pages_with_ai(recipe_id, language, cfg, conn, max_pages, timeout, job_id)
    content = "\n\n".join(page["reviewed_text"] for page in pages if page.get("reviewed_text")).strip()
    image_paths = [page["path"] for page in pages]
    estimated_image_tokens = _estimate_image_tokens(image_paths)
    return {
        "content": content,
        "usage": usage,
        "pages_sent": len(pages),
        "provider": cfg.get("ai_provider", "openai_compatible"),
        "model": cfg.get("ai_model", "").strip(),
        "prompt": prompt,
        "workflow": "AI vision page scan",
        "engine": "ai_vision",
        "steps": ["load pages", "AI vision page scan"],
        "warnings": ["Provider token totals may exclude or approximate image tokens."],
        "estimated_input_tokens": estimated_image_tokens + _estimate_text_tokens(prompt) * max(1, len(pages)),
        "estimated_image_tokens": estimated_image_tokens,
        "token_report_note": "Provider-reported token totals may not match billing when image inputs are used.",
        "ocr_text": content,
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
    if not base_url or not model:
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
        base_url = cfg.get("ai_base_url", "").rstrip("/")
        model = cfg.get("ai_model", "").strip()
        provider = cfg.get("ai_provider", "openai_compatible")
        display_model = model
        _update_ai_job(job_id, provider=provider, model=display_model)
        if not base_url or not model:
            raise HTTPException(status_code=400, detail="AI base URL and model are required")
        timeout = int(_clamped_float(cfg.get("ai_timeout"), 600, 60, 1800))
        timeout = max(300, timeout)
        try:
            result = await _create_review_session_from_ai_pages(recipe_id, language, cfg, row["generated_by"], job_id=job_id)
        finally:
            conn.close()
        content = "\n\n".join((page.get("reviewed_text") or page.get("ocr_text") or "") for page in result.get("pages", []))
        usage = {}
        pages_sent = result.get("page_count") or len(result.get("pages", []))
        provider = cfg.get("ai_provider", "openai_compatible")
        model = cfg.get("ai_model", "").strip()
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


async def _resume_ai_queue_on_startup():
    _ensure_ai_queue_processor()
    _ensure_release_sync_processor()

# ── Health ────────────────────────────────────────────────────────────────────


async def generate_recipe_text_version(recipe_id: str, data: dict = Body(default={}), current_user: dict = Depends(get_current_user)):
    language = str(data.get("language", "") or current_user.get("language", "en"))
    return await _generate_text_version(recipe_id, language, current_user)


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
            cfg.get("ai_provider", "openai_compatible"),
            cfg.get("ai_model", ""),
            current_user["username"],
            now,
        )
    )
    conn.commit()
    row = conn.execute("SELECT * FROM ai_text_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    _ensure_ai_queue_processor()
    return {"job": _job_dict(row)}



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



__all__ = [name for name in globals() if not name.startswith("__")]
