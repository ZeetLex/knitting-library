# Dockerfile
# Stage 1: Build the React frontend
# Stage 2: Final image — Python/uvicorn serves both API and React frontend directly.
# No nginx — eliminates all nginx permission issues across different host UIDs.

FROM node:20-alpine AS builder
WORKDIR /app
COPY app/frontend/package.json ./
RUN npm install --legacy-peer-deps
COPY app/frontend/ .

# Fonts are bundled via @fontsource npm packages (imported in index.js).
# No external font downloads needed — they are included in node_modules.
RUN npm run build

FROM python:3.12-alpine3.22

LABEL org.opencontainers.image.source="https://github.com/ZeetLex/knitting-library"

# poppler-utils: converts PDF pages to images
# gcc/musl/zlib/jpeg/libffi: needed to COMPILE Python packages (bcrypt, Pillow, uvloop)
# After pip install we remove the compiler toolchain (gcc, musl-dev, binutils) since
# they are only needed at build time. Runtime shared libraries (zlib, libjpeg, libffi)
# are kept — they are pulled in as dependencies of zlib-dev etc. and survive apk del.
# This eliminates CVE-2025-69649 and CVE-2025-69650 (alpine/binutils) from the image.
RUN apk add --no-cache \
    poppler-utils \
    gcc \
    musl-dev \
    zlib-dev \
    jpeg-dev \
    libffi-dev \
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
# Copy React build — FastAPI's SPA middleware serves it directly
COPY --from=builder /app/build /app/frontend/build

# Create data dirs — entrypoint will set final permissions at runtime
RUN mkdir -p /data /logs && chmod 777 /data /logs
COPY entrypoint.sh /entrypoint.sh
# Strip Windows CRLF line endings if the file was edited on Windows
RUN sed -i 's/\r//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8080

# Container runs as root so entrypoint.sh can chown /data and /logs on first run.
# Uvicorn starts on port 8080 — no root privileges required.
ENTRYPOINT ["/entrypoint.sh"]
