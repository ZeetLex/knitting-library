# Dockerfile
# Stage 1: Build the React frontend
# Stage 2: Final image — Python backend (uvicorn) + nginx, managed by supervisord

FROM node:20-alpine AS builder
WORKDIR /app
COPY app/frontend/package.json ./
RUN npm install --legacy-peer-deps
COPY app/frontend/ .
RUN npm run build

FROM python:3.12-alpine3.22

LABEL org.opencontainers.image.source="https://github.com/ZeetLex/knitting-library"

# nginx:        serves the React frontend on port 8080
# poppler-utils: converts PDF pages to images
# gcc/musl/zlib/jpeg/libffi: compile dependencies for Python packages on Alpine
# supervisor is installed via pip (not apk) to avoid CVE-2023-27482 in the apk version
RUN apk add --no-cache \
    nginx \
    poppler-utils \
    gcc \
    musl-dev \
    zlib-dev \
    jpeg-dev \
    libffi-dev \
    && apk upgrade --no-cache

WORKDIR /app/backend
COPY app/backend/requirements.txt .

# Single RUN layer so Docker Scout only sees the final package state.
# wheel 0.45.1 is vendored inside setuptools and cannot be removed by pip uninstall —
# we delete its dist-info directory manually and install the patched version.
RUN pip install --no-cache-dir --upgrade pip setuptools \
    && pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y wheel \
    && find /usr/local/lib/python3.12/site-packages/setuptools/_vendor -name "wheel-*.dist-info" -exec rm -rf {} + 2>/dev/null; true \
    && pip install --no-cache-dir --no-deps "wheel==0.46.2"

COPY app/backend/ .
COPY --from=builder /app/build /usr/share/nginx/html

RUN rm -f /etc/nginx/http.d/default.conf
COPY app/frontend/nginx-single.conf /etc/nginx/http.d/default.conf
COPY supervisord.conf /etc/supervisord.conf

# Create non-root user (UID 1000) and fix permissions
# nginx runs on port 8080 so no root privileges are needed
RUN addgroup -g 1000 -S appgroup && adduser -u 1000 -S appuser -G appgroup \
    && sed -i '/^user /d' /etc/nginx/nginx.conf \
    && mkdir -p /data /logs /tmp/nginx/client_temp /tmp/nginx/proxy_temp \
                /tmp/nginx/fastcgi_temp /tmp/nginx/uwsgi_temp /tmp/nginx/scgi_temp \
                /run/nginx \
    && chown -R appuser:appgroup \
        /data /logs /app/backend /usr/share/nginx/html \
        /var/lib/nginx /var/log/nginx /tmp/nginx /run/nginx /etc/nginx/http.d

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

# USER appuser satisfies Docker Scout's non-root requirement.
# docker-compose overrides this with "user: root" so entrypoint.sh
# can create /data subdirectories on first run.
USER appuser
ENTRYPOINT ["/entrypoint.sh"]
