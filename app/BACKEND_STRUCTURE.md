# Backend Structure Reference

Functionality preservation is priority ONE. This refactor moved the old single-file backend into feature modules without changing public API paths, request/response shapes, SQLite table or column names, auth/session/CSRF behavior, upload validation, `/data` and `/logs` paths, security headers, or static frontend serving.

## App startup

- `backend/main.py` is the Docker and `uvicorn main:app` compatibility shim.
- `backend/app/main.py` builds the FastAPI app, registers middleware, includes routers, wires service modules, starts background hooks, and serves the frontend.
- `backend/app/service_registry.py` imports the split service modules and shares cross-domain symbols needed by behavior-preserving moved code.

## Shared infrastructure

- `backend/app/core/foundation.py` contains shared imports, runtime constants, security helpers, DB initialization, auth dependencies, release-sync helpers, and other foundation code used by several domains.
- `backend/app/core/config.py` re-exports runtime paths and environment-backed settings.
- `backend/app/core/security.py` contains HTTP security, CSRF, proxy, upload magic-byte, and SSRF/public URL validation helpers.
- `backend/app/core/logging.py` contains auth and user-action logging helpers.
- `backend/app/core/static.py` serves the built frontend and SPA fallback.
- `backend/app/db/connection.py`, `backend/app/db/schema.py`, and `backend/app/db/migrations.py` point to the SQLite connection, schema setup, and migration helpers.

## Feature areas

- Authentication and account endpoints: `backend/app/auth/service.py`; FastAPI dependencies are in `backend/app/auth/dependencies.py`.
- Admin users, logs, mail settings, AI settings, admin 2FA, and announcements: `backend/app/admin/service.py`.
- Recipe list/detail/CRUD, taxonomy, project sessions, annotations, imports, and exports: `backend/app/recipes/repository.py`, surfaced through `backend/app/recipes/service.py`.
- Recipe files, images, PDFs, thumbnails, downloads, and text-version storage: `backend/app/recipes/files.py`.
- AI settings, OCR, text generation, chart extraction, work queue, and startup queue resume: `backend/app/ai/service.py`.
- AI review sessions, review assets, diagrams, legends, and chart review endpoints: `backend/app/review/service.py`.
- Yarn catalogue, colour variants, images, and URL scraping: `backend/app/yarns/service.py`.
- Inventory CRUD, stock adjustments, and inventory logs: `backend/app/inventory/service.py`.
- Stats and AI usage reset: `backend/app/stats/service.py`.
- GitHub release listing, dismissal, and manual sync: `backend/app/releases/service.py`.

## Routes

Each feature `routes.py` owns API path registration for that area and imports its local `service.py`. Keep route files thin: request routing belongs there, workflow belongs in service modules, SQL-heavy code belongs in repositories, and recipe file/PDF/image behavior belongs in `recipes/files.py`.

## When changing code

- Preserve behavior first; prefer moving code before cleaning style.
- Do not rename API paths, request bodies, response fields, database tables, or columns unless a separate migration explicitly requires it.
- Keep new helpers near the feature that owns them. Only move helpers into shared/core modules when multiple features genuinely need them.
- Avoid growing `services.py`; it is a temporary compatibility facade, not a place for new behavior.
