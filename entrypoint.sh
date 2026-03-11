#!/bin/sh
# entrypoint.sh — single-process: uvicorn serves both API and React frontend
# No nginx, no permission issues, works with any PUID/PGID.

# ── Set up /data and /logs ────────────────────────────────────────────────────
mkdir -p /data/recipes /data/yarns /logs 2>/dev/null || true
chmod 777 /logs 2>/dev/null || true

# If running as root, chown data to PUID:PGID so host sees correct ownership
if [ "$(id -u)" = "0" ]; then
    PUID=${PUID:-0}
    PGID=${PGID:-0}
    if [ "$PUID" != "0" ]; then
        chown -R "${PUID}:${PGID}" /data /logs 2>/dev/null || true
    fi
fi

# ── Log rotation ──────────────────────────────────────────────────────────────
rotate_log() {
    log="$1"; max_bytes=10485760
    if [ -f "$log" ] && [ "$(wc -c < "$log")" -gt "$max_bytes" ]; then
        for i in 4 3 2 1; do [ -f "${log}.${i}" ] && mv "${log}.${i}" "${log}.$((i+1))"; done
        mv "$log" "${log}.1"
    fi
}
rotate_log /logs/uvicorn.log

echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  container started (uid=$(id -u) gid=$(id -g))" >> /logs/supervisord.log

# ── Start uvicorn (serves React frontend + API on port 8080) ──────────────────
cd /app/backend
uvicorn main:app --host 0.0.0.0 --port 8080 --access-log >> /logs/uvicorn.log 2>&1 &
UVICORN_PID=$!
echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  uvicorn started (pid $UVICORN_PID)" >> /logs/supervisord.log

# ── Graceful shutdown ─────────────────────────────────────────────────────────
shutdown() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') INFO  shutting down..." >> /logs/supervisord.log
    kill "$UVICORN_PID" 2>/dev/null
    wait; exit 0
}
trap shutdown TERM INT

# ── Watchdog ──────────────────────────────────────────────────────────────────
while true; do
    if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') WARN  uvicorn exited — restarting" >> /logs/supervisord.log
        rotate_log /logs/uvicorn.log
        cd /app/backend
        uvicorn main:app --host 0.0.0.0 --port 8080 --access-log >> /logs/uvicorn.log 2>&1 &
        UVICORN_PID=$!
    fi
    sleep 10
done
