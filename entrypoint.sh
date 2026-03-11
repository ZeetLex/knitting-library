#!/bin/sh
# entrypoint.sh — start nginx + uvicorn without supervisor

set -e

# ── Create directories ────────────────────────────────────────────────────────
mkdir -p /data/recipes /data/yarns /logs

# ── Log rotation helper (keeps last 5 × 10 MB per service) ───────────────────
rotate_log() {
    log="$1"
    max_bytes=10485760   # 10 MB
    if [ -f "$log" ] && [ "$(wc -c < "$log")" -gt "$max_bytes" ]; then
        for i in 4 3 2 1; do
            [ -f "${log}.${i}" ] && mv "${log}.${i}" "${log}.$((i+1))"
        done
        mv "$log" "${log}.1"
    fi
}

rotate_log /logs/nginx.log
rotate_log /logs/uvicorn.log

# ── Write startup marker ──────────────────────────────────────────────────────
echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  container started (pid $$)" >> /logs/supervisord.log

# ── Start nginx ───────────────────────────────────────────────────────────────
nginx -g "daemon off; pid /tmp/nginx.pid;" >> /logs/nginx.log 2>&1 &
NGINX_PID=$!
echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  nginx started (pid $NGINX_PID)" >> /logs/supervisord.log

# ── Start uvicorn ─────────────────────────────────────────────────────────────
cd /app/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --access-log >> /logs/uvicorn.log 2>&1 &
UVICORN_PID=$!
echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  uvicorn started (pid $UVICORN_PID)" >> /logs/supervisord.log

# ── Give processes time to start before watchdog begins ──────────────────────
sleep 3

# ── Graceful shutdown on SIGTERM / SIGINT ────────────────────────────────────
shutdown() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  shutting down..." >> /logs/supervisord.log
    kill "$NGINX_PID"   2>/dev/null
    kill "$UVICORN_PID" 2>/dev/null
    wait
    exit 0
}
trap shutdown TERM INT

# ── Watchdog — restart either process if it exits unexpectedly ───────────────
while true; do
    if ! kill -0 "$NGINX_PID" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') WARN  nginx exited — restarting" >> /logs/supervisord.log
        rotate_log /logs/nginx.log
        nginx -g "daemon off; pid /tmp/nginx.pid;" >> /logs/nginx.log 2>&1 &
        NGINX_PID=$!
        echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  nginx restarted (pid $NGINX_PID)" >> /logs/supervisord.log
    fi

    if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') WARN  uvicorn exited — restarting" >> /logs/supervisord.log
        rotate_log /logs/uvicorn.log
        cd /app/backend
        uvicorn main:app --host 0.0.0.0 --port 8000 --access-log >> /logs/uvicorn.log 2>&1 &
        UVICORN_PID=$!
        echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  uvicorn restarted (pid $UVICORN_PID)" >> /logs/supervisord.log
    fi

    sleep 10
done
