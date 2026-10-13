"""Turning DROPS HTML and PDF text into clean lines."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

_BLOCK = {"p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "section"}
_SKIP = {"script", "style", "noscript", "head"}


def html_to_lines(node: Tag | BeautifulSoup) -> list[str]:
    """Flatten markup to text lines. <br> and block elements break lines; inline tags do not."""
    parts: list[str] = []

    def walk(el):
        for child in el.children:
            if isinstance(child, NavigableString):
                if child.__class__.__name__ in {"Comment", "Doctype", "Declaration", "CData", "ProcessingInstruction"}:
                    continue
                parts.append(str(child))
            elif isinstance(child, Tag):
                if child.name in _SKIP:
                    continue
                if child.name == "br":
                    parts.append("\n")
                    continue
                is_block = child.name in _BLOCK
                if is_block:
                    parts.append("\n")
                walk(child)
                if is_block:
                    parts.append("\n")

    walk(node)
    text = "".join(parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n")]
    return lines


def collapse_blank_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    while out and not out[0]:
        out.pop(0)
    return out


def pdf_to_text(path: Path, timeout: int = 30) -> str:
    """Extract text with poppler. Returns '' if the PDF has no text layer."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", "-nopgbrk", str(path), "-"],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", errors="replace")


_SENTENCE_END = re.compile(r"[.:;!?)\]]$")
_HEADER_LINE_RE = re.compile(
    r"^(DROPS Design|#\S+|DROPS \d+-\d+|DROPS Design: Pattern .+|Yarn group .+)$", re.IGNORECASE
)


def reflow_pdf_text(text: str) -> list[str]:
    """PDF text is hard-wrapped. Join wrapped lines back into the original logical lines.

    A line is joined to the previous one when the previous line does not end a sentence.
    Blank lines are kept as separators. Headings (ALL CAPS ending in a colon) stay on their own line.
    """
    from app.drops.pattern_text import HEADING_RE  # local import avoids a cycle

    raw = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.replace("\xa0", " ").split("\n")]
    out: list[str] = []
    for ln in raw:
        if not ln:
            out.append("")
            continue
        prev = out[-1] if out else ""
        if (
            prev
            and not HEADING_RE.match(prev)
            and not HEADING_RE.match(ln)
            and not _HEADER_LINE_RE.match(prev)
            and not _HEADER_LINE_RE.match(ln)
            and not re.match(r"^-{8,}$", prev)
            and not re.match(r"^-{8,}$", ln)
            and not _SENTENCE_END.search(prev)
            and not ln.startswith("#")
        ):
            joiner = "" if prev.endswith("-") and re.search(r"\d-$", prev) else " "
            out[-1] = prev + joiner + ln
        else:
            out.append(ln)
    return collapse_blank_lines(out)
