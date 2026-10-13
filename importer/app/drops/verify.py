"""Checking files that Mary saves by hand, and telling her plainly what is right or wrong."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.drops.fetcher import _CHALLENGE_MARKERS
from app.drops.parser import looks_like_main_page, looks_like_print_view, parse_main_page, parse_print_page
from app.drops.pattern_text import parse_pattern_text
from app.drops.pdfinfo import inspect_pdf
from app.drops.text import pdf_to_text, reflow_pdf_text

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Check:
    state: str
    label: str
    detail: str = ""


@dataclass
class Verdict:
    kind: str  # pdf | main_html | print_html | unknown
    ok: bool
    headline: str
    checks: list[Check] = field(default_factory=list)
    title: str = ""
    number: str = ""
    site_id: int | None = None
    page_count: int = 0
    advice: str = ""

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "ok": self.ok,
            "headline": self.headline,
            "checks": [c.__dict__ for c in self.checks],
            "title": self.title,
            "number": self.number,
            "site_id": self.site_id,
            "page_count": self.page_count,
            "advice": self.advice,
        }


@dataclass
class Expect:
    number: str = ""
    site_id: int | None = None
    title: str = ""


def _same_pattern(expect: Expect, number: str, site_id: int | None) -> Check | None:
    if expect.number and number and expect.number != number:
        return Check(FAIL, "Same pattern as your other file", f"This one is {number}, the other is {expect.number}.")
    if expect.site_id and site_id and expect.site_id != site_id:
        return Check(FAIL, "Same pattern as your other file", "The two files are for different patterns.")
    if (expect.number and number) or (expect.site_id and site_id):
        return Check(OK, "Same pattern as your other file")
    return None


def verify_pdf(path: Path, max_mb: int, expect: Expect | None = None) -> Verdict:
    v = Verdict(kind="pdf", ok=False, headline="")
    size_mb = path.stat().st_size / 1_000_000
    facts = inspect_pdf(path)
    if facts.error == "not a PDF":
        v.checks.append(Check(FAIL, "It is a PDF file", "This file is not a PDF."))
        v.headline = "That is not a PDF"
        v.advice = "In the DROPS print window, choose Save as PDF as the destination, then Save. Drop the saved file here."
        return v
    if not facts.ok:
        detail = "It is password protected." if facts.encrypted else "The file could not be opened."
        v.checks.append(Check(FAIL, "It is a PDF file", detail))
        v.headline = "That PDF could not be opened"
        v.advice = "Try saving it again from the DROPS print window."
        return v
    v.checks.append(Check(OK, "It is a PDF file", f"{facts.pages} page{'s' if facts.pages != 1 else ''}, {size_mb:.1f} MB"))
    v.page_count = facts.pages

    if size_mb > max_mb:
        v.checks.append(Check(FAIL, "Small enough to store", f"{size_mb:.0f} MB. The library accepts up to {max_mb} MB."))
        v.headline = "That PDF is too big"
        v.advice = "A normal DROPS pattern is under 1 MB. Check you saved the print view, not the whole website."
        return v

    raw_text = pdf_to_text(path)
    if len(raw_text.strip()) < 200:
        v.checks.append(Check(FAIL, "Text can be read", "This PDF is only pictures, so the instructions cannot be read."))
        v.headline = "This PDF has no readable text"
        v.advice = "Use the DROPS print window and choose Save as PDF. Do not use a screenshot or scan."
        return v
    v.checks.append(Check(OK, "Text can be read"))

    lines = reflow_pdf_text(raw_text)
    text = parse_pattern_text(lines)
    from_drops = bool(re.search(r"DROPS\s+Design", raw_text[:400], re.I)) or "garnstudio" in raw_text.lower()
    if not from_drops:
        v.checks.append(Check(FAIL, "From DROPS Design", "The PDF does not mention DROPS Design."))
        v.headline = "This does not look like a DROPS pattern"
        v.advice = "Open the pattern on garnstudio.com, press its Print button, and save from there."
        return v
    v.checks.append(Check(OK, "From DROPS Design"))

    v.title = text.title
    v.number = text.number
    if text.title:
        v.checks.append(Check(OK, "Pattern found", f"{text.title}" + (f" ({text.number})" if text.number else "")))
    else:
        v.checks.append(Check(WARN, "Pattern found", "The title could not be read, you can type it in the next step."))

    complete = bool(text.sizes) and bool(text.body)
    if complete:
        v.checks.append(Check(OK, "Looks like the print view", "Sizes, yarn and instructions are all there."))
    else:
        v.checks.append(
            Check(WARN, "Looks like the print view", "Some parts are missing. Make sure you used the Print button on the pattern page.")
        )
    if facts.picture_pages:
        v.checks.append(Check(OK, "Pictures included"))
    else:
        v.checks.append(Check(WARN, "Pictures included", "No photos were found in the PDF. The pattern will still work."))

    if expect:
        same = _same_pattern(expect, text.number, None)
        if same:
            v.checks.append(same)
            if same.state == FAIL:
                v.headline = "This is a different pattern"
                v.advice = "Check that both files come from the same DROPS pattern page."
                return v

    v.ok = True
    v.headline = "PDF checked" if complete else "PDF accepted, with a warning"
    return v


def _challenge_page(html: str) -> bool:
    low = html[:6000].lower()
    return any(m in low for m in _CHALLENGE_MARKERS)


def verify_html(html: str, expect: Expect | None = None) -> Verdict:
    v = Verdict(kind="unknown", ok=False, headline="")
    size_kb = len(html.encode("utf-8", errors="ignore")) / 1000
    if "<html" not in html[:2000].lower() and "<!doctype" not in html[:200].lower():
        v.checks.append(Check(FAIL, "It is a web page file", "This file is not a saved web page."))
        v.headline = "That is not a saved web page"
        v.advice = "On the DROPS pattern page press Ctrl+S (Cmd+S on a Mac) and choose Webpage, HTML only."
        return v
    v.checks.append(Check(OK, "It is a web page file", f"{size_kb:.0f} KB"))

    if _challenge_page(html):
        v.checks.append(Check(FAIL, "It is the pattern page", "This is the website's 'checking your browser' page, not the pattern."))
        v.headline = "This saved page is a security check"
        v.advice = "Wait for the pattern to appear in your browser, then save the page."
        return v

    if looks_like_print_view(html):
        pr = parse_print_page(html)
        v.kind = "print_html"
        if not pr.usable:
            v.checks.append(Check(FAIL, "It is the print view", "The saved print page is empty."))
            v.headline = "That print page is empty"
            v.advice = "Open the pattern, press Print, and save the page again."
            return v
        text = parse_pattern_text(pr.lines)
        v.title, v.number = text.title or pr.title, text.number or pr.number
        v.checks.append(Check(WARN, "It is the print page", f"{v.title} ({v.number})".strip()))
        v.headline = "That is the print page, not the pattern page"
        v.advice = (
            "For the PDF, press Print on the pattern page and choose Save as PDF. "
            "For tags, yarn links and videos, save the pattern page itself (Ctrl+S, then Webpage, HTML only)."
        )
        return v

    main = parse_main_page(html)
    if not main.usable:
        v.checks.append(Check(FAIL, "It is a DROPS pattern page", "Could not find a pattern in this page."))
        v.headline = "This does not look like a DROPS pattern page"
        v.advice = "Open the pattern on garnstudio.com first, then save that page."
        return v
    v.kind = "main_html"
    v.title, v.number, v.site_id = main.title, main.number, main.site_id
    v.checks.append(Check(OK, "It is a DROPS pattern page", f"{main.title} ({main.number})".strip()))
    if expect:
        same = _same_pattern(expect, main.number, main.site_id)
        if same:
            v.checks.append(same)
            if same.state == FAIL:
                v.headline = "This is a different pattern"
                v.advice = "Check that both files come from the same DROPS pattern page."
                return v

    if main.tags:
        v.checks.append(Check(OK, "Tags found", ", ".join(main.tags)))
    else:
        v.checks.append(Check(WARN, "Tags found", "None. Tags can be added by hand."))
    cats = [l for l, _ in main.breadcrumb][1:3]
    if cats:
        v.checks.append(Check(OK, "Categories found", ", ".join(cats)))
    else:
        v.checks.append(Check(WARN, "Categories found", "None. Categories can be added by hand."))
    if main.videos:
        v.checks.append(Check(OK, "Tutorial videos found", f"{len(main.videos)} videos"))
    else:
        v.checks.append(
            Check(WARN, "Tutorial videos found", "None. The saved page may have been saved before it finished loading.")
        )
    v.ok = True
    v.headline = "Pattern page checked"
    return v
