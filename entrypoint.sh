#!/bin/sh
# entrypoint.sh — start nginx + uvicorn with PUID/PGID support

PUID=${PUID:-1000}
PGID=${PGID:-1000}

# ── If running as root, set up dirs then drop privileges ─────────────────────
if [ "$(id -u)" = "0" ]; then
    mkdir -p /data/recipes /data/yarns /logs

    # Set ownership — ignore errors (some host filesystems don't allow chown)
    chown -R "${PUID}:${PGID}" /data /logs 2>/dev/null || true

    # Ensure the folders are writable regardless of ownership
    chmod 755 /data /data/recipes /data/yarns
    chmod 777 /logs

    # Test if the target user can actually write — if not, stay as root
    if su-exec "${PUID}:${PGID}" touch /logs/.writetest 2>/dev/null; then
        rm -f /logs/.writetest
        exec su-exec "${PUID}:${PGID}" "$0" "$@"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') WARN  cannot write to /logs as ${PUID}:${PGID} — running as root" 
        # Fall through and run as root
    fi
fi

# ── Running as PUID:PGID (or root as fallback) ───────────────────────────────

rotate_log() {
    log="$1"
    max_bytes=10485760
    if [ -f "$log" ] && [ "$(wc -c < "$log")" -gt "$max_bytes" ]; then
        for i in 4 3 2 1; do
            [ -f "${log}.${i}" ] && mv "${log}.${i}" "${log}.$((i+1))"
        done
        mv "$log" "${log}.1"
    fi
}

rotate_log /logs/nginx.log
rotate_log /logs/uvicorn.log

echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  container started (uid=$(id -u) gid=$(id -g))" >> /logs/supervisord.log

nginx -g "daemon off; pid /tmp/nginx.pid;" >> /logs/nginx.log 2>&1 &
NGINX_PID=$!
echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  nginx started (pid $NGINX_PID)" >> /logs/supervisord.log

cd /app/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --access-log >> /logs/uvicorn.log 2>&1 &
UVICORN_PID=$!
echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  uvicorn started (pid $UVICORN_PID)" >> /logs/supervisord.log

sleep 3

shutdown() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  shutting down..." >> /logs/supervisord.log
    kill "$NGINX_PID" "$UVICORN_PID" 2>/dev/null
    wait
    exit 0
}
trap shutdown TERM INT

while true; do
    if ! kill -0 "$NGINX_PID" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') WARN  nginx exited — restarting" >> /logs/supervisord.log
        rotate_log /logs/nginx.log
        nginx -g "daemon off; pid /tmp/nginx.pid;" >> /logs/nginx.log 2>&1 &
        NGINX_PID=$!
    fi
    if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') WARN  uvicorn exited — restarting" >> /logs/supervisord.log
        rotate_log /logs/uvicorn.log
        cd /app/backend
        uvicorn main:app --host 0.0.0.0 --port 8000 --access-log >> /logs/uvicorn.log 2>&1 &
        UVICORN_PID=$!
    fi
    sleep 10
done
