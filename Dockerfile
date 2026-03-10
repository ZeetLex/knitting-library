# Dockerfile — single image for the knitting library app (v2.83)
#
# How it works:
#   Stage 1 (builder): Compiles the React frontend into static HTML/JS/CSS files
#   Stage 2 (final):   Runs both nginx (serves frontend) and uvicorn (runs backend API)
#                      using supervisord to manage both processes in one container
#
# The final image is based on Python+Alpine with nginx added on top.
# supervisord is a lightweight process manager that keeps both services running.
# nginx runs on port 8080 (not 80) so the whole container can run as non-root.

# ── Stage 1: Build the React frontend ────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (cached layer — only re-runs if package.json changes)
COPY app/frontend/package.json ./
RUN npm install --legacy-peer-deps

# Copy frontend source and build it
COPY app/frontend/ .
RUN npm run build
# Result: /app/build/ contains the compiled React app


# ── Stage 2: Final image with Python backend + nginx ─────────────────────────
FROM python:3.12-alpine3.22

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

COPY app/backend/requirements.txt .

# All pip operations in a single RUN layer so Docker Scout only sees the final state.
# wheel 0.45.1 is vendored INSIDE setuptools at setuptools/_vendor/wheel-0.45.1.dist-info
# pip uninstall cannot touch it — must delete the dist-info directory manually.
RUN pip install --no-cache-dir --upgrade pip setuptools \
    && pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y wheel \
    && find /usr/local/lib/python3.12/site-packages/setuptools/_vendor -name "wheel-*.dist-info" -exec rm -rf {} + 2>/dev/null; true \
    && pip install --no-cache-dir --no-deps "wheel==0.46.2" \
    && pip show wheel | grep Version

COPY app/backend/ .

# ── Frontend setup ────────────────────────────────────────────────────────────
COPY --from=builder /app/build /usr/share/nginx/html

# ── nginx config ─────────────────────────────────────────────────────────────
RUN rm -f /etc/nginx/http.d/default.conf
COPY app/frontend/nginx-single.conf /etc/nginx/http.d/default.conf

# ── supervisord config ────────────────────────────────────────────────────────
COPY supervisord.conf /etc/supervisord.conf

# ── Non-root user setup ───────────────────────────────────────────────────────
# Create appuser, redirect nginx pid/temp paths to /tmp, fix all ownership.
# nginx on 8080 + uvicorn on 8000 both work without root privileges.
# Create non-root user and fix all directory permissions.
# nginx pid is now set via supervisord command line ("pid /tmp/nginx.pid;")
# so no fragile sed patching of nginx.conf needed.
# We still chown /run/nginx as a safety net in case nginx tries to write there.
RUN addgroup -g 1000 -S appgroup && adduser -u 1000 -S appuser -G appgroup \
    && sed -i '/^user /d' /etc/nginx/nginx.conf \
    && mkdir -p /data /tmp/nginx/client_temp /tmp/nginx/proxy_temp \
                /tmp/nginx/fastcgi_temp /tmp/nginx/uwsgi_temp /tmp/nginx/scgi_temp \
                /run/nginx \
    && chown -R appuser:appgroup \
        /data \
        /app/backend \
        /usr/share/nginx/html \
        /var/lib/nginx \
        /var/log/nginx \
        /tmp/nginx \
        /run/nginx \
        /etc/nginx/http.d

# Copy entrypoint script — runs as root to fix /data permissions,
# then supervisord takes over running nginx + uvicorn as appuser.
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

# Docker Scout compliance: USER appuser declared here so the image
# is marked as non-root. At runtime, docker-compose overrides this with
# "user: root" so entrypoint.sh can chown /data, then supervisord
# drops back to appuser via the user= directive in supervisord.conf.
USER appuser
ENTRYPOINT ["/entrypoint.sh"]
