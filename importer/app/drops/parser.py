"""Parsing DROPS pages: the pattern page (metadata) and the print view (full text)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from app.drops.text import collapse_blank_lines, html_to_lines


@dataclass
class Video:
    id: str
    title: str
    duration: str
    url: str


@dataclass
class Lesson:
    title: str
    url: str


@dataclass
class MainPage:
    site_id: int | None = None
    cid: int | None = None
    title: str = ""
    number: str = ""
    description: str = ""
    canonical: str = ""
    breadcrumb: list[tuple[str, str]] = field(default_factory=list)  # (label, href)
    tags: list[str] = field(default_factory=list)
    photos: list[str] = field(default_factory=list)
    videos: list[Video] = field(default_factory=list)
    lessons: list[Lesson] = field(default_factory=list)
    yarn_slugs: list[str] = field(default_factory=list)
    language: str = ""

    @property
    def usable(self) -> bool:
        return bool(self.title and (self.number or self.site_id))


@dataclass
class PrintPage:
    title: str = ""
    number: str = ""
    lines: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return bool(self.lines) and len(self.lines) > 15


def looks_like_print_view(html: str) -> bool:
    head = html[:6000].lower()
    return "pattern-print.php" in head or "printed version" in head


def looks_like_main_page(html: str) -> bool:
    head = html[:200000].lower()
    return ("breadcrumb" in head and "patterndescription" in head) or "pattern.php?id=" in html[:400]


def _site_ids(text: str) -> tuple[int | None, int | None]:
    try:
        q = parse_qs(urlparse(text).query)
        site = int(q["id"][0]) if "id" in q else None
        cid = int(q["cid"][0]) if "cid" in q else None
        return site, cid
    except (ValueError, IndexError):
        return None, None


def parse_main_page(html: str) -> MainPage:
    soup = BeautifulSoup(html, "lxml")
    page = MainPage()

    saved = re.search(r"saved from url=\(\d+\)(\S+)", html[:600])
    canon_el = soup.find("link", rel="canonical")
    canonical = (canon_el.get("href") if canon_el else "") or ""
    if not canonical:
        og = soup.find("meta", property="og:url")
        canonical = (og.get("content") if og else "") or ""
    if not canonical and saved:
        canonical = saved.group(1)
    page.canonical = canonical
    page.site_id, page.cid = _site_ids(canonical)

    h1 = soup.find("h1")
    page.title = h1.get_text(" ", strip=True) if h1 else ""
    og_title = soup.find("meta", property="og:title")
    title_src = (og_title.get("content") if og_title else "") or (soup.title.get_text() if soup.title else "")
    m = re.search(r"DROPS\s+(\d+-\d+)", title_src)
    page.number = f"DROPS {m.group(1)}" if m else ""
    desc = soup.find("meta", attrs={"name": "description"})
    page.description = (desc.get("content") if desc else "") or ""

    crumb = soup.select_one("ol.breadcrumb") or soup.select_one(".breadcrumb")
    if crumb:
        for a in crumb.find_all("a"):
            page.breadcrumb.append((a.get_text(" ", strip=True), a.get("href", "")))
        last = crumb.find_all("li")
        # The current page is a plain <li> without a link; ignore it.

    for a in soup.find_all("a", href=re.compile(r"action=search&k=\d+")):
        label = a.get_text(" ", strip=True)
        if label and label not in page.tags:
            page.tags.append(label)

    for meta in soup.find_all("meta", property="og:image"):
        src = meta.get("content")
        if src and src not in page.photos:
            page.photos.append(src)

    videos = soup.find(id="videos")
    if videos:
        for a in videos.select('a[href*="video.php?id="]'):
            vid = parse_qs(urlparse(a["href"]).query).get("id", [""])[0]
            title_el = a.select_one(".videos-title")
            dur_el = a.select_one(".video-duration")
            if not vid or not title_el:
                continue
            page.videos.append(
                Video(
                    id=vid,
                    title=title_el.get_text(" ", strip=True),
                    duration=dur_el.get_text(strip=True) if dur_el else "",
                    url=a["href"],
                )
            )

    lessons = soup.find(id="lessons")
    if lessons:
        seen: set[str] = set()
        for a in lessons.find_all("a", href=re.compile(r"lesson\.php\?id=")):
            label = a.get_text(" ", strip=True)
            if label and a["href"] not in seen:
                seen.add(a["href"])
                page.lessons.append(Lesson(title=label, url=a["href"]))

    desc_block = soup.find(id="patternDescription")
    if desc_block:
        for a in desc_block.find_all("a", href=re.compile(r"yarn\.php\?show=")):
            slug = parse_qs(urlparse(a["href"]).query).get("show", [""])[0]
            if slug and slug not in page.yarn_slugs:
                page.yarn_slugs.append(slug)

    lang = soup.select_one(".languages-dropdown .dropdown-toggle")
    page.language = lang.get_text(" ", strip=True) if lang else ""
    return page


def parse_print_page(html: str, base_url: str = "") -> PrintPage:
    soup = BeautifulSoup(html, "lxml")
    page = PrintPage()
    page.title = (soup.title.get_text(" ", strip=True) if soup.title else "").split(" - ")[0].strip()
    meta = soup.find("meta", attrs={"name": "description"})
    m = re.search(r"DROPS\s+(\d+-\d+)", (meta.get("content") if meta else "") or "")
    page.number = f"DROPS {m.group(1)}" if m else ""
    body = soup.body or soup
    page.lines = collapse_blank_lines(html_to_lines(body))
    for img in body.find_all("img"):
        src = img.get("src") or ""
        if src and not src.startswith("data:"):
            page.images.append(urljoin(base_url, src) if base_url else src)
    return page
