"""Parsing the plain text of a DROPS pattern (print view text or PDF text)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.drops.yarns import YarnOption, parse_yarn_section

# ALL CAPS line ending in a colon, e.g. "YOKE:" or "JUMPER – SHORT OVERVIEW OF THE PIECE:".
HEADING_RE = re.compile(r"^(?=.*[A-ZÆØÅÄÖÜ]{3})[A-ZÆØÅÄÖÜ0-9 ,\-–/()&'’+.]+:\s*$")
# "ROUND 1:" style lines are content, not headings.
_STEP_RE = re.compile(r"^(ROUND|ROW|RND|PART|STEP|MARKER)\s*\d", re.IGNORECASE)
_DASHES_RE = re.compile(r"^-{8,}$")
_NUMBER_RE = re.compile(r"^DROPS\s+(?P<num>\d+-\d+)\s*$", re.IGNORECASE)
_DESIGNER_RE = re.compile(r"^DROPS Design:\s*Pattern\s+(?P<id>[A-Za-z]+-\d+)\s*$", re.IGNORECASE)
_GROUP_RE = re.compile(r"^Yarn group\s+(?P<g>.+)$", re.IGNORECASE)
_FOOTER_STARTS = ("have you finished this pattern", "©", "do you need help with this pattern")

SECTION_ALIASES = {
    "SIZES": "sizes",
    "SIZE": "sizes",
    "YARN": "yarn",
    "NEEDLES": "needles",
    "CROCHET HOOK": "needles",
    "KNITTING TENSION": "tension",
    "KNITTING GAUGE": "tension",
    "CROCHET TENSION": "tension",
    "CROCHET GAUGE": "tension",
    "TENSION": "tension",
    "GAUGE": "tension",
}


@dataclass
class Section:
    heading: str
    lines: list[str] = field(default_factory=list)


@dataclass
class PatternText:
    title: str = ""
    hashtag: str = ""
    intro: str = ""
    number: str = ""
    designer_id: str = ""
    yarn_group: str = ""
    sizes: list[str] = field(default_factory=list)
    yarn_options: list[YarnOption] = field(default_factory=list)
    yarn_raw: list[str] = field(default_factory=list)
    needles: list[str] = field(default_factory=list)
    tension: list[str] = field(default_factory=list)
    body: list[Section] = field(default_factory=list)  # everything after the tension block, in order
    has_diagram_note: bool = False
    warnings: list[str] = field(default_factory=list)


def is_heading(line: str) -> bool:
    return bool(HEADING_RE.match(line)) and not _STEP_RE.match(line)


def _split_sizes(lines: list[str]) -> list[str]:
    text = " ".join(l for l in lines if l)
    parts = [p.strip() for p in re.split(r"\s+-\s+|\s+–\s+", text) if p.strip()]
    return parts


def parse_pattern_text(lines: list[str]) -> PatternText:
    out = PatternText()
    # Cut footer
    cleaned: list[str] = []
    for ln in lines:
        if ln.lower().startswith(_FOOTER_STARTS):
            break
        cleaned.append(ln)
    lines = cleaned

    # ----- header: everything before the first dashed separator or first heading
    idx = 0
    header: list[str] = []
    while idx < len(lines) and not _DASHES_RE.match(lines[idx]) and not is_heading(lines[idx]):
        header.append(lines[idx])
        idx += 1
    header = [h for h in header if h]
    # Drop the site name line.
    header = [h for h in header if h.lower() not in {"drops design", "garnstudio.com"}]
    if header:
        out.title = header[0]
    intro: list[str] = []
    for h in header[1:]:
        if h.startswith("#"):
            out.hashtag = h
        elif (m := _NUMBER_RE.match(h)):
            out.number = f"DROPS {m.group('num')}"
        elif (m := _DESIGNER_RE.match(h)):
            out.designer_id = m.group("id")
        elif (m := _GROUP_RE.match(h)):
            out.yarn_group = m.group("g").strip()
        else:
            intro.append(h)
    out.intro = " ".join(intro).strip()

    # ----- sections
    sections: list[Section] = []
    current: Section | None = None
    for ln in lines[idx:]:
        if _DASHES_RE.match(ln):
            continue
        if is_heading(ln):
            current = Section(heading=ln.rstrip(":").strip())
            sections.append(current)
            continue
        if re.match(r"^diagram explanations\s*:?$", ln, re.IGNORECASE):
            out.has_diagram_note = True
            current = None
            continue
        if current is None:
            if ln:
                current = Section(heading="")
                sections.append(current)
                current.lines.append(ln)
            continue
        current.lines.append(ln)

    for sec in sections:
        sec.lines = _trim(sec.lines)

    # Pull out the facts sections, keep the rest in order
    body: list[Section] = []
    seen_body = False
    for sec in sections:
        key = SECTION_ALIASES.get(sec.heading.upper())
        if key and not seen_body:
            if key == "sizes":
                out.sizes = _split_sizes(sec.lines)
            elif key == "yarn":
                out.yarn_raw = [l for l in sec.lines if l]
                out.yarn_options, warn = parse_yarn_section(sec.lines)
                out.warnings.extend(warn)
            elif key == "needles":
                out.needles = [l for l in sec.lines if l]
            elif key == "tension":
                out.tension = [l for l in sec.lines if l]
            continue
        seen_body = True
        body.append(sec)
    out.body = body

    if not out.title:
        out.warnings.append("Could not find the pattern title in the text.")
    if not out.sizes:
        out.warnings.append("Could not find the size list.")
    if not out.yarn_options:
        out.warnings.append("Could not read the yarn amounts.")
    else:
        for opt in out.yarn_options:
            for comp in opt.components:
                for col in comp.colours:
                    if out.sizes and col.amounts and len(col.amounts) not in (1, len(out.sizes)):
                        out.warnings.append(
                            f"{comp.name}: {len(col.amounts)} amounts for {len(out.sizes)} sizes. Check the yarn list."
                        )
    return out


def _trim(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return lines[start:end]
