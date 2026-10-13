"""Shared test set-up: a pretend DROPS website that serves the saved fixture pages."""
from __future__ import annotations

import urllib.parse
from pathlib import Path

import httpx
import pytest

from app.config import Settings

FIX = Path(__file__).parent / "fixtures"
CHROMIUM = "/opt/pw-browsers/chromium"


def drops_handler(mode: str = "ok"):
    """mode: ok | blocked | notfound | challenge | noprint"""

    def handler(request: httpx.Request) -> httpx.Response:
        url = request.url
        path = url.path
        if mode == "blocked":
            return httpx.Response(403, text="Forbidden")
        if mode == "challenge":
            return httpx.Response(200, text="<html><title>Just a moment...</title><body>Checking your browser</body></html>")
        if path.endswith("/pattern.php"):
            if mode == "notfound" or url.params.get("id") != "12759":
                return httpx.Response(404, text="nope")
            return httpx.Response(200, text=(FIX / "main.html").read_text(encoding="utf-8"), headers={"content-type": "text/html; charset=utf-8"})
        if path.endswith("/pattern-print.php"):
            if mode == "noprint":
                return httpx.Response(403, text="Forbidden")
            return httpx.Response(200, text=(FIX / "print.html").read_text(encoding="utf-8"), headers={"content-type": "text/html; charset=utf-8"})
        name = urllib.parse.unquote(path.rsplit("/", 1)[-1])
        f = FIX / "print_files" / name
        if f.is_file():
            ctype = {"jpg": "image/jpeg", "svg": "image/svg+xml", "css": "text/css"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
            return httpx.Response(200, content=f.read_bytes(), headers={"content-type": ctype})
        return httpx.Response(404, text="missing")

    return handler


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        kl_url="http://kl.test",
        kl_public_url="https://knit.example",
        kl_password="pw",
        data_dir=tmp_path / "data",
        drops_min_interval=0.0,
        chromium_path=CHROMIUM,
    )


HAVE_FIXTURES = (FIX / "main.html").exists() and (FIX / "print.html").exists() and (FIX / "reference-chrome-print.pdf").exists()
needs_fixtures = pytest.mark.skipif(
    not HAVE_FIXTURES,
    reason="tests/fixtures holds a saved DROPS pattern. It is DROPS material, so it is not kept in the public repository.",
)


def _fixture_bytes(name: str) -> bytes:
    if not HAVE_FIXTURES:
        pytest.skip("saved DROPS fixtures are not present")
    return (FIX / name).read_bytes()


@pytest.fixture
def pdf_bytes() -> bytes:
    return _fixture_bytes("reference-chrome-print.pdf")


@pytest.fixture
def main_html_bytes() -> bytes:
    return _fixture_bytes("main.html")


@pytest.fixture
def print_html_bytes() -> bytes:
    return _fixture_bytes("print.html")
