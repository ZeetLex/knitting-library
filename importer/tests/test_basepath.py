"""The importer works at the root of its own hostname and under /import on the library's hostname."""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import STATIC, create_app


def client(settings, base="/import"):
    return TestClient(create_app(replace(settings, base_path=base)), follow_redirects=False)


def test_page_and_api_work_with_and_without_the_prefix(settings):
    c = client(settings)
    for prefix in ("", "/import"):
        assert c.get(f"{prefix}/").status_code == 200
        assert c.get(f"{prefix}/app.js").status_code == 200
        assert c.get(f"{prefix}/app.css").status_code == 200
        assert c.get(f"{prefix}/api/health").json()["ok"] is True


def test_prefix_without_slash_redirects_and_keeps_the_query(settings):
    r = client(settings).get("/import?x=1")
    assert r.status_code == 308
    assert r.headers["location"] == "/import/?x=1"


def test_changes_still_need_the_header_under_the_prefix(settings):
    c = client(settings)
    assert c.post("/import/api/drafts", json={"url": "x"}).status_code == 403


def test_prefix_can_be_switched_off(settings):
    c = client(settings, base="")
    assert c.get("/import/api/health").status_code == 404
    assert c.get("/api/health").status_code == 200


def test_other_prefix_names_are_not_swallowed(settings):
    assert client(settings).get("/important/api/health").status_code == 404


def test_page_only_uses_relative_addresses():
    """A leading slash would break the page when it sits under /import."""
    html = (STATIC / "index.html").read_text()
    assert not re.search(r'(?:href|src)="/', html)
    js = (STATIC / "app.js").read_text()
    assert not re.search(r"""(?:fetch|api)\(\s*["'`]/|src:\s*[`"']/""", js)
    assert "`/api/" not in js and '"/api/' not in js


def test_status_gives_the_address_for_the_back_link(settings):
    # The library itself is not running in this test, so only the address is checked.
    body = client(settings).get("/import/api/status").json()
    assert body["library_url"] == "https://knit.example"
    assert 'id="back"' in (STATIC / "index.html").read_text()
