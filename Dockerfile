# Dockerfile — single image for the knitting library app
#
# How it works:
#   Stage 1 (builder): Compiles the React frontend into static HTML/JS/CSS files
#   Stage 2 (final):   Runs both nginx (serves frontend) and uvicorn (runs backend API)
#                      using supervisord to manage both processes in one container
#
# The final image is based on Python+Alpine with nginx added on top.
# supervisord is a lightweight process manager that keeps both services running.

# ── Stage 1: Build the React frontend ────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (cached layer — only re-runs if package.json changes)
COPY app/frontend/package.json ./
RUN npm install --legacy-peer-deps && npm install ajv@^8.11.0 --legacy-peer-deps

# Copy frontend source and build it
COPY app/frontend/ .
RUN npm run build
# Result: /app/build/ contains the compiled React app


# ── Stage 2: Final image with Python backend + nginx ─────────────────────────
# python:3.12-alpine gives us a newer Alpine base with more recent apk packages,
# reducing the number of OS-level CVEs in poppler, busybox, nss, zlib etc.
FROM python:3.12-alpine3.21

LABEL org.opencontainers.image.source="https://github.com/ZeetLex/knitting-library"

# Install system dependencies:
#   nginx        - web server to serve the React frontend
#   poppler-utils - converts PDF pages to images
#   gcc/musl/etc - needed to compile Python packages on Alpine
# NOTE: supervisor is intentionally NOT installed via apk — the apk version
# carries CVE-2023-27482 (CVSS 10). We install it via pip instead (see below).
RUN apk add --no-cache \
    nginx \
    poppler-utils \
    gcc \
    musl-dev \
    zlib-dev \
    jpeg-dev \
    libffi-dev \
    && apk upgrade --no-cache

# ── Backend setup ─────────────────────────────────────────────────────────────
WORKDIR /app/backend

# Upgrade pip and wheel, then install all Python deps including supervisor
# (supervisor via pip is v4.2.5+ which is not affected by CVE-2023-27482)
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

COPY app/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/backend/ .

# ── Frontend setup ────────────────────────────────────────────────────────────
# Copy the compiled React app from Stage 1 into nginx's web root
COPY --from=builder /app/build /usr/share/nginx/html

# ── nginx config ─────────────────────────────────────────────────────────────
# Nginx listens on port 80, serves React files, and proxies /api/ to uvicorn
# which runs on port 8000 on the same container (localhost)
RUN rm -f /etc/nginx/http.d/default.conf
COPY app/frontend/nginx-single.conf /etc/nginx/http.d/default.conf

# ── supervisord config ────────────────────────────────────────────────────────
# supervisord starts and monitors both nginx and uvicorn
COPY supervisord.conf /etc/supervisord.conf

# Expose port 80 (nginx)
EXPOSE 80

# supervisord is installed via pip into /usr/local/bin/
CMD ["/usr/local/bin/supervisord", "-c", "/etc/supervisord.conf"]
