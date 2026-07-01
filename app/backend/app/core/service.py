"""Core application endpoints."""
from app.core.foundation import *

def health():
    return {"status": "ok"}

# ── Recipes ───────────────────────────────────────────────────────────────────


__all__ = [name for name in globals() if not name.startswith("__")]
