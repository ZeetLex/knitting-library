#!/bin/sh
# entrypoint.sh — single-process: uvicorn serves both API and React frontend
# No nginx, no permission issues, works with any PUID/PGID.

# Match Python's unset/blank defaults and validate before any filesystem changes.
KNITTING_DATA_DIR=$(printf '%s' "${KNITTING_DATA_DIR:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
KNITTING_LOG_DIR=$(printf '%s' "${KNITTING_LOG_DIR:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
KNITTING_STATIC_DIR=$(printf '%s' "${KNITTING_STATIC_DIR:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
export KNITTING_DATA_DIR="${KNITTING_DATA_DIR:-/data}"
export KNITTING_LOG_DIR="${KNITTING_LOG_DIR:-/logs}"
export KNITTING_STATIC_DIR="${KNITTING_STATIC_DIR:-/app/frontend/build}"
for name in KNITTING_DATA_DIR KNITTING_LOG_DIR KNITTING_STATIC_DIR; do
    case "$name" in
        KNITTING_DATA_DIR) directory=$KNITTING_DATA_DIR ;;
        KNITTING_LOG_DIR) directory=$KNITTING_LOG_DIR ;;
        KNITTING_STATIC_DIR) directory=$KNITTING_STATIC_DIR ;;
    esac
    case "$directory" in
        /*) ;;
        *) echo "$name must be an absolute path (received $directory)" >&2; exit 1 ;;
    esac
done

# ── Set up configured data and log directories ────────────────────────────────
mkdir -p "$KNITTING_DATA_DIR/recipes" "$KNITTING_DATA_DIR/yarns" "$KNITTING_LOG_DIR" || exit 1
chmod 777 "$KNITTING_LOG_DIR" 2>/dev/null || true

# If running as root, chown data to PUID:PGID so host sees correct ownership
if [ "$(id -u)" = "0" ]; then
    PUID=${PUID:-0}
    PGID=${PGID:-0}
    if [ "$PUID" != "0" ]; then
        chown -R "${PUID}:${PGID}" "$KNITTING_DATA_DIR" "$KNITTING_LOG_DIR" 2>/dev/null || true
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
rotate_log "$KNITTING_LOG_DIR/uvicorn.log"
touch "$KNITTING_LOG_DIR/uvicorn.log" || exit 1

log_supervisor() {
    line="$(date '+%Y-%m-%d %H:%M:%S') $1"
    echo "$line" | tee -a "$KNITTING_LOG_DIR/supervisord.log"
}

log_supervisor "INFO  container started (uid=$(id -u) gid=$(id -g))"

# Mirror uvicorn's persistent log file to container stdout so `docker logs`
# works while the admin UI reads the same configured file.
tail -n 0 -F "$KNITTING_LOG_DIR/uvicorn.log" &
TAIL_PID=$!

# ── Start uvicorn (serves React frontend + API on port 8080) ──────────────────
cd /app/backend
uvicorn main:app --host 0.0.0.0 --port 8080 --access-log >> "$KNITTING_LOG_DIR/uvicorn.log" 2>&1 &
UVICORN_PID=$!
log_supervisor "INFO  uvicorn started (pid $UVICORN_PID)"

# ── Graceful shutdown ─────────────────────────────────────────────────────────
shutdown() {
    log_supervisor "INFO  shutting down..."
    kill "$UVICORN_PID" 2>/dev/null
    kill "$TAIL_PID" 2>/dev/null
    wait; exit 0
}
trap shutdown TERM INT

# ── Watchdog ──────────────────────────────────────────────────────────────────
while true; do
    if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
        log_supervisor "WARN  uvicorn exited — restarting"
        rotate_log "$KNITTING_LOG_DIR/uvicorn.log"
        cd /app/backend
        uvicorn main:app --host 0.0.0.0 --port 8080 --access-log >> "$KNITTING_LOG_DIR/uvicorn.log" 2>&1 &
        UVICORN_PID=$!
    fi
    sleep 10
done
