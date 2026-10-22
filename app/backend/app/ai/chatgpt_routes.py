"""Connection setup and status never expose OAuth credentials to the browser."""
import asyncio
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from app.auth.service import require_admin
from app.ai import chatgpt_connection as connection
from app.ai.chatgpt_protocol import ChatGPTError

router = APIRouter(prefix="/api/admin/ai/chatgpt")
HELPER = Path(__file__).resolve().parents[2] / "assets" / "KnittingLibrary-ChatGPT.exe"


async def _call(func, *args):
    try:
        return await asyncio.to_thread(func, *args)
    except ChatGPTError as exc:
        raise HTTPException(status_code=400, detail=exc.code) from None


@router.get("")
async def get_connection(admin: dict = Depends(require_admin)):
    result = await _call(connection.status)
    if HELPER.is_file():
        result["helper_sha256"] = hashlib.sha256(HELPER.read_bytes()).hexdigest()
    result["helper_available"] = HELPER.is_file()
    return result


@router.post("/setup")
async def begin_setup(admin: dict = Depends(require_admin)):
    return await _call(connection.begin_setup, admin)


@router.get("/helper")
async def download_helper(admin: dict = Depends(require_admin)):
    if not HELPER.is_file():
        raise HTTPException(status_code=503, detail="helper_unavailable")
    return FileResponse(HELPER, filename=HELPER.name, media_type="application/octet-stream",
                        headers={"Cache-Control": "no-store"})


@router.post("/import")
async def import_connection(file: UploadFile = File(...), admin: dict = Depends(require_admin)):
    raw = await file.read(65537)
    if len(raw) > 65536:
        raise HTTPException(status_code=413, detail="invalid_connection_file")
    try:
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise HTTPException(status_code=400, detail="invalid_connection_file") from None
    return await _call(connection.import_connection, envelope, admin)


@router.post("/models")
async def models(admin: dict = Depends(require_admin)):
    return await _call(connection.refresh_models)


@router.get("/prompt")
async def prompt_preview(language: str = "en", admin: dict = Depends(require_admin)):
    from app.ai.transcription import formatted_prompt
    return {"prompt": formatted_prompt(language)}


@router.delete("")
async def disconnect(admin: dict = Depends(require_admin)):
    return await _call(connection.disconnect)


@router.get("/jobs/{job_id}/diagnostics")
async def diagnostics(job_id: str, admin: dict = Depends(require_admin)):
    from app.core.foundation import get_db
    conn = get_db()
    try:
        job = conn.execute("SELECT id,provider,duration_seconds,provider_usage_json FROM ai_text_jobs WHERE id=?", (job_id,)).fetchone()
        if not job or job["provider"] != "chatgpt_subscription":
            raise HTTPException(status_code=404, detail="Job not found")
        requests = [dict(row) for row in conn.execute("SELECT * FROM ai_request_metrics WHERE job_id=? ORDER BY created_at,id", (job_id,))]
        for item in requests:
            item["settings"] = json.loads(item.pop("settings_json"))
        return {"job_id": job_id, "duration_seconds": job["duration_seconds"],
                "usage": json.loads(job["provider_usage_json"] or "{}"), "requests": requests}
    finally:
        conn.close()
