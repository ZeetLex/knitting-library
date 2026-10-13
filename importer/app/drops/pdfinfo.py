"""Inspecting a PDF with poppler: page count, which pages hold pictures, page previews."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PdfFacts:
    pages: int = 0
    encrypted: bool = False
    producer: str = ""
    images_by_page: dict[int, list[tuple[int, int]]] = field(default_factory=dict)  # page -> [(w, h)]
    has_text: bool = False
    ok: bool = False
    error: str = ""

    @property
    def picture_pages(self) -> list[int]:
        """Pages whose main content is photographs: the first page with a large portrait image."""
        out = []
        for page, sizes in sorted(self.images_by_page.items()):
            if page == 1 and any(h >= w and h >= 300 for w, h in sizes):
                out.append(page)
        return out

    @property
    def diagram_pages(self) -> list[int]:
        """Pages after the first that hold a large image (size chart, stitch diagrams)."""
        out = []
        for page, sizes in sorted(self.images_by_page.items()):
            if page == 1:
                continue
            if any(w >= 300 and h >= 200 for w, h in sizes):
                out.append(page)
        return out


def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return res.stdout.decode("utf-8", errors="replace") if res.returncode == 0 else ""


def inspect_pdf(path: Path) -> PdfFacts:
    facts = PdfFacts()
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError as exc:
        facts.error = str(exc)
        return facts
    if not head.startswith(b"%PDF-"):
        facts.error = "not a PDF"
        return facts

    info = _run(["pdfinfo", str(path)])
    if not info:
        facts.error = "unreadable"
        return facts
    m = re.search(r"^Pages:\s+(\d+)", info, re.M)
    facts.pages = int(m.group(1)) if m else 0
    facts.encrypted = bool(re.search(r"^Encrypted:\s+yes", info, re.M))
    m = re.search(r"^Producer:\s+(.+)$", info, re.M)
    facts.producer = m.group(1).strip() if m else ""

    listing = _run(["pdfimages", "-list", str(path)])
    for line in listing.splitlines()[2:]:
        cols = line.split()
        if len(cols) >= 5 and cols[0].isdigit() and cols[3].isdigit() and cols[4].isdigit():
            facts.images_by_page.setdefault(int(cols[0]), []).append((int(cols[3]), int(cols[4])))
    facts.ok = facts.pages > 0 and not facts.encrypted
    return facts


def render_page_jpeg(pdf: Path, page: int, out: Path, dpi: int = 70) -> bool:
    """Render one page to a JPEG for previews. `out` is the final file name."""
    stem = out.with_suffix("")
    try:
        subprocess.run(
            ["pdftoppm", "-jpeg", "-r", str(dpi), "-f", str(page), "-l", str(page), "-singlefile", str(pdf), str(stem)],
            capture_output=True,
            timeout=60,
            check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
    return out.exists()
