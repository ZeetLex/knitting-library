"""Deployment paths shared by the server and CLI, without startup side effects."""
import os
from pathlib import Path


def _environment_path(name: str, default: str) -> Path:
    value = os.environ.get(name, "").strip()
    if not value:
        return Path(default)
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path (received {value!r})")
    return path


DATA_ROOT = _environment_path("KNITTING_DATA_DIR", "/data")
LOG_DIR = _environment_path("KNITTING_LOG_DIR", "/logs")
STATIC_DIR = _environment_path("KNITTING_STATIC_DIR", "/app/frontend/build")
DATA_DIR = DATA_ROOT / "recipes"
YARN_DIR = DATA_ROOT / "yarns"
DB_PATH = DATA_ROOT / "recipes.db"
BRANDING_DIR = DATA_ROOT / "branding"


def ensure_data_directories() -> None:
    for directory in (DATA_DIR, YARN_DIR):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Cannot create data directory {directory}: {exc}") from exc


__all__ = [
    "DATA_ROOT", "LOG_DIR", "STATIC_DIR", "DATA_DIR", "YARN_DIR", "DB_PATH",
    "BRANDING_DIR", "ensure_data_directories",
]
