"""Importer against a REAL Knitting Library (patched) and a pretend DROPS. Prints what ended up in the library."""
import json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi.testclient import TestClient
from app.config import Settings
from app.drops.fetcher import DropsFetcher
from app.kl.client import KnittingLibrary
from app.main import create_app
from tests.conftest import drops_handler

KL = "http://127.0.0.1:8089"
c = httpx.Client(base_url=KL, timeout=60)
if c.get("/api/setup/status").json().get("setup_required"):
    tok = c.post("/api/setup/admin", json={"username": "jeff", "password": "a-long-test-password-1"}).json()["token"]
    c.post("/api/admin/users", json={"username": "importer", "password": "importer-pass-1234"}, headers={"X-Session-Token": tok})

s = Settings(kl_url=KL, kl_public_url="https://knit.wighttrash.uk", kl_username="importer", kl_password="importer-pass-1234",
             data_dir=Path(tempfile.mkdtemp()), drops_min_interval=0, chromium_path="/opt/pw-browsers/chromium")
app = create_app(s, fetcher=DropsFetcher(s, transport=httpx.MockTransport(drops_handler("ok"))))
H = {"X-Requested-With": "knit-import"}
with TestClient(app) as t:
    print("status:", t.get("/api/status").json())
    print("suggestions before:", t.get("/api/suggestions").json())
    d = t.post("/api/drafts", json={"url": "https://www.garnstudio.com/pattern.php?id=12759&cid=19"}, headers=H).json()
    for _ in range(120):
        d = t.get(f"/api/drafts/{d['id']}").json()
        if d["status"] in ("ready", "manual", "error"): break
        time.sleep(0.5)
    print("draft:", d["status"], d["pattern"]["title"])
    t.patch(f"/api/drafts/{d['id']}", json={"cover_page": 1}, headers=H)
    t.post(f"/api/drafts/{d['id']}/publish", json={}, headers=H)
    for _ in range(120):
        d = t.get(f"/api/drafts/{d['id']}").json()
        if d["publish"]["state"] in ("done", "error", "duplicate"): break
        time.sleep(0.5)
    print("publish:", d["publish"]["state"], [(x["key"], x["state"], x["detail"]) for x in d["publish"]["steps"]], d["publish"]["error"])
    rid = d["publish"]["recipe_id"]
    # second publish of the same pattern should be flagged as duplicate
    d2 = t.post("/api/drafts", json={"url": "https://www.garnstudio.com/pattern.php?id=12759&cid=19"}, headers=H).json()
    for _ in range(120):
        d2 = t.get(f"/api/drafts/{d2['id']}").json()
        if d2["status"] in ("ready", "manual", "error"): break
        time.sleep(0.5)
    t.post(f"/api/drafts/{d2['id']}/publish", json={}, headers=H)
    for _ in range(120):
        d2 = t.get(f"/api/drafts/{d2['id']}").json()
        if d2["publish"]["state"] in ("done", "error", "duplicate"): break
        time.sleep(0.5)
    print("second publish:", d2["publish"]["state"], d2["publish"].get("duplicates"))
    print("suggestions after:", t.get("/api/suggestions").json())

# look inside the library as Mary would
lt = c.post("/api/auth/login", json={"username": "importer", "password": "importer-pass-1234"}).json()["token"]
KH = {"X-Session-Token": lt}
r = c.get(f"/api/recipes/{rid}", headers=KH).json()
print("recipe:", r["id"], "| cats:", r.get("categories"), "| tags:", len(r.get("tags", [])), r.get("tags")[:5], "| thumb:", r.get("thumbnail") or r.get("has_thumbnail"))
tv = c.get(f"/api/recipes/{rid}/text-version", headers=KH).json()
md = tv.get("content_markdown", "")
print("text version chars:", len(md), "| first lines:", md.splitlines()[:6])
print("yarns:", [y["name"] for y in c.get("/api/yarns", headers=KH).json()])
