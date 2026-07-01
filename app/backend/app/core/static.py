"""Static frontend and SPA fallback middleware."""
from app.core.foundation import *

_static_app = StaticFiles(directory=str(STATIC_DIR)) if STATIC_DIR.exists() else None

async def spa_static_middleware(request: Request, call_next):
    path = request.url.path

    # Always pass API and data requests to FastAPI's router
    if path.startswith("/api/") or path.startswith("/data/"):
        return await call_next(request)

    # Try to serve as a static file
    if _static_app is not None:
        static_path = path.lstrip("/") or "index.html"
        candidate = STATIC_DIR / static_path
        if candidate.is_file():
            resp = FileResponse(str(candidate))
            ct = resp.media_type or ""
            return _apply_security_headers(resp, is_html="text/html" in ct)

    # SPA fallback: return index.html for all other paths (React Router handles routing)
    index = STATIC_DIR / "index.html"
    if index.exists():
        resp = FileResponse(str(index), media_type="text/html")
        return _apply_security_headers(resp, is_html=True)

    return await call_next(request)

__all__ = [name for name in globals() if not name.startswith("__")]
