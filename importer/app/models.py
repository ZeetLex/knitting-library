"""Data shapes shared by the API, the draft store and the Knitting Library client."""
from __future__ import annotations

from pydantic import BaseModel, Field


class YarnColourM(BaseModel):
    number: str = ""
    name: str = ""
    amounts: list[float] = Field(default_factory=list)
    unit: str = "g"
    label: str = ""


class YarnComponentM(BaseModel):
    name: str
    group: str = ""
    slug: str = ""
    product_url: str = ""
    colours: list[YarnColourM] = Field(default_factory=list)


class YarnOptionM(BaseModel):
    components: list[YarnComponentM] = Field(default_factory=list)


class SectionM(BaseModel):
    heading: str = ""
    lines: list[str] = Field(default_factory=list)


class VideoM(BaseModel):
    id: str
    title: str
    duration: str = ""
    url: str


class LessonM(BaseModel):
    title: str
    url: str


class PatternData(BaseModel):
    """Everything read from DROPS. Read-only for the user; the Check stage edits `Edits` instead."""

    site_id: int | None = None
    cid: int | None = None
    source_url: str = ""
    title: str = ""
    number: str = ""
    designer_id: str = ""
    hashtag: str = ""
    intro: str = ""
    yarn_group: str = ""
    sizes: list[str] = Field(default_factory=list)
    yarn_options: list[YarnOptionM] = Field(default_factory=list)
    yarn_raw: list[str] = Field(default_factory=list)
    needles: list[str] = Field(default_factory=list)
    tension: list[str] = Field(default_factory=list)
    body: list[SectionM] = Field(default_factory=list)
    has_diagram_note: bool = False
    videos: list[VideoM] = Field(default_factory=list)
    lessons: list[LessonM] = Field(default_factory=list)
    language: str = ""
    craft: str = "knitting"
    page_count: int = 0
    picture_pages: list[int] = Field(default_factory=list)  # pages that hold photos (usually 1)
    diagram_pages: list[int] = Field(default_factory=list)  # pages that hold charts and diagrams
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    has_main_page: bool = False
    text_source: str = ""  # "print", "pdf"


class Edits(BaseModel):
    title: str = ""
    description: str = ""
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    cover_page: int = 1


class CreateDraft(BaseModel):
    url: str


class PatchDraft(BaseModel):
    title: str | None = None
    description: str | None = None
    categories: list[str] | None = None
    tags: list[str] | None = None
    cover_page: int | None = None


class PublishRequest(BaseModel):
    allow_duplicate: bool = False
