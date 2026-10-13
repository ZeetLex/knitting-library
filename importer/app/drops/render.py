"""Turning the DROPS print view into a PDF.

The print page is fetched once (with its few pictures and style file), made self-contained,
and printed by a local headless Chromium with all network access switched off.
Chromium never talks to DROPS.
"""
from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.config import Settings
from app.drops.fetcher import DropsFetcher, FetchBlocked


class RendererUnavailable(RuntimeError):
    pass


MAX_RESOURCES = 14
MAX_TOTAL_BYTES = 30_000_000


async def make_self_contained(print_html: str, base_url: str, fetcher: DropsFetcher) -> str:
    soup = BeautifulSoup(print_html, "lxml")
    for tag in soup.find_all(["script", "iframe", "noscript", "object", "embed", "protonpass-root-c7b4"]):
        tag.decompose()

    total = 0
    count = 0

    async def fetch(url: str) -> tuple[bytes, str]:
        nonlocal total, count
        count += 1
        if count > MAX_RESOURCES:
            raise FetchBlocked("unexpected", "The print page asked for more files than expected.", url)
        data, ctype = await fetcher.get_resource(url)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise FetchBlocked("unexpected", "The print page was larger than expected.", url)
        return data, ctype

    for link in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
        href = link.get("href")
        if not href:
            link.decompose()
            continue
        try:
            data, _ = await fetch(urljoin(base_url, href))
        except FetchBlocked:
            link.decompose()  # style file is nice to have; the text still prints
            continue
        css = data.decode("utf-8", errors="replace")
        css = re.sub(r"@import[^;]+;", "", css)
        css = re.sub(r"url\((?!['\"]?data:)[^)]*\)", "url()", css)  # no network from inside the stylesheet
        style = soup.new_tag("style")
        style.string = css
        link.replace_with(style)

    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if not src or src.startswith("data:"):
            continue
        try:
            data, ctype = await fetch(urljoin(base_url, src))
        except FetchBlocked:
            img.decompose()
            continue
        ctype = (ctype.split(";")[0].strip() if ctype else "") or mimetypes.guess_type(src)[0] or "image/jpeg"
        img["src"] = f"data:{ctype};base64,{base64.b64encode(data).decode()}"
        for attr in ("srcset", "loading"):
            img.attrs.pop(attr, None)

    return str(soup)


async def html_to_pdf(html: str, out_path: Path, settings: Settings) -> None:
    exe = Path(settings.chromium_path)
    if not exe.exists():
        raise RendererUnavailable(f"Chromium not found at {exe}")
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover
        raise RendererUnavailable("playwright is not installed") from exc

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path=str(exe),
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--disable-extensions"],
        )
        try:
            page = await browser.new_page()

            async def only_inline(route):
                url = route.request.url
                if url.startswith("data:") or url.startswith("about:"):
                    await route.continue_()
                else:
                    await route.abort()

            await page.route("**/*", only_inline)
            await page.set_content(html, wait_until="load")
            await page.pdf(
                path=str(out_path),
                format="A4",
                print_background=True,
                margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
            )
        finally:
            await browser.close()
