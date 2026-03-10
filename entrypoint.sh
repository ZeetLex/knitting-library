#!/bin/sh
# entrypoint.sh
# This script runs as root (set via --user=root in the exec form below).
# supervisord then manages nginx (root) and uvicorn (appuser) as configured.
exec /usr/local/bin/supervisord -c /etc/supervisord.conf
