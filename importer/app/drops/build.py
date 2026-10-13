"""Putting the parsed pieces together into one PatternData plus suggested edits."""
from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.drops.parser import MainPage, PrintPage, parse_main_page, parse_print_page
from app.drops.pattern_text import PatternText, parse_pattern_text
from app.drops.pdfinfo import PdfFacts, inspect_pdf
from app.drops.taxonomy import build_taxonomy, craft_of
from app.drops.text import pdf_to_text, reflow_pdf_text
from app.drops.urls import PatternRef
from app.models import (
    Edits,
    LessonM,
    PatternData,
    SectionM,
    VideoM,
    YarnColourM,
    YarnComponentM,
    YarnOptionM,
)


class NotAPattern(ValueError):
    """The material given could not be read as a DROPS pattern."""


def _yarn_models(text: PatternText, cid: int, base: str) -> list[YarnOptionM]:
    options: list[YarnOptionM] = []
    for opt in text.yarn_options:
        comps = []
        for comp in opt.components:
            comps.append(
                YarnComponentM(
                    name=comp.name,
                    group=comp.group,
                    slug=comp.slug,
                    product_url=f"{base}/yarn.php?show={comp.slug}&cid={cid}",
                    colours=[
                        YarnColourM(number=c.number, name=c.name, amounts=c.amounts, unit=c.unit, label=c.label)
                        for c in comp.colours
                    ],
                )
            )
        options.append(YarnOptionM(components=comps))
    return options


def build_pattern(
    *,
    settings: Settings,
    ref: PatternRef | None,
    main_html: str | None,
    print_html: str | None,
    pdf_path: Path | None,
) -> tuple[PatternData, Edits]:
    main: MainPage | None = None
    if main_html:
        parsed = parse_main_page(main_html)
        main = parsed if parsed.usable else None

    printed: PrintPage | None = None
    if print_html:
        p = parse_print_page(print_html, settings.drops_base)
        printed = p if p.usable else None

    facts: PdfFacts | None = inspect_pdf(pdf_path) if pdf_path else None

    text_source = ""
    lines: list[str] = []
    if printed:
        lines = printed.lines
        text_source = "print"
    elif pdf_path and facts and facts.ok:
        lines = reflow_pdf_text(pdf_to_text(pdf_path))
        text_source = "pdf"
    if not lines:
        raise NotAPattern("No readable pattern text was found.")

    text = parse_pattern_text(lines)
    if not text.title and main:
        text.title = main.title
    if not text.title:
        raise NotAPattern("Could not find a pattern title.")
    if not text.number and main:
        text.number = main.number

    site_id = main.site_id if main and main.site_id else (ref.site_id if ref else None)
    cid = main.cid if main and main.cid else (ref.cid if ref else settings.drops_default_cid)
    source_url = ""
    if main and main.canonical:
        source_url = main.canonical
    elif site_id:
        source_url = PatternRef(site_id, cid or settings.drops_default_cid).main_url(settings.drops_base)

    categories, tags, notes = build_taxonomy(main, text)

    data = PatternData(
        site_id=site_id,
        cid=cid,
        source_url=source_url,
        title=text.title,
        number=text.number,
        designer_id=text.designer_id,
        hashtag=text.hashtag,
        intro=text.intro or (main.description if main else ""),
        yarn_group=text.yarn_group,
        sizes=text.sizes,
        yarn_options=_yarn_models(text, cid or settings.drops_default_cid, settings.drops_base),
        yarn_raw=text.yarn_raw,
        needles=text.needles,
        tension=text.tension,
        body=[SectionM(heading=s.heading, lines=s.lines) for s in text.body],
        has_diagram_note=text.has_diagram_note,
        videos=[VideoM(id=v.id, title=v.title, duration=v.duration, url=v.url) for v in (main.videos if main else [])],
        lessons=[LessonM(title=l.title, url=l.url) for l in (main.lessons if main else [])],
        language=main.language if main else "",
        craft=craft_of(main, text),
        page_count=facts.pages if facts else 0,
        picture_pages=facts.picture_pages if facts else [],
        diagram_pages=facts.diagram_pages if facts else [],
        warnings=list(text.warnings),
        notes=notes,
        has_main_page=main is not None,
        text_source=text_source,
    )

    title = f"{data.title} ({data.number})" if data.number else data.title
    desc_parts = [data.intro.strip()] if data.intro.strip() else []
    ident = " · ".join(x for x in [data.number, f"Pattern {data.designer_id}" if data.designer_id else ""] if x)
    if ident:
        desc_parts.append(ident)
    if source_url:
        desc_parts.append(f"Source: {source_url}")
    edits = Edits(
        title=title,
        description="\n".join(desc_parts),
        categories=categories,
        tags=tags,
        cover_page=1,
    )
    return data, edits
