"""Reading and validating DROPS pattern links."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from app.config import Settings


class BadLink(ValueError):
    """The text pasted is not a usable DROPS pattern link. The message is safe to show to the user."""


@dataclass(frozen=True)
class PatternRef:
    site_id: int
    cid: int

    def main_url(self, base: str) -> str:
        return f"{base}/pattern.php?id={self.site_id}&cid={self.cid}"

    def print_url(self, base: str) -> str:
        return f"{base}/includes/pattern-print.php?id={self.site_id}&cid={self.cid}"


def parse_pattern_link(text: str, settings: Settings) -> PatternRef:
    raw = (text or "").strip()
    if not raw:
        raise BadLink("Paste the link to a DROPS pattern first.")
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        raise BadLink("That does not look like a link.") from None
    host = (parsed.hostname or "").lower()
    if host not in settings.drops_hosts or host in settings.drops_image_hosts:
        raise BadLink("That link is not from garnstudio.com. Open a pattern on the DROPS website and copy its link.")

    path = parsed.path.lower()
    if not (path.endswith("/pattern.php") or path.endswith("/pattern-print.php")):
        raise BadLink(
            "That is a DROPS page, but not a single pattern. Open the pattern itself, then copy the link from the address bar."
        )
    query = parse_qs(parsed.query)
    try:
        site_id = int(query.get("id", [""])[0])
    except ValueError:
        raise BadLink("The link has no pattern number in it. Copy it again from the address bar.") from None
    if site_id <= 0:
        raise BadLink("The link has no pattern number in it. Copy it again from the address bar.")
    try:
        cid = int(query.get("cid", [""])[0])
    except ValueError:
        cid = settings.drops_default_cid
    if not 1 <= cid <= 99:
        cid = settings.drops_default_cid
    return PatternRef(site_id=site_id, cid=cid)
