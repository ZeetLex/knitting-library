"""Fetching DROPS pages politely.

Rules this module keeps:
 - one request at a time, with a pause between requests (DROPS_MIN_INTERVAL)
 - an honest User-Agent, no cookie tricks, no headless browser against the site
 - only the DROPS hosts that are configured
 - anything that looks like a bot check or a refusal is reported, never worked around
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from app.config import Settings


class FetchBlocked(Exception):
    """DROPS did not hand over the page. `code` is stable, `message` is safe to show."""

    def __init__(self, code: str, message: str, technical: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.technical = technical


class PatternNotFound(Exception):
    pass


_CHALLENGE_MARKERS = (
    "just a moment",
    "cf-chl",
    "challenge-platform",
    "attention required",
    "captcha",
    "verify you are human",
    "checking your browser",
    "access denied",
    "bot detection",
)


def detect_block(status: int, headers: httpx.Headers | dict, body: str) -> FetchBlocked | None:
    h = {k.lower(): v for k, v in dict(headers).items()}
    if h.get("cf-mitigated", "").lower() == "challenge":
        return FetchBlocked("challenge", "DROPS asked for a human check, which a program cannot do.", "cf-mitigated: challenge")
    if status == 404:
        return None  # handled separately
    if status == 429:
        return FetchBlocked("rate", "DROPS asked us to slow down.", f"HTTP {status}")
    if status in (401, 403):
        return FetchBlocked("refused", "DROPS refused the request.", f"HTTP {status}")
    if status >= 500:
        return FetchBlocked("unavailable", "DROPS is not answering at the moment.", f"HTTP {status}")
    low = body[:6000].lower()
    if status != 200 or any(m in low for m in _CHALLENGE_MARKERS):
        # A normal pattern page never contains these markers near the top
        if any(m in low for m in _CHALLENGE_MARKERS):
            return FetchBlocked("challenge", "DROPS asked for a human check, which a program cannot do.", "challenge marker in page")
        if status != 200:
            return FetchBlocked("unexpected", f"DROPS answered in an unexpected way (HTTP {status}).", f"HTTP {status}")
    return None


def _decode(content: bytes, content_type: str) -> str:
    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=")[-1].split(";")[0].strip() or "utf-8"
    try:
        return content.decode(charset, errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


class DropsFetcher:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.s = settings
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._transport = transport
        self._cache_dir = settings.data_dir / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- helpers
    def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        return p.scheme in {"http", "https"} and (p.hostname or "") in self.s.drops_hosts

    def _cache_path(self, url: str) -> Path:
        return self._cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".bin")

    def _cache_get(self, url: str) -> bytes | None:
        path = self._cache_path(url)
        try:
            if path.exists() and time.time() - path.stat().st_mtime < self.s.drops_cache_hours * 3600:
                return path.read_bytes()
        except OSError:
            return None
        return None

    def _cache_put(self, url: str, data: bytes) -> None:
        try:
            self._cache_path(url).write_bytes(data)
        except OSError:
            pass

    async def _pause(self) -> None:
        wait = self.s.drops_min_interval - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)

    async def _get(self, url: str, accept: str) -> tuple[int, httpx.Headers, bytes]:
        if not self._allowed(url):
            raise FetchBlocked("host", "That address is not one this tool is allowed to fetch.", url)
        async with self._lock:
            await self._pause()
            try:
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=httpx.Timeout(20.0, connect=10.0),
                    follow_redirects=False,
                    headers={"User-Agent": self.s.user_agent, "Accept": accept, "Accept-Language": "en-GB,en;q=0.8"},
                ) as client:
                    current = url
                    for _ in range(4):
                        resp = await client.get(current)
                        self._last = time.monotonic()
                        if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                            current = urljoin(current, resp.headers["location"])
                            if not self._allowed(current):
                                raise FetchBlocked("host", "DROPS sent us to another website.", current)
                            continue
                        return resp.status_code, resp.headers, resp.content
                    raise FetchBlocked("unexpected", "DROPS redirected too many times.", url)
            except httpx.TimeoutException as exc:
                raise FetchBlocked("network", "DROPS took too long to answer.", repr(exc)) from exc
            except httpx.HTTPError as exc:
                raise FetchBlocked("network", "Could not reach DROPS from here.", repr(exc)) from exc

    # ---- public
    async def get_html(self, url: str) -> str:
        cached = self._cache_get(url)
        if cached is not None:
            return cached.decode("utf-8", errors="replace")
        status, headers, content = await self._get(url, "text/html,application/xhtml+xml")
        text = _decode(content, headers.get("content-type", ""))
        if status == 404:
            raise PatternNotFound()
        blocked = detect_block(status, headers, text)
        if blocked:
            raise blocked
        self._cache_put(url, content)
        return text

    async def get_resource(self, url: str, max_bytes: int = 12_000_000) -> tuple[bytes, str]:
        cached = self._cache_get(url)
        if cached is not None:
            return cached, ""
        status, headers, content = await self._get(url, "image/*,text/css,*/*;q=0.5")
        if status != 200:
            raise FetchBlocked("unexpected", f"A picture or style file could not be fetched (HTTP {status}).", url)
        if len(content) > max_bytes:
            raise FetchBlocked("unexpected", "A file on the page was larger than expected.", url)
        self._cache_put(url, content)
        return content, headers.get("content-type", "")
