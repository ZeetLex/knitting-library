#!/bin/sh
# entrypoint.sh
# Ensures the /data directories exist, then starts the app.
# Note: chown is intentionally not used here.
# On Docker Desktop for Windows, bind-mounted folders are owned by Windows
# and cannot be re-owned from inside the container.
# The app uses SQLite WAL mode instead, which handles writes correctly
# without needing to change file ownership.

echo "Creating data directories if needed..."
mkdir -p /data/recipes /data/yarns /data/import 2>/dev/null || true

echo "Starting supervisord..."
exec /usr/local/bin/supervisord -c /etc/supervisord.conf
