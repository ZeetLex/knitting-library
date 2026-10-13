"""A tiny pretend Knitting Library, enough to follow the importer's calls."""
from __future__ import annotations

import json
import re
import urllib.parse

import httpx


class FakeKL:
    def __init__(self, duplicate: bool = False, fail_text: bool = False, pages: int = 5):
        self.recipes: dict[str, dict] = {}
        self.yarns: dict[str, dict] = {}
        self.colours: dict[str, list[dict]] = {}
        self.duplicate = duplicate
        self.fail_text = fail_text
        self.pages = pages
        self.calls: list[str] = []
        self.logins = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        self.calls.append(f"{method} {path}")
        if path == "/api/setup/status":
            return httpx.Response(200, json={"setup_required": False})
        if path == "/api/auth/login":
            self.logins += 1
            return httpx.Response(200, json={"token": "tok123", "user": {"username": "importer"}})
        if req.headers.get("x-session-token") != "tok123":
            return httpx.Response(401, json={"detail": "no"})
        if path == "/api/auth/me":
            return httpx.Response(200, json={"username": "importer"})
        if path == "/api/categories":
            return httpx.Response(200, json=[{"name": "Women"}, {"name": "Jumpers"}])
        if path == "/api/tags":
            return httpx.Response(200, json=[{"name": "raglan"}])
        if path == "/api/recipes/check-duplicate":
            if self.duplicate:
                return httpx.Response(200, json={"content_duplicates": [{"id": "old", "title": "Old copy"}], "title_duplicates": []})
            return httpx.Response(200, json={"content_duplicates": [], "title_duplicates": []})
        if path == "/api/recipes" and method == "POST":
            body = req.content.decode("latin-1")
            m = re.search(r'name="title"\r\n\r\n([^\r]*)', body)
            title = m.group(1) if m else "x"
            rid = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            self.recipes[rid] = {"id": rid, "title": title, "body": body[:2000]}
            return httpx.Response(200, json={"id": rid, "title": title})
        m = re.fullmatch(r"/api/recipes/([^/]+)/pdf-pages", path)
        if m:
            return httpx.Response(200, json={"pages": [f"page-{i:03d}.jpg" for i in range(1, self.pages + 1)]})
        m = re.fullmatch(r"/api/recipes/([^/]+)/text-version", path)
        if m and method == "PUT":
            if self.fail_text:
                return httpx.Response(500, json={"detail": "boom"})
            self.recipes[m.group(1)]["text"] = json.loads(req.content)
            return httpx.Response(200, json={"ok": True})
        m = re.fullmatch(r"/api/recipes/([^/]+)/set-thumbnail", path)
        if m:
            self.recipes[m.group(1)]["thumb"] = json.loads(req.content)
            return httpx.Response(200, json={"ok": True})
        if path == "/api/yarns" and method == "GET":
            return httpx.Response(200, json=list(self.yarns.values()))
        if path == "/api/yarns" and method == "POST":
            name = urllib.parse.parse_qs(req.content.decode())["name"][0]
            yid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            self.yarns[yid] = {"id": yid, "name": name}
            self.colours[yid] = []
            return httpx.Response(200, json={"id": yid, "name": name})
        m = re.fullmatch(r"/api/yarns/([^/]+)/colours", path)
        if m:
            yid = m.group(1)
            if method == "GET":
                return httpx.Response(200, json=self.colours.get(yid, []))
            name = json.loads(req.content)["name"]
            self.colours.setdefault(yid, []).append({"name": name})
            return httpx.Response(200, json={"name": name})
        return httpx.Response(404, json={"detail": f"unmocked {method} {path}"})
