# Dockerfile
# Stage 1: Build the React frontend
# Stage 2: Final image — Python backend (uvicorn) + nginx, managed by entrypoint.sh

FROM node:20-alpine AS builder
WORKDIR /app
COPY app/frontend/package.json ./
RUN npm install --legacy-peer-deps
COPY app/frontend/ .
RUN npm run build

FROM python:3.12-alpine3.22

LABEL org.opencontainers.image.source="https://github.com/ZeetLex/knitting-library"

# nginx:         serves the React frontend on port 8080
# poppler-utils: converts PDF pages to images
# gcc/musl/zlib/jpeg/libffi: needed to COMPILE Python packages (bcrypt, Pillow, uvloop)
# After pip install we remove the compiler toolchain (gcc, musl-dev, binutils) since
# they are only needed at build time. Runtime shared libraries (zlib, libjpeg, libffi)
# are kept — they are pulled in as dependencies of zlib-dev etc. and survive apk del.
# This eliminates CVE-2025-69649 and CVE-2025-69650 (alpine/binutils) from the image.
RUN apk add --no-cache \
    nginx \
    poppler-utils \
    gcc \
    musl-dev \
    zlib-dev \
    jpeg-dev \
    libffi-dev \
    su-exec \
    && apk upgrade --no-cache

WORKDIR /app/backend
COPY app/backend/requirements.txt .

# 1. Compile all Python packages (bcrypt, Pillow, uvloop need gcc)
# 2. Strip the compiler toolchain — compiled .so files remain, tools are removed
# 3. Fix vendored wheel CVE
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y wheel \
    && find /usr/local/lib/python3.12/site-packages/setuptools/_vendor -name "wheel-*.dist-info" -exec rm -rf {} + 2>/dev/null; true \
    && pip install --no-cache-dir --no-deps "wheel==0.46.2" \
    && apk del gcc musl-dev binutils \
    && rm -rf /usr/libexec/gcc /usr/lib/gcc /var/cache/apk/*

COPY app/backend/ .
COPY --from=builder /app/build /usr/share/nginx/html

RUN rm -f /etc/nginx/http.d/default.conf
COPY app/frontend/nginx-single.conf /etc/nginx/http.d/default.conf

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
# can create /data and /logs on first run.
USER appuser
ENTRYPOINT ["/entrypoint.sh"]
