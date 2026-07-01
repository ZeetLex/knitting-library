"""SQLite schema initialization."""
from app.core.foundation import init_db

__all__ = [name for name in globals() if not name.startswith("__")]
