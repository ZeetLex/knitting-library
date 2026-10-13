"""Lets the importer live under a path such as /import on a shared hostname.

Pangolin can send knit.example/import/... to this app. It may or may not strip the
prefix first, so both are accepted: a request for /import/api/health and one for
/api/health reach the same place. The page itself only uses relative addresses,
so it works either way.
"""
from __future__ import annotations

from urllib.parse import quote


def clean_base_path(value: str) -> str:
    value = (value or "").strip().strip("/")
    return f"/{value}" if value else ""


class BasePathMiddleware:
    def __init__(self, app, base_path: str):
        self.app = app
        self.base = clean_base_path(base_path)

    async def __call__(self, scope, receive, send):
        if not self.base or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        if path == self.base:
            # The page uses relative addresses, so it must be opened with the slash.
            query = scope.get("query_string", b"").decode("latin-1")
            location = quote(self.base) + "/" + (f"?{query}" if query else "")
            await send({
                "type": "http.response.start",
                "status": 308,
                "headers": [(b"location", location.encode("latin-1")), (b"content-length", b"0")],
            })
            await send({"type": "http.response.body", "body": b""})
            return
        if path.startswith(self.base + "/"):
            scope = dict(scope)
            scope["path"] = path[len(self.base):]
            raw = scope.get("raw_path")
            if raw:
                prefix = self.base.encode("latin-1")
                if raw.startswith(prefix):
                    scope["raw_path"] = raw[len(prefix):]
        await self.app(scope, receive, send)
