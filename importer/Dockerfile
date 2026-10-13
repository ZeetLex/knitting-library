# Knit Import: reads DROPS patterns and adds them to Knitting Library.
# Chromium makes the PDF. poppler-utils reads and previews it.
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/wight-trash/knitting-library"
LABEL org.opencontainers.image.description="Adds patterns from pattern websites to Knitting Library"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    CHROMIUM_PATH=/usr/bin/chromium \
    DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium poppler-utils fonts-liberation fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 568 is the usual "apps" user on TrueNAS SCALE. Change it to match the owner of your dataset.
ARG APP_UID=568
RUN useradd --system --uid ${APP_UID} --no-create-home --shell /usr/sbin/nologin importer \
    && mkdir -p /data && chown importer /data
USER importer

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/api/health', timeout=4)"

CMD ["uvicorn", "app.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
