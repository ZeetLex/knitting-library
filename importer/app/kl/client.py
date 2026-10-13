"""Talking to Knitting Library over its own HTTP API.

The importer signs in as a normal (non-admin) user. Requests carry `X-Session-Token`,
which Knitting Library accepts without a CSRF token. The token lasts 30 days; if it stops
working the client signs in again once and retries.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings


class KLError(Exception):
    def __init__(self, message: str, status: int | None = None, technical: str = ""):
        super().__init__(message)
        self.message = message
        self.status = status
        self.technical = technical


class KnittingLibrary:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.s = settings
        self._transport = transport
        self._token: str | None = None
        self._login_lock = asyncio.Lock()

    def _client(self, timeout: float = 60.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.s.kl_url, transport=self._transport, timeout=timeout)

    async def _login(self) -> None:
        async with self._login_lock:
            if not self.s.kl_password:
                raise KLError("The importer has no Knitting Library password set (KL_PASSWORD).")
            try:
                async with self._client(15) as c:
                    r = await c.post("/api/auth/login", json={"username": self.s.kl_username, "password": self.s.kl_password})
            except httpx.HTTPError as exc:
                raise KLError("Could not reach Knitting Library.", technical=repr(exc)) from exc
            if r.status_code == 429:
                raise KLError("Knitting Library is limiting sign-ins. Wait a few minutes and try again.", 429)
            if r.status_code != 200:
                raise KLError("Knitting Library did not accept the importer's sign-in.", r.status_code, r.text[:200])
            data = r.json()
            token = data.get("token")
            if not token or data.get("requires_2fa") or data.get("two_factor_required"):
                raise KLError("The importer account must not use two-factor sign-in.", technical=str(list(data.keys())))
            self._token = token

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self._token:
            await self._login()
        for attempt in (1, 2):
            try:
                async with self._client() as c:
                    r = await c.request(method, path, headers={"X-Session-Token": self._token or ""}, **kwargs)
            except httpx.HTTPError as exc:
                raise KLError("Could not reach Knitting Library.", technical=repr(exc)) from exc
            if r.status_code == 401 and attempt == 1:
                self._token = None
                await self._login()
                continue
            return r
        raise KLError("Knitting Library kept refusing the importer's sign-in.", 401)

    @staticmethod
    def _ok(r: httpx.Response, what: str) -> Any:
        if r.status_code >= 400:
            detail = ""
            try:
                detail = str(r.json().get("detail", ""))
            except Exception:
                detail = r.text[:200]
            raise KLError(f"Knitting Library could not {what}.", r.status_code, detail)
        try:
            return r.json()
        except Exception:
            return {}

    # ---- status and suggestions
    async def status(self) -> dict:
        try:
            async with self._client(8) as c:
                r = await c.get("/api/setup/status")
            if r.status_code != 200:
                return {"reachable": False, "logged_in": False, "detail": f"HTTP {r.status_code}"}
            if r.json().get("setup_required"):
                return {"reachable": True, "logged_in": False, "detail": "Knitting Library has not been set up yet."}
        except httpx.HTTPError:
            return {"reachable": False, "logged_in": False, "detail": "Cannot reach Knitting Library."}
        try:
            await self._login() if not self._token else None
            r = await self._request("GET", "/api/auth/me")
            return {"reachable": True, "logged_in": r.status_code == 200, "detail": "" if r.status_code == 200 else "Sign-in failed."}
        except KLError as exc:
            return {"reachable": True, "logged_in": False, "detail": exc.message}

    async def suggestions(self) -> dict:
        out = {"categories": [], "tags": []}
        for key, path in (("categories", "/api/categories?all=true"), ("tags", "/api/tags?all=true")):
            try:
                r = await self._request("GET", path)
                data = r.json() if r.status_code == 200 else []
                out[key] = [x if isinstance(x, str) else x.get("name", "") for x in data]
            except KLError:
                pass
        return out

    # ---- recipes
    async def check_duplicate(self, pdf: Path, title: str) -> dict:
        with open(pdf, "rb") as fh:
            r = await self._request(
                "POST", "/api/recipes/check-duplicate", data={"title": title}, files={"files": ("pattern.pdf", fh, "application/pdf")}
            )
        data = self._ok(r, "check for duplicates")
        return {
            "content": data.get("content_duplicates", []),
            "title": data.get("title_duplicates", []),
        }

    async def create_recipe(self, title: str, description: str, categories: list[str], tags: list[str], pdf: Path) -> dict:
        with open(pdf, "rb") as fh:
            r = await self._request(
                "POST",
                "/api/recipes",
                data={
                    "title": title,
                    "description": description,
                    "categories": ",".join(c.replace(",", " ") for c in categories),
                    "tags": ",".join(t.replace(",", " ") for t in tags),
                },
                files={"files": ("pattern.pdf", fh, "application/pdf")},
            )
        return self._ok(r, "add the pattern")

    async def get_recipe(self, recipe_id: str) -> dict:
        r = await self._request("GET", f"/api/recipes/{recipe_id}")
        return self._ok(r, "read the pattern back")

    async def pdf_pages_ready(self, recipe_id: str) -> int:
        r = await self._request("GET", f"/api/recipes/{recipe_id}/pdf-pages")
        if r.status_code != 200:
            return 0
        data = r.json()
        pages = data.get("pages", data) if isinstance(data, dict) else data
        return len(pages) if isinstance(pages, list) else 0

    async def put_text_version(self, recipe_id: str, markdown: str, language: str = "en") -> dict:
        r = await self._request(
            "PUT", f"/api/recipes/{recipe_id}/text-version", json={"content_markdown": markdown, "language": language}
        )
        return self._ok(r, "save the instructions text")

    async def set_cover_page(self, recipe_id: str, page: int) -> dict:
        r = await self._request(
            "POST", f"/api/recipes/{recipe_id}/set-thumbnail", json={"source": "pdf_page", "filename": f"page-{page:03d}.jpg"}
        )
        return self._ok(r, "set the cover picture")

    # ---- yarns
    async def list_yarns(self) -> list[dict]:
        r = await self._request("GET", "/api/yarns")
        data = self._ok(r, "list yarns")
        return data if isinstance(data, list) else data.get("yarns", [])

    async def ensure_yarn(self, name: str, product_url: str) -> tuple[str, bool]:
        for y in await self.list_yarns():
            if (y.get("name", "").strip().lower()) == name.strip().lower():
                return y["id"], False
        r = await self._request(
            "POST", "/api/yarns", data={"name": name, "seller": "DROPS Design", "product_info": product_url}
        )
        return self._ok(r, f"add the yarn {name}")["id"], True

    async def ensure_colour(self, yarn_id: str, label: str) -> bool:
        r = await self._request("GET", f"/api/yarns/{yarn_id}/colours")
        have = [c.get("name", "").strip().lower() for c in (self._ok(r, "list colours") or [])]
        if label.strip().lower() in have:
            return False
        r = await self._request("POST", f"/api/yarns/{yarn_id}/colours", json={"name": label})
        self._ok(r, f"add the colour {label}")
        return True
