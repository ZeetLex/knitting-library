"""End to end through the HTTP API, with a pretend DROPS and a pretend Knitting Library."""
from __future__ import annotations

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.drops.fetcher import DropsFetcher
from app.kl.client import KnittingLibrary
from app.main import create_app
from tests.conftest import needs_fixtures, drops_handler
from tests.fakekl import FakeKL

pytestmark = needs_fixtures

H = {"X-Requested-With": "knit-import"}
LINK = "https://www.garnstudio.com/pattern.php?id=12759&cid=19"


def make_client(settings, drops_mode="ok", kl: FakeKL | None = None):
    kl = kl or FakeKL()
    fetcher = DropsFetcher(settings, transport=httpx.MockTransport(drops_handler(drops_mode)))
    app = create_app(settings, fetcher=fetcher, kl=KnittingLibrary(settings, transport=kl.transport()))
    return TestClient(app), kl


def wait_for(client, draft_id, until, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        data = client.get(f"/api/drafts/{draft_id}").json()
        if until(data):
            return data
        time.sleep(0.3)
    raise AssertionError(f"timed out; last state {data['status']} {data.get('manual')}")


def test_changes_need_the_header(settings):
    client, _ = make_client(settings)
    with client:
        assert client.post("/api/drafts", json={"url": LINK}).status_code == 403
        assert client.get("/api/health").json() == {"ok": True}


def test_bad_links_get_friendly_messages(settings):
    client, _ = make_client(settings)
    with client:
        r = client.post("/api/drafts", json={"url": "https://example.com/x"}, headers=H)
        assert r.status_code == 422 and "garnstudio" in r.json()["detail"]
        r = client.post("/api/drafts", json={"url": ""}, headers=H)
        assert r.status_code == 422


def test_link_route_then_publish(settings):
    client, kl = make_client(settings)
    with client:
        d = client.post("/api/drafts", json={"url": LINK}, headers=H).json()
        data = wait_for(client, d["id"], lambda x: x["status"] in ("ready", "manual", "error"))
        assert data["status"] == "ready", data
        assert data["pattern"]["title"] == "Sage Leaf Sweater"
        assert data["pattern"]["page_count"] == 5
        assert "Jumpers" in data["edits"]["categories"]
        assert "raglan" in data["edits"]["tags"]

        # page picture and pdf
        assert client.get(f"/api/drafts/{d['id']}/pages/1.jpg").headers["content-type"] == "image/jpeg"
        assert client.get(f"/api/drafts/{d['id']}/pages/9.jpg").status_code == 404
        assert client.get(f"/api/drafts/{d['id']}/pdf").content[:5] == b"%PDF-"
        assert "Sage Leaf Sweater" in client.get(f"/api/drafts/{d['id']}/text").json()["markdown"]

        # edit
        r = client.patch(f"/api/drafts/{d['id']}", json={"tags": ["raglan", "Raglan", "cosy, warm"], "cover_page": 99, "title": "  Sage   Leaf  "}, headers=H)
        e = r.json()["edits"]
        assert e["tags"] == ["raglan", "cosy warm"]
        assert e["cover_page"] == 5
        assert e["title"] == "Sage Leaf"

        # publish
        client.patch(f"/api/drafts/{d['id']}", json={"cover_page": 5}, headers=H)
        client.post(f"/api/drafts/{d['id']}/publish", json={}, headers=H)
        data = wait_for(client, d["id"], lambda x: (x["publish"] or {}).get("state") in ("done", "error", "duplicate"))
        assert data["publish"]["state"] == "done", data["publish"]
        assert [s["state"] for s in data["publish"]["steps"]] == ["done"] * 5
        rid = data["publish"]["recipe_id"]
        assert kl.recipes[rid]["thumb"] == {"source": "pdf_page", "filename": "page-005.jpg"}
        assert "## " in kl.recipes[rid]["text"]["content_markdown"]
        assert any("DROPS ALPACA" in y["name"].upper() for y in kl.yarns.values())
        assert kl.logins == 1


def test_duplicate_then_add_anyway(settings):
    client, kl = make_client(settings, kl=FakeKL(duplicate=True))
    with client:
        d = client.post("/api/drafts", json={"url": LINK}, headers=H).json()
        wait_for(client, d["id"], lambda x: x["status"] == "ready")
        client.post(f"/api/drafts/{d['id']}/publish", json={}, headers=H)
        data = wait_for(client, d["id"], lambda x: (x["publish"] or {}).get("state") in ("done", "error", "duplicate"))
        assert data["publish"]["state"] == "duplicate"
        assert data["publish"]["duplicates"]["content"][0]["title"] == "Old copy"
        assert not kl.recipes
        client.post(f"/api/drafts/{d['id']}/publish", json={"allow_duplicate": True}, headers=H)
        data = wait_for(client, d["id"], lambda x: (x["publish"] or {}).get("state") in ("done", "error"))
        assert data["publish"]["state"] == "done"
        assert len(kl.recipes) == 1


def test_publish_failure_can_be_resumed(settings):
    kl = FakeKL(fail_text=True)
    client, _ = make_client(settings, kl=kl)
    with client:
        d = client.post("/api/drafts", json={"url": LINK}, headers=H).json()
        wait_for(client, d["id"], lambda x: x["status"] == "ready")
        client.post(f"/api/drafts/{d['id']}/publish", json={}, headers=H)
        data = wait_for(client, d["id"], lambda x: (x["publish"] or {}).get("state") in ("done", "error"))
        assert data["publish"]["state"] == "error"
        assert data["publish"]["recipe_id"]
        kl.fail_text = False
        client.post(f"/api/drafts/{d['id']}/publish", json={}, headers=H)
        data = wait_for(client, d["id"], lambda x: (x["publish"] or {}).get("state") in ("done", "error"))
        assert data["publish"]["state"] == "done"
        assert len(kl.recipes) == 1  # not added twice


@pytest.mark.parametrize("mode,code", [("blocked", "refused"), ("challenge", "challenge"), ("noprint", "refused")])
def test_blocked_link_falls_back_to_manual(settings, mode, code):
    client, _ = make_client(settings, drops_mode=mode)
    with client:
        d = client.post("/api/drafts", json={"url": LINK}, headers=H).json()
        data = wait_for(client, d["id"], lambda x: x["status"] in ("ready", "manual", "error"))
        assert data["status"] == "manual"
        assert data["manual"]["code"] == code
        assert data["links"]["pattern"] == LINK
        assert any(s["state"] == "failed" for s in data["progress"])


def test_not_found_is_an_error_not_manual(settings):
    client, _ = make_client(settings, drops_mode="notfound")
    with client:
        d = client.post("/api/drafts", json={"url": LINK}, headers=H).json()
        data = wait_for(client, d["id"], lambda x: x["status"] in ("ready", "manual", "error"))
        assert data["status"] == "error"
        assert data["error"]["code"] == "not_found"


def test_manual_route_with_checks(settings, pdf_bytes, main_html_bytes, print_html_bytes):
    client, kl = make_client(settings, drops_mode="blocked")
    with client:
        d = client.post("/api/drafts/manual", headers=H).json()
        assert d["status"] == "manual"
        did = d["id"]

        def upload(name, data, mime="application/octet-stream"):
            return client.post(f"/api/drafts/{did}/files", files=[("files", (name, data, mime))], headers=H).json()

        # rubbish
        r = upload("notes.txt", b"hello there")
        assert r["accepted"] == [] and r["rejected"][0]["verdict"]["headline"]
        # the print page by mistake
        r = upload("print.html", print_html_bytes, "text/html")
        assert r["accepted"] == [] and "print page" in r["rejected"][0]["verdict"]["headline"].lower()
        # not a pdf
        r = upload("fake.pdf", b"%PDF-1.4 not really", "application/pdf")
        assert r["accepted"] == []
        # the real page
        r = upload("page.html", main_html_bytes, "text/html")
        assert r["accepted"][0]["verdict"]["kind"] == "main_html"
        assert r["status"] == "manual"
        # the real pdf
        r = upload("Sage.pdf", pdf_bytes, "application/pdf")
        assert r["accepted"][0]["verdict"]["kind"] == "pdf"
        assert r["status"] == "ready"
        assert r["pattern"]["title"] == "Sage Leaf Sweater"
        assert r["edits"]["tags"] and "raglan" in r["edits"]["tags"]
        assert r["pattern"]["videos"]


def test_manual_pdf_only_still_works(settings, pdf_bytes):
    client, _ = make_client(settings)
    with client:
        did = client.post("/api/drafts/manual", headers=H).json()["id"]
        r = client.post(f"/api/drafts/{did}/files", files=[("files", ("a.pdf", pdf_bytes, "application/pdf"))], headers=H).json()
        assert r["status"] == "ready"
        assert r["pattern"]["title"] == "Sage Leaf Sweater"
        assert r["edits"]["categories"] == [] or isinstance(r["edits"]["categories"], list)


def test_two_files_in_one_drop(settings, pdf_bytes, main_html_bytes):
    client, _ = make_client(settings)
    with client:
        did = client.post("/api/drafts/manual", headers=H).json()["id"]
        files = [("files", ("p.html", main_html_bytes, "text/html")), ("files", ("a.pdf", pdf_bytes, "application/pdf"))]
        r = client.post(f"/api/drafts/{did}/files", files=files, headers=H).json()
        assert len(r["accepted"]) == 2 and r["status"] == "ready"
        assert r["edits"]["tags"]


def test_retry_after_block(settings):
    client, _ = make_client(settings, drops_mode="blocked")
    with client:
        d = client.post("/api/drafts", json={"url": LINK}, headers=H).json()
        wait_for(client, d["id"], lambda x: x["status"] == "manual")
        r = client.post(f"/api/drafts/{d['id']}/retry", headers=H)
        assert r.status_code == 200 and r.json()["status"] == "working"


def test_unknown_draft(settings):
    client, _ = make_client(settings)
    with client:
        assert client.get("/api/drafts/0123456789abcdef").status_code == 404
        assert client.get("/api/drafts/../../etc").status_code in (404, 405)
