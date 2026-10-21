# Dockerfile
# Stage 1: Build the React frontend
# Stage 2: Final image — Python/uvicorn serves both API and React frontend directly.
# No nginx — eliminates all nginx permission issues across different host UIDs.

FROM node:24-alpine3.24@sha256:f777d4615e9f225aa23d72dc05bd8454a0fadcb033e00417c5b9257f5585677b AS builder
WORKDIR /app
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY app/frontend/ .

# Fonts are bundled via @fontsource npm packages (imported in index.jsx).
# No external font downloads needed — they are included in node_modules.
RUN npm run build

FROM python:3.12-alpine3.24@sha256:2055081c860db8c842b663415b795b026e7e5cc63b59c5193fcc9997713ea5b8

LABEL org.opencontainers.image.source="https://github.com/ZeetLex/knitting-library"

# poppler-utils: converts PDF pages to images for AI vision scanning
# .build-deps supports source builds when a dependency has no compatible wheel.
# Runtime libraries are explicitly retained before the build group is removed.
RUN apk upgrade --no-cache \
    && apk add --no-cache poppler-utils \
    && apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    zlib-dev \
    jpeg-dev \
    libffi-dev

WORKDIR /app/backend
COPY app/backend/requirements.txt app/backend/requirements.lock ./

# Install runtime libraries explicitly so removing build dependencies preserves them.
# Remove build tooling rather than altering its vulnerability metadata.
RUN apk add --no-cache libjpeg-turbo zlib libffi \
    && pip install --no-cache-dir -r requirements.txt -c requirements.lock \
    && pip uninstall -y pip setuptools wheel \
    && apk del .build-deps

COPY app/backend/ .
# Copy frontend build — FastAPI's SPA middleware serves it directly
COPY --from=builder /app/dist /app/frontend/build

# Create data dirs — entrypoint will set final permissions at runtime
RUN mkdir -p /data /logs && chmod 777 /data /logs
COPY entrypoint.sh /entrypoint.sh
# Strip Windows CRLF line endings if the file was edited on Windows
RUN sed -i 's/\r//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8080

# Container runs as root so entrypoint.sh can chown /data and /logs on first run.
# Uvicorn starts on port 8080 — no root privileges required.
ENTRYPOINT ["/entrypoint.sh"]
