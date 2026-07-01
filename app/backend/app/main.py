"""FastAPI application assembly for Knitting Recipe Library."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.service_registry import wire_services
from app.admin.routes import router as admin_router
from app.ai.routes import router as ai_router
from app.auth.routes import router as auth_router
from app.core.routes import router as core_router
from app.inventory.routes import router as inventory_router
from app.recipes.routes import router as recipes_router
from app.releases.routes import router as releases_router
from app.review.routes import router as review_router
from app.stats.routes import router as stats_router
from app.yarns.routes import router as yarns_router
from app.core import config, security, static
from app.ai import service as ai_service


wire_services()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Knitting Recipe Library",
        # Disable the auto-generated docs endpoints in production.
        # They expose route names and models to anyone who can reach the server.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.middleware("http")(security.security_headers)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config._ALLOWED_ORIGINS,   # empty = same-origin only
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Session-Token", "X-CSRF-Token"],
    )
    app.middleware("http")(security.redact_request_url_for_logs)
    app.middleware("http")(security.csrf_cookie_guard)

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(core_router)
    app.include_router(recipes_router)
    app.include_router(ai_router)
    app.include_router(review_router)
    app.include_router(yarns_router)
    app.include_router(inventory_router)
    app.include_router(releases_router)
    app.include_router(stats_router)

    app.on_event("startup")(ai_service._resume_ai_queue_on_startup)
    app.middleware("http")(static.spa_static_middleware)
    return app


app = create_app()
