"""Settings, read once from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Knitting Library (reached over the Docker network, never through Pangolin)
    kl_url: str = "http://knitting-library:8080"
    kl_public_url: str = ""
    kl_username: str = "importer"
    kl_password: str = ""

    # Storage
    data_dir: Path = Path("/data")
    draft_ttl_hours: int = 24
    max_upload_mb: int = 50

    # DROPS
    drops_base: str = "https://www.garnstudio.com"
    drops_image_hosts: tuple[str, ...] = ("images.garnstudio.com",)
    drops_default_cid: int = 19  # English (UK, cm, grams)
    drops_min_interval: float = 3.0  # seconds between requests to DROPS
    drops_contact: str = ""
    drops_cache_hours: int = 24
    drops_fetch_enabled: bool = True

    # PDF rendering for the "paste a link" route
    chromium_path: str = "/usr/bin/chromium"

    # Extra hosts allowed in test setups
    extra_allowed_hosts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def user_agent(self) -> str:
        contact = f"; {self.drops_contact}" if self.drops_contact else ""
        return f"KnitImport/0.1 (personal household use, one pattern per click{contact})"

    @property
    def drops_host(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.drops_base).hostname or "www.garnstudio.com"

    @property
    def drops_hosts(self) -> set[str]:
        host = self.drops_host
        hosts = {host, *self.drops_image_hosts, *self.extra_allowed_hosts}
        if host.startswith("www."):
            hosts.add(host[4:])
        return hosts

    @property
    def public_url(self) -> str:
        return (self.kl_public_url or self.kl_url).rstrip("/")


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        kl_url=env("KL_URL", "http://knitting-library:8080").rstrip("/"),
        kl_public_url=env("KL_PUBLIC_URL", "").rstrip("/"),
        kl_username=env("KL_USERNAME", "importer"),
        kl_password=env("KL_PASSWORD", ""),
        data_dir=Path(env("DATA_DIR", "/data")),
        draft_ttl_hours=int(env("DRAFT_TTL_HOURS", "24")),
        max_upload_mb=int(env("MAX_UPLOAD_MB", "50")),
        drops_base=env("DROPS_BASE", "https://www.garnstudio.com").rstrip("/"),
        drops_image_hosts=tuple(
            h.strip() for h in env("DROPS_IMAGE_HOSTS", "images.garnstudio.com").split(",") if h.strip()
        ),
        drops_default_cid=int(env("DROPS_DEFAULT_CID", "19")),
        drops_min_interval=float(env("DROPS_MIN_INTERVAL", "3.0")),
        drops_contact=env("DROPS_CONTACT", ""),
        drops_cache_hours=int(env("DROPS_CACHE_HOURS", "24")),
        drops_fetch_enabled=_bool("DROPS_FETCH_ENABLED", True),
        chromium_path=env("CHROMIUM_PATH", "/usr/bin/chromium"),
        extra_allowed_hosts=tuple(h.strip() for h in env("EXTRA_ALLOWED_HOSTS", "").split(",") if h.strip()),
    )
