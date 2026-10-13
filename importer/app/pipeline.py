"""The work behind the three stages.

Stage 1  Get the pattern   fetch the pages and make the PDF, or take files Mary saved by hand
Stage 2  Check             read the pattern, suggest title, categories and tags
Stage 3  Add               send it all to Knitting Library
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.drafts import Draft
from app.drops.build import NotAPattern, build_pattern
from app.drops.fetcher import DropsFetcher, FetchBlocked, PatternNotFound
from app.drops.render import RendererUnavailable, html_to_pdf, make_self_contained
from app.drops.urls import PatternRef
from app.kl.client import KLError, KnittingLibrary
from app.kl.textversion import build_text_version
from app.models import Edits, PatternData

log = logging.getLogger("knit-import")

AUTO_STEPS = [
    ("page", "Reading the pattern page"),
    ("print", "Reading the print view"),
    ("pdf", "Making the PDF"),
    ("read", "Reading the pattern"),
]
PUBLISH_STEPS = [
    ("check", "Checking your library"),
    ("recipe", "Adding the pattern and PDF"),
    ("text", "Saving the instructions as text"),
    ("cover", "Choosing the cover picture"),
    ("yarn", "Adding the yarns to your yarn list"),
]


@dataclass
class Services:
    settings: Settings
    fetcher: DropsFetcher
    kl: KnittingLibrary


def _steps(spec: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"key": k, "label": label, "state": "pending", "detail": ""} for k, label in spec]


def init_auto_meta(url: str, ref: PatternRef, settings: Settings) -> dict[str, Any]:
    return {
        "mode": "auto",
        "url": url,
        "ref": {"site_id": ref.site_id, "cid": ref.cid},
        "progress": _steps(AUTO_STEPS),
        "manual": None,
        "files": {"main_html": False, "print_html": False, "pdf": False},
        "verification": {},
        "pattern": None,
        "edits": None,
        "publish": None,
    }


def init_manual_meta(url: str, ref: PatternRef | None, reason: dict | None) -> dict[str, Any]:
    return {
        "mode": "manual",
        "url": url,
        "ref": {"site_id": ref.site_id, "cid": ref.cid} if ref else None,
        "progress": [],
        "manual": reason or {"code": "chosen", "message": ""},
        "files": {"main_html": False, "print_html": False, "pdf": False},
        "verification": {},
        "pattern": None,
        "edits": None,
        "publish": None,
    }


def _set_step(meta: dict, key: str, state: str, detail: str = "") -> None:
    for step in meta["progress"]:
        if step["key"] == key:
            step["state"] = state
            step["detail"] = detail


def go_manual(draft: Draft, meta: dict, code: str, message: str, technical: str = "") -> None:
    meta["status"] = "manual"
    meta["mode"] = "manual"
    meta["manual"] = {"code": code, "message": message, "technical": technical}
    draft.save(meta)


def rebuild_pattern(draft: Draft, meta: dict, settings: Settings) -> None:
    """(Re)build the pattern from whatever files the draft has. Needs the PDF at least."""
    ref = meta.get("ref")
    ref_obj = PatternRef(ref["site_id"], ref["cid"]) if ref else None
    main_html = draft.main_html.read_text(encoding="utf-8") if draft.main_html.exists() else None
    print_html = draft.print_html.read_text(encoding="utf-8") if draft.print_html.exists() else None
    pdf = draft.pdf if draft.pdf.exists() else None
    if not pdf:
        return
    previous = meta.get("edits")
    pattern, suggested = build_pattern(settings=settings, ref=ref_obj, main_html=main_html, print_html=print_html, pdf_path=pdf)
    meta["pattern"] = pattern.model_dump()
    if previous:
        # Keep what the user has typed. Only fill in empty lists that the new file can supply.
        merged = Edits(**previous)
        if not merged.categories and suggested.categories:
            merged.categories = suggested.categories
        if suggested.tags:
            merged.tags = list(dict.fromkeys([*merged.tags, *suggested.tags]))
        meta["edits"] = merged.model_dump()
    else:
        meta["edits"] = suggested.model_dump()
    meta["files"] = {"main_html": main_html is not None, "print_html": print_html is not None, "pdf": True}
    meta["status"] = "ready"


async def run_auto(draft: Draft, svc: Services) -> None:
    """Stage 1, link route. Never raises: every outcome ends in 'ready', 'manual' or 'error'."""
    s = svc.settings
    meta = draft.load()
    ref = PatternRef(meta["ref"]["site_id"], meta["ref"]["cid"])
    try:
        # 1. pattern page
        _set_step(meta, "page", "active")
        draft.save(meta)
        try:
            main_html = await svc.fetcher.get_html(ref.main_url(s.drops_base))
        except PatternNotFound:
            meta["status"] = "error"
            meta["error"] = {"code": "not_found", "message": "DROPS has no pattern with that number. Check the link."}
            _set_step(meta, "page", "failed", "Not found")
            draft.save(meta)
            return
        draft.main_html.write_text(main_html, encoding="utf-8")
        _set_step(meta, "page", "done")

        # 2. print view
        _set_step(meta, "print", "active")
        draft.save(meta)
        print_html = await svc.fetcher.get_html(ref.print_url(s.drops_base))
        draft.print_html.write_text(print_html, encoding="utf-8")
        _set_step(meta, "print", "done")

        # 3. PDF (headless Chromium, offline)
        _set_step(meta, "pdf", "active")
        draft.save(meta)
        html = await make_self_contained(print_html, f"{s.drops_base}/includes/", svc.fetcher)
        await html_to_pdf(html, draft.pdf, s)
        _set_step(meta, "pdf", "done")

        # 4. read
        _set_step(meta, "read", "active")
        draft.save(meta)
        rebuild_pattern(draft, meta, s)
        _set_step(meta, "read", "done")
        draft.save(meta)
    except FetchBlocked as exc:
        log.warning("DROPS fetch blocked for %s: %s (%s)", ref, exc.code, exc.technical)
        for step in meta["progress"]:
            if step["state"] == "active":
                step["state"] = "failed"
                step["detail"] = exc.message
        go_manual(draft, meta, exc.code, exc.message, exc.technical)
    except RendererUnavailable as exc:
        log.warning("PDF renderer unavailable: %s", exc)
        _set_step(meta, "pdf", "failed", "No PDF maker on this server")
        go_manual(draft, meta, "no_renderer", "This server cannot make the PDF itself.", str(exc))
    except NotAPattern as exc:
        _set_step(meta, "read", "failed", str(exc))
        go_manual(draft, meta, "unreadable", "The pages came back, but the pattern could not be read from them.", str(exc))
    except Exception as exc:  # last resort: never leave a draft stuck on 'working'
        log.exception("Unexpected error in run_auto")
        for step in meta["progress"]:
            if step["state"] == "active":
                step["state"] = "failed"
        go_manual(draft, meta, "unexpected", "Something went wrong while getting the pattern.", repr(exc))


def _publish_set(meta: dict, key: str, state: str, detail: str = "") -> None:
    for step in meta["publish"]["steps"]:
        if step["key"] == key:
            step["state"] = state
            step["detail"] = detail


async def run_publish(draft: Draft, svc: Services, allow_duplicate: bool) -> None:
    """Stage 3. Safe to call again after a failure: finished steps are not repeated."""
    s = svc.settings
    meta = draft.load()
    pub = meta.get("publish") or {}
    if not pub.get("steps"):
        pub = {"state": "running", "steps": _steps(PUBLISH_STEPS), "recipe_id": None, "error": None, "duplicates": None}
    pub["state"] = "running"
    pub["error"] = None
    meta["publish"] = pub
    draft.save(meta)

    pattern = PatternData(**meta["pattern"])
    edits = Edits(**meta["edits"])
    title = edits.title.strip() or pattern.title

    def done(step: str) -> bool:
        return any(st["key"] == step and st["state"] == "done" for st in pub["steps"])

    try:
        # 1. duplicates
        if not done("check"):
            _publish_set(meta, "check", "active")
            draft.save(meta)
            dups = await svc.kl.check_duplicate(draft.pdf, title)
            if (dups["content"] or dups["title"]) and not allow_duplicate:
                pub["state"] = "duplicate"
                pub["duplicates"] = dups
                _publish_set(meta, "check", "failed", "Already in your library")
                draft.save(meta)
                return
            _publish_set(meta, "check", "done", "Not in your library yet" if not (dups["content"] or dups["title"]) else "Adding anyway")

        # 2. recipe
        if not done("recipe"):
            _publish_set(meta, "recipe", "active")
            draft.save(meta)
            recipe = await svc.kl.create_recipe(title, edits.description, edits.categories, edits.tags, draft.pdf)
            pub["recipe_id"] = recipe["id"]
            _publish_set(meta, "recipe", "done")
            draft.save(meta)
        recipe_id = pub["recipe_id"]

        # 3. text version
        if not done("text"):
            _publish_set(meta, "text", "active")
            draft.save(meta)
            md = build_text_version(pattern, recipe_id=recipe_id)
            await svc.kl.put_text_version(recipe_id, md, "en")
            _publish_set(meta, "text", "done")
            draft.save(meta)

        # 4. cover
        if not done("cover"):
            _publish_set(meta, "cover", "active")
            draft.save(meta)
            detail = ""
            try:
                await _wait_for_pages(svc.kl, recipe_id, edits.cover_page)
                if edits.cover_page != 1:
                    await svc.kl.set_cover_page(recipe_id, edits.cover_page)
                else:
                    detail = "Page 1"
                _publish_set(meta, "cover", "done", detail or f"Page {edits.cover_page}")
            except KLError as exc:
                _publish_set(meta, "cover", "skipped", exc.message)
            draft.save(meta)

        # 5. yarns (nice to have; never blocks the pattern)
        if not done("yarn"):
            _publish_set(meta, "yarn", "active")
            draft.save(meta)
            try:
                added = await _seed_yarns(svc.kl, pattern)
                _publish_set(meta, "yarn", "done", added)
            except KLError as exc:
                _publish_set(meta, "yarn", "skipped", exc.message)
            draft.save(meta)

        pub["state"] = "done"
        meta["status"] = "published"
        draft.save(meta)
    except KLError as exc:
        log.warning("Publish failed: %s (%s %s)", exc.message, exc.status, exc.technical)
        for st in pub["steps"]:
            if st["state"] == "active":
                st["state"] = "failed"
                st["detail"] = exc.message
        pub["state"] = "error"
        pub["error"] = {"message": exc.message, "technical": exc.technical, "status": exc.status}
        draft.save(meta)
    except Exception as exc:
        log.exception("Unexpected publish error")
        for st in pub["steps"]:
            if st["state"] == "active":
                st["state"] = "failed"
        pub["state"] = "error"
        pub["error"] = {"message": "Something unexpected went wrong.", "technical": repr(exc), "status": None}
        draft.save(meta)


async def _wait_for_pages(kl: KnittingLibrary, recipe_id: str, want_page: int, tries: int = 12) -> None:
    import asyncio

    for _ in range(tries):
        if await kl.pdf_pages_ready(recipe_id) >= want_page:
            return
        await asyncio.sleep(1.0)
    raise KLError("The page pictures were not ready in time.")


async def _seed_yarns(kl: KnittingLibrary, pattern: PatternData) -> str:
    new_yarns = new_colours = 0
    seen: set[tuple[str, str]] = set()
    for opt in pattern.yarn_options:
        for comp in opt.components:
            yarn_id, created = await kl.ensure_yarn(comp.name, comp.product_url)
            new_yarns += int(created)
            for col in comp.colours:
                label = f"{col.number} {col.name}".strip()
                if not label or (comp.slug, label) in seen:
                    continue
                seen.add((comp.slug, label))
                new_colours += int(await kl.ensure_colour(yarn_id, label))
    if not (new_yarns or new_colours):
        return "Already there"
    return f"{new_yarns} new yarn{'s' if new_yarns != 1 else ''}, {new_colours} new colour{'s' if new_colours != 1 else ''}"
