#!/bin/sh
# Create persistent data and log directories if they don't exist, then start.
mkdir -p /data/recipes /data/yarns /logs
exec /usr/local/bin/supervisord -c /etc/supervisord.conf
