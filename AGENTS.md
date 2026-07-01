# Knitting Library Backend Guidance

The backend is split into a FastAPI package under `app/backend/app/`.
Keep `app/backend/main.py` as a tiny compatibility shim because Docker starts the
server with `uvicorn main:app`.

## Structure

- `app/backend/app/main.py` creates the FastAPI app, registers middleware,
  includes routers, attaches startup hooks, and wires static/frontend serving.
- Route registrations belong in focused `routes.py` files under `auth`,
  `recipes`, `yarns`, `inventory`, `ai`, `review`, `admin`, `releases`,
  `stats`, and `core`.
- Business logic belongs in the matching `service.py` module.
- Database connection, schema initialization, migrations, and shared persistence
  helpers belong under `db/`.
- SQL-heavy feature code should move toward feature `repository.py` modules.
- Recipe file, image, PDF, and thumbnail behavior belongs in `recipes/files.py`.

## Rules For Future Changes

- Do not grow `app/backend/main.py`; it should only expose `app`.
- Keep route files thin. Put validation/workflow code in services and SQL/file
  work in repositories or file helpers.
- Preserve public API paths, request bodies, response shapes, SQLite table and
  column names, `/data` and `/logs` paths, auth/session/CSRF behavior, security
  headers, upload validation, SSRF protection, and disabled FastAPI docs.
- Prefer behavior-preserving moves before style cleanup.

## Validation

Run at least:

```powershell
& 'C:\Users\Gamestation\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m compileall app\backend
docker build -t knitting-library-local:beta .
docker rm -f knitting-library-codex-preview
docker run -d --name knitting-library-codex-preview -p 18080:8080 -e PUID=0 -e PGID=0 -v "${PWD}\data:/data" -v "${PWD}\logs:/logs" knitting-library-local:beta
Invoke-WebRequest -Uri http://localhost:18080/api/health -UseBasicParsing
```
