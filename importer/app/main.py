"""The importer's web API and page. Three stages: get the pattern, check it, add it to the library."""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import pipeline
from app.basepath import BasePathMiddleware
from app.config import Settings, load_settings
from app.drafts import Draft, DraftStore
from app.drops.build import NotAPattern
from app.drops.fetcher import DropsFetcher
from app.drops.pdfinfo import render_page_jpeg
from app.drops.urls import BadLink, PatternRef, parse_pattern_link
from app.drops.verify import Expect, verify_html, verify_pdf
from app.kl.client import KLError, KnittingLibrary
from app.kl.textversion import build_text_version
from app.models import CreateDraft, Edits, PatchDraft, PatternData, PublishRequest

log = logging.getLogger("knit-import")
STATIC = Path(__file__).parent / "static"

MAX_LIST = 30
MAX_ITEM = 60


def _clean_list(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        v = " ".join(str(v).replace(",", " ").split())[:MAX_ITEM]
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out[:MAX_LIST]


def create_app(
    settings: Settings | None = None,
    fetcher: DropsFetcher | None = None,
    kl: KnittingLibrary | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    store = DraftStore(settings.data_dir, settings.draft_ttl_hours)
    fetcher = fetcher or DropsFetcher(settings)
    kl = kl or KnittingLibrary(settings)
    svc = pipeline.Services(settings=settings, fetcher=fetcher, kl=kl)
    tasks: dict[str, asyncio.Task] = {}
    suggestion_cache: dict[str, Any] = {"at": 0.0, "data": {"categories": [], "tags": []}}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        removed = await asyncio.to_thread(store.cleanup)
        if removed:
            log.info("Removed %d old drafts", removed)
        yield
        for t in tasks.values():
            t.cancel()

    app = FastAPI(title="Knit Import", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.svc = svc

    # ------------------------------------------------------------------ guards
    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Browsers cannot add a custom header to a cross-site request without our consent,
        # so requiring one on every change stops other websites from driving this app.
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "knit-import":
            return JSONResponse({"detail": "Reload the page and try again."}, status_code=403)
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ------------------------------------------------------------------ helpers
    def get_draft(draft_id: str) -> Draft:
        d = store.get(draft_id)
        if not d:
            raise HTTPException(404, "That pattern is no longer here. Start again from the first step.")
        return d

    def spawn(draft_id: str, coro) -> None:
        task = asyncio.create_task(coro)
        tasks[draft_id] = task
        task.add_done_callback(lambda t, key=draft_id: tasks.pop(key, None) if tasks.get(key) is t else None)

    def running(draft_id: str) -> bool:
        t = tasks.get(draft_id)
        return bool(t and not t.done())

    def settle_stale(draft: Draft, meta: dict) -> dict:
        """A draft marked busy with nothing running means the server restarted. Send it to the manual route."""
        if meta.get("status") == "working" and not running(draft.id):
            for step in meta.get("progress", []):
                if step["state"] == "active":
                    step["state"] = "failed"
            pipeline.go_manual(draft, meta, "interrupted", "The importer was restarted while this was running.")
        pub = meta.get("publish")
        if pub and pub.get("state") == "running" and not running(draft.id):
            pub["state"] = "error"
            pub["error"] = {"message": "The importer was restarted part way through. Press Try again.", "technical": "", "status": None}
            for st in pub["steps"]:
                if st["state"] == "active":
                    st["state"] = "pending"
            draft.save(meta)
        return meta

    def view(draft: Draft, meta: dict) -> dict:
        meta = settle_stale(draft, meta)
        pattern = meta.get("pattern")
        summary = None
        if pattern:
            p = PatternData(**pattern)
            summary = {
                **p.model_dump(exclude={"body", "yarn_raw"}),
                "sections": [{"heading": s.heading, "lines": len(s.lines), "preview": " ".join(s.lines[:2])[:160]} for s in p.body],
            }
        ref = meta.get("ref")
        links = {}
        if ref:
            r = PatternRef(ref["site_id"], ref["cid"])
            links = {"pattern": r.main_url(settings.drops_base)}
        pub = meta.get("publish")
        recipe_url = ""
        if pub and pub.get("recipe_id"):
            recipe_url = f"{settings.public_url}/"
        return {
            "id": draft.id,
            "status": meta.get("status"),
            "mode": meta.get("mode"),
            "url": meta.get("url", ""),
            "progress": meta.get("progress", []),
            "manual": meta.get("manual"),
            "files": meta.get("files", {}),
            "verification": meta.get("verification", {}),
            "pattern": summary,
            "edits": meta.get("edits"),
            "publish": pub,
            "error": meta.get("error"),
            "links": links,
            "library_url": recipe_url,
            "max_upload_mb": settings.max_upload_mb,
        }

    # ------------------------------------------------------------------ status
    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/api/status")
    async def status():
        library = await kl.status()
        return {
            "library": library,
            "library_url": settings.public_url,
            "fetch_enabled": settings.drops_fetch_enabled,
            "renderer": Path(settings.chromium_path).exists(),
        }

    @app.get("/api/suggestions")
    async def suggestions():
        if time.time() - suggestion_cache["at"] > 60:
            suggestion_cache["data"] = await kl.suggestions()
            suggestion_cache["at"] = time.time()
        return suggestion_cache["data"]

    # ------------------------------------------------------------------ drafts
    @app.post("/api/drafts")
    async def create_draft(body: CreateDraft):
        try:
            ref = parse_pattern_link(body.url, settings)
        except BadLink as exc:
            raise HTTPException(422, str(exc)) from exc
        if not settings.drops_fetch_enabled:
            draft = store.create(pipeline.init_manual_meta(body.url, ref, {"code": "disabled", "message": "Fetching from DROPS is switched off on this server."}))
            meta = draft.load()
            meta["status"] = "manual"
            draft.save(meta)
            return view(draft, meta)
        draft = store.create(pipeline.init_auto_meta(body.url, ref, settings))
        spawn(draft.id, pipeline.run_auto(draft, svc))
        return view(draft, draft.load())

    @app.post("/api/drafts/manual")
    async def create_manual_draft():
        draft = store.create(pipeline.init_manual_meta("", None, {"code": "chosen", "message": ""}))
        meta = draft.load()
        meta["status"] = "manual"
        draft.save(meta)
        return view(draft, meta)

    @app.get("/api/drafts/{draft_id}")
    async def read_draft(draft_id: str):
        d = get_draft(draft_id)
        return view(d, d.load())

    @app.delete("/api/drafts/{draft_id}")
    async def delete_draft(draft_id: str):
        t = tasks.pop(draft_id, None)
        if t:
            t.cancel()
        store.delete(draft_id)
        return {"ok": True}

    @app.post("/api/drafts/{draft_id}/retry")
    async def retry_auto(draft_id: str):
        """Try the link route again (for example after a temporary block)."""
        d = get_draft(draft_id)
        meta = d.load()
        if running(draft_id) or meta.get("status") == "working":
            raise HTTPException(409, "Still working on it.")
        if not meta.get("ref") or not meta.get("url"):
            raise HTTPException(409, "There is no link to try again.")
        if meta.get("publish") and meta["publish"].get("state") in ("running", "done"):
            raise HTTPException(409, "This pattern has already been added.")
        ref = PatternRef(meta["ref"]["site_id"], meta["ref"]["cid"])
        fresh = pipeline.init_auto_meta(meta["url"], ref, settings)
        meta.update({k: fresh[k] for k in ("mode", "progress", "manual", "files", "verification", "pattern", "edits", "publish")})
        meta["status"] = "working"
        meta.pop("error", None)
        for f in (d.main_html, d.print_html, d.pdf):
            f.unlink(missing_ok=True)
        shutil.rmtree(d.dir / "previews", ignore_errors=True)
        d.save(meta)
        spawn(d.id, pipeline.run_auto(d, svc))
        return view(d, d.load())

    # ------------------------------------------------------------------ manual files
    def expectation(meta: dict) -> Expect:
        ver = meta.get("verification", {})
        number = (ver.get("pdf") or {}).get("number") or (ver.get("main_html") or {}).get("number") or ""
        site_id = (ver.get("main_html") or {}).get("site_id") or (meta.get("ref") or {}).get("site_id")
        return Expect(number=number, site_id=site_id)

    @app.post("/api/drafts/{draft_id}/files")
    async def add_files(draft_id: str, files: list[UploadFile] = File(...)):
        d = get_draft(draft_id)
        meta = d.load()
        if running(draft_id) or meta.get("status") == "working":
            raise HTTPException(409, "Still working on it. Wait a moment.")
        if meta.get("publish") and meta["publish"].get("state") in ("running", "done"):
            raise HTTPException(409, "This pattern has already been added.")
        if len(files) > 6:
            raise HTTPException(422, "Drop one or two files at a time.")

        limit = settings.max_upload_mb * 1_000_000
        loaded: list[tuple[str, bytes]] = []
        for up in files:
            data = await up.read(limit + 1)
            name = (up.filename or "file").rsplit("/", 1)[-1][:120]
            if len(data) > limit:
                loaded.append((name, b""))  # reported below as too big
                continue
            loaded.append((name, data))
        # PDFs first, so the page file can be matched against it.
        loaded.sort(key=lambda item: 0 if item[1][:5] == b"%PDF-" else 1)

        accepted: list[dict] = []
        rejected: list[dict] = []
        for name, data in loaded:
            if not data:
                rejected.append({"filename": name, "verdict": {
                    "kind": "unknown", "ok": False, "headline": "That file is too big or empty",
                    "checks": [], "advice": f"Files up to {settings.max_upload_mb} MB are accepted. A DROPS pattern is normally under 1 MB.",
                    "title": "", "number": "", "site_id": None, "page_count": 0}})
                continue
            expect = expectation(meta)
            if data[:5] == b"%PDF-":
                tmp = d.dir / "upload.pdf"
                tmp.write_bytes(data)
                verdict = await asyncio.to_thread(verify_pdf, tmp, settings.max_upload_mb, expect)
                if verdict.ok:
                    tmp.replace(d.pdf)
                else:
                    tmp.unlink(missing_ok=True)
            else:
                verdict = await asyncio.to_thread(verify_html, data.decode("utf-8", errors="replace"), expect)
                if verdict.ok and verdict.kind == "main_html":
                    d.main_html.write_bytes(data)
            rec = verdict.as_dict()
            if verdict.ok:
                rec["filename"] = name
                meta.setdefault("verification", {})[verdict.kind] = rec
                accepted.append({"filename": name, "verdict": rec})
            else:
                rejected.append({"filename": name, "verdict": rec})

        problem = ""
        if accepted:
            try:
                if d.pdf.exists():
                    await asyncio.to_thread(pipeline.rebuild_pattern, d, meta, settings)
                meta["files"] = {"main_html": d.main_html.exists(), "print_html": d.print_html.exists(), "pdf": d.pdf.exists()}
                if meta.get("status") != "ready":
                    meta["status"] = "manual"
            except NotAPattern as exc:
                problem = str(exc)
                d.pdf.unlink(missing_ok=True)
                meta.get("verification", {}).pop("pdf", None)
                meta["status"] = "manual"
            d.save(meta)
        out = view(d, d.load())
        out["accepted"] = accepted
        out["rejected"] = rejected
        out["problem"] = problem
        return out

    # ------------------------------------------------------------------ check stage
    @app.patch("/api/drafts/{draft_id}")
    async def edit_draft(draft_id: str, body: PatchDraft):
        d = get_draft(draft_id)
        meta = d.load()
        if not meta.get("edits"):
            raise HTTPException(409, "There is nothing to edit yet.")
        if meta.get("publish") and meta["publish"].get("state") in ("running", "done"):
            raise HTTPException(409, "This pattern has already been added.")
        e = Edits(**meta["edits"])
        if body.title is not None:
            e.title = " ".join(body.title.split())[:200]
        if body.description is not None:
            e.description = body.description.strip()[:2000]
        if body.categories is not None:
            e.categories = _clean_list(body.categories)
        if body.tags is not None:
            e.tags = _clean_list(body.tags)
        if body.cover_page is not None:
            pages = (meta.get("pattern") or {}).get("page_count") or 1
            e.cover_page = min(max(1, body.cover_page), max(1, pages))
        meta["edits"] = e.model_dump()
        d.save(meta)
        return view(d, meta)

    @app.get("/api/drafts/{draft_id}/pdf")
    async def draft_pdf(draft_id: str):
        d = get_draft(draft_id)
        if not d.pdf.exists():
            raise HTTPException(404, "There is no PDF yet.")
        return FileResponse(d.pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="pattern.pdf"'})

    @app.get("/api/drafts/{draft_id}/pages/{page}.jpg")
    async def draft_page(draft_id: str, page: int):
        d = get_draft(draft_id)
        meta = d.load()
        count = (meta.get("pattern") or {}).get("page_count") or 0
        if not d.pdf.exists() or not 1 <= page <= count:
            raise HTTPException(404, "No such page.")
        out = d.previews_dir() / f"p{page}.jpg"
        if not out.exists():
            ok = await asyncio.to_thread(render_page_jpeg, d.pdf, page, out)
            if not ok:
                raise HTTPException(500, "Could not draw that page.")
        return FileResponse(out, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/api/drafts/{draft_id}/text")
    async def draft_text(draft_id: str):
        d = get_draft(draft_id)
        meta = d.load()
        if not meta.get("pattern"):
            raise HTTPException(404, "Nothing has been read yet.")
        md = build_text_version(PatternData(**meta["pattern"]), recipe_id=None)
        return {"markdown": md}

    # ------------------------------------------------------------------ add stage
    @app.post("/api/drafts/{draft_id}/publish")
    async def publish(draft_id: str, body: PublishRequest | None = None):
        d = get_draft(draft_id)
        meta = d.load()
        if running(draft_id):
            raise HTTPException(409, "Already adding this pattern.")
        if not (meta.get("pattern") and meta.get("edits") and d.pdf.exists()):
            raise HTTPException(409, "The pattern is not ready to add yet.")
        if (meta.get("publish") or {}).get("state") == "done":
            raise HTTPException(409, "This pattern has already been added.")
        edits = Edits(**meta["edits"])
        if not (edits.title.strip() or meta["pattern"].get("title")):
            raise HTTPException(422, "Give the pattern a title first.")
        spawn(d.id, pipeline.run_publish(d, svc, bool(body and body.allow_duplicate)))
        await asyncio.sleep(0)
        return view(d, d.load())

    # ------------------------------------------------------------------ page
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    app.add_middleware(BasePathMiddleware, base_path=settings.base_path)  # added last, so it runs first
    return app


def app_factory() -> FastAPI:  # for `uvicorn app.main:app_factory --factory`
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return create_app()
