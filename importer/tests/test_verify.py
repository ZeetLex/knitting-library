"""The checks that tell Mary whether a hand-saved file is right."""
from pathlib import Path

from app.drops.verify import Expect, verify_html, verify_pdf



def test_real_pdf_passes(tmp_path, pdf_bytes):
    f = tmp_path / "a.pdf"
    f.write_bytes(pdf_bytes)
    v = verify_pdf(f, 50)
    assert v.ok and v.kind == "pdf" and v.title == "Sage Leaf Sweater" and v.page_count == 5
    assert all(c.state != "fail" for c in v.checks)


def test_pdf_wrong_pattern_is_refused(tmp_path, pdf_bytes):
    f = tmp_path / "a.pdf"
    f.write_bytes(pdf_bytes)
    v = verify_pdf(f, 50, Expect(number="DROPS 100-1"))
    assert not v.ok and "different pattern" in v.headline.lower()


def test_pdf_too_big(tmp_path, pdf_bytes):
    f = tmp_path / "a.pdf"
    f.write_bytes(pdf_bytes)
    v = verify_pdf(f, 0)  # limit of 0 MB
    assert not v.ok and "too big" in v.headline.lower()


def test_not_a_pdf(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"just words")
    v = verify_pdf(f, 50)
    assert not v.ok and "not a pdf" in v.headline.lower()


def test_pdf_without_text(tmp_path):
    # A real PDF with no text: made from a blank page by Chromium would need a browser, so use poppler's smallest valid file.
    f = tmp_path / "blank.pdf"
    f.write_bytes(
        b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"trailer<</Root 1 0 R/Size 4>>\n%%EOF\n"
    )
    v = verify_pdf(f, 50)
    assert not v.ok


def test_main_page_passes(main_html_bytes):
    v = verify_html(main_html_bytes.decode())
    assert v.ok and v.kind == "main_html" and v.site_id == 12759
    labels = {c.label: c.state for c in v.checks}
    assert labels["Tags found"] == "ok" and labels["Tutorial videos found"] == "ok"


def test_print_page_is_rejected_with_advice(print_html_bytes):
    v = verify_html(print_html_bytes.decode())
    assert not v.ok and v.kind == "print_html" and v.advice


def test_challenge_page_is_rejected():
    v = verify_html("<html><title>Just a moment...</title><body>Checking your browser</body></html>")
    assert not v.ok and "security check" in v.headline.lower()


def test_random_text_is_rejected():
    assert not verify_html("hello there").ok


def test_wrong_site_id_is_refused(main_html_bytes):
    v = verify_html(main_html_bytes.decode(), Expect(site_id=1))
    assert not v.ok and "different pattern" in v.headline.lower()
