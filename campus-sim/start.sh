#!/bin/bash
set -e

# Start Caddy in background but logging to stdout
caddy run --config /etc/caddy/Caddyfile &

# Start the Python application
exec python main.py
