"""Build the 'text version' Markdown for Knitting Library.

Knitting Library renders this text with a small line-based viewer, not full Markdown:
 - '# ', '## ', '### ' make headings, a blank line makes a gap, '- ' makes a bullet
 - a line wrapped in underscores is a muted note
 - images only work for /api/recipes/... paths on the same site
 - links are only clickable when the patched viewer is installed ([label](https://...))
Lines that would be misread as markup get a leading word joiner so they show literally.
"""
from __future__ import annotations

import re

from app.models import PatternData, YarnComponentM

WJ = "⁠"  # word joiner: invisible, stops a line being read as markup


def _plain(line: str) -> str:
    line = line.rstrip()
    if re.match(r"^(\s*[-*+]\s|#|---\s*$|```|_.*_\s*$|!\[)", line):
        return WJ + line
    return line


def _heading_case(raw: str) -> str:
    text = raw.strip().rstrip(":")
    return text[:1].upper() + text[1:].lower() if text else text


def _fmt_amounts(amounts: list[float], unit: str) -> str:
    def one(x: float) -> str:
        return str(int(x)) if float(x).is_integer() else str(x)

    return "-".join(one(a) for a in amounts) + f" {unit}" if amounts else ""


def _component_line(comp: YarnComponentM, links: bool) -> list[str]:
    group = f" (yarn group {comp.group})" if comp.group else ""
    name = f"[{comp.name}]({comp.product_url})" if links and comp.product_url else comp.name
    out = [f"- {name}{group}"]
    for col in comp.colours:
        bits = [b for b in [_fmt_amounts(col.amounts, col.unit), f"colour {col.number} {col.name}".strip() if col.number else col.name] if b]
        if bits:
            out.append(f"- {WJ}   " + ", ".join(bits))
    return out


def build_text_version(p: PatternData, recipe_id: str | None = None, links: bool = True) -> str:
    out: list[str] = []
    add = out.append

    add(f"# {p.title}")
    ident = " · ".join(x for x in [p.number, f"Pattern {p.designer_id}" if p.designer_id else "", p.hashtag] if x)
    if ident:
        add(ident)
    if p.source_url:
        add(f"[Open on DROPS Design]({p.source_url})" if links else f"Source: {p.source_url}")
    add("")
    if p.intro:
        add(_plain(p.intro))
        add("")

    if recipe_id and p.picture_pages:
        for page in p.picture_pages[:1]:
            add(f"![Pattern pictures](/api/recipes/{recipe_id}/pdf-pages/page-{page:03d}.jpg)")
        add("")

    if p.sizes:
        add("## Sizes")
        add(" · ".join(p.sizes))
        add("")

    if p.yarn_options:
        add("## Yarn")
        if p.yarn_group:
            add(f"Yarn group {p.yarn_group}")
        for i, opt in enumerate(p.yarn_options, start=1):
            if len(p.yarn_options) > 1:
                add(f"### Option {i}")
            for comp in opt.components:
                out.extend(_component_line(comp, links))
        add("")
    elif p.yarn_raw:
        add("## Yarn")
        out.extend(_plain(l) for l in p.yarn_raw)
        add("")

    if p.needles:
        add("## Needles")
        out.extend(f"- {l}" for l in p.needles)
        add("")

    if p.tension:
        add("## Tension")
        out.extend(_plain(l) for l in p.tension)
        add("")

    diagram_added = False
    for sec in p.body:
        head = sec.heading.strip()
        upper = head.upper()
        if upper == "EXPLANATIONS FOR THE PATTERN":
            add("## Explanations")
        elif upper == "START THE PIECE HERE":
            add("## Pattern")
        elif head:
            add(f"### {_heading_case(head)}")
        for line in sec.lines:
            add(_plain(line) if line else "")
        add("")

    if recipe_id and p.diagram_pages:
        add("## Charts and diagrams")
        for page in p.diagram_pages:
            add(f"![Chart on page {page}](/api/recipes/{recipe_id}/pdf-pages/page-{page:03d}.jpg)")
        add("")
    elif p.has_diagram_note:
        add("_The charts and diagrams are in the PDF._")
        add("")

    if p.videos:
        add("## Tutorial videos")
        for v in p.videos:
            dur = f" ({v.duration})" if v.duration else ""
            add(f"- [{v.title}]({v.url}){dur}" if links else f"- {v.title}{dur} {v.url}")
        add("")

    if p.lessons:
        add("## Lessons")
        for l in p.lessons:
            add(f"- [{l.title}]({l.url})" if links else f"- {l.title} {l.url}")
        add("")

    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"
