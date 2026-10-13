"""Reading the saved DROPS pages (private fixtures: a single pattern kept for testing only)."""
from app.drops.build import build_pattern
from app.drops.parser import parse_main_page, parse_print_page
from app.drops.pattern_text import parse_pattern_text
from app.drops.urls import PatternRef
from tests.conftest import needs_fixtures, FIX


pytestmark = needs_fixtures


def test_main_page_fields(main_html_bytes):
    m = parse_main_page(main_html_bytes.decode())
    assert m.usable and m.site_id == 12759 and m.title == "Sage Leaf Sweater"
    assert "raglan" in m.tags and "top down" in m.tags
    assert [l for l, _ in m.breadcrumb][1:3] == ["Women", "Jumpers"]
    assert len(m.videos) == 21 and all(v.url.startswith("https://www.garnstudio.com/") for v in m.videos)


def test_print_page_text(print_html_bytes):
    pr = parse_print_page(print_html_bytes.decode())
    t = parse_pattern_text(pr.lines)
    assert t.title == "Sage Leaf Sweater"
    assert t.sizes == ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
    assert len(t.yarn_options) == 2  # Alpaca + Kid-Silk, or Baby Merino + Kid-Silk
    assert any(s.heading.startswith("YOKE") for s in t.body)
    # a size run stays intact
    text = "\n".join(l for s in t.body for l in s.lines)
    assert "92-92-96-96-104-108-112 stitches" in text


def test_build_pattern_from_all_three_files(settings):
    pattern, edits = build_pattern(
        settings=settings, ref=PatternRef(12759, 19),
        main_html=(FIX / "main.html").read_text(encoding="utf-8"),
        print_html=(FIX / "print.html").read_text(encoding="utf-8"),
        pdf_path=FIX / "reference-chrome-print.pdf",
    )
    assert pattern.page_count == 5 and pattern.has_main_page
    assert edits.categories == ["Women", "Jumpers"] and "raglan" in edits.tags
    names = {c.name for o in pattern.yarn_options for c in o.components}
    assert {"DROPS Alpaca", "DROPS Kid-Silk", "DROPS Baby Merino"} <= names
