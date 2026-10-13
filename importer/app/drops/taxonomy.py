"""Deciding which categories and tags a DROPS pattern gets in Knitting Library."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from app.drops.parser import MainPage
from app.drops.pattern_text import PatternText

MAX_TAGS = 20


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _browse_levels(main: MainPage) -> list[str]:
    levels = []
    for label, href in main.breadcrumb:
        q = parse_qs(urlparse(href).query)
        if q.get("action", [""])[0] == "browse" and q.get("c"):
            levels.append(label)
    return levels


def _collection(main: MainPage) -> str:
    for label, href in main.breadcrumb:
        q = parse_qs(urlparse(href).query)
        show = q.get("show", [""])[0]
        if show.startswith("drops-"):
            return f"DROPS {label}"
    return ""


def craft_of(main: MainPage | None, text: PatternText) -> str:
    probe = " ".join(filter(None, [main.description if main else "", text.intro, " ".join(text.tension)])).lower()
    if re.search(r"\bcrochet", probe[:200]) or any("crochet" in t.lower() for t in text.tension):
        return "crochet"
    return "knitting"


def build_taxonomy(main: MainPage | None, text: PatternText) -> tuple[list[str], list[str], list[str]]:
    """Return (categories, tags, notes)."""
    notes: list[str] = []
    categories: list[str] = []
    tags: list[str] = []

    if main:
        levels = _browse_levels(main)
        categories = levels[:2]
        if len(levels) > 2:
            tags.extend(l.lower() for l in levels[2:])
        tags.extend(main.tags)
        collection = _collection(main)
        if collection:
            tags.append(collection)
        if not main.tags:
            notes.append("The page had no tag chips, so only the basics were added.")
        if not categories:
            notes.append("No categories were found on the page.")
    else:
        notes.append("Tags and categories come from the pattern page. Add the saved page to fill them in, or add them by hand.")
        m = re.search(r"DROPS\s+(\d+)-\d+", text.number)
        if m:
            tags.append(f"DROPS {m.group(1)}")

    tags.append("DROPS")
    tags.append(craft_of(main, text))
    for opt in text.yarn_options:
        for comp in opt.components:
            tags.append(comp.name)
    return _dedupe(categories), _dedupe(tags)[:MAX_TAGS], notes
