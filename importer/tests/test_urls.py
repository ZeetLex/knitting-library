import pytest

from app.drops.urls import BadLink, parse_pattern_link


@pytest.mark.parametrize(
    "text,site_id,cid",
    [
        ("https://www.garnstudio.com/pattern.php?id=12759&cid=19", 12759, 19),
        ("  garnstudio.com/pattern.php?id=12759  ", 12759, 19),  # no scheme, no cid: default
        ("https://www.garnstudio.com/pattern.php?id=12759&cid=17&utm_source=x", 12759, 17),
        ("https://www.garnstudio.com/includes/pattern-print.php?id=5&cid=12", 5, 12),
        ("https://garnstudio.com/pattern.php?id=7&cid=999", 7, 19),  # silly cid: default
    ],
)
def test_good_links(settings, text, site_id, cid):
    ref = parse_pattern_link(text, settings)
    assert (ref.site_id, ref.cid) == (site_id, cid)
    assert ref.print_url(settings.drops_base).endswith(f"pattern-print.php?id={site_id}&cid={cid}")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello",
        "https://example.com/pattern.php?id=1",
        "https://www.garnstudio.com/",
        "https://www.garnstudio.com/pattern.php",
        "https://www.garnstudio.com/pattern.php?id=abc",
        "https://www.garnstudio.com/pattern.php?id=-3",
        "https://garnstudio.com.evil.example/pattern.php?id=1",
        "https://images.garnstudio.com/pattern.php?id=1",
        "javascript:alert(1)",
    ],
)
def test_bad_links(settings, text):
    with pytest.raises(BadLink):
        parse_pattern_link(text, settings)
