#!/bin/bash
set -e

# Start Caddy in background but logging to stdout
caddy run --config /etc/caddy/Caddyfile &

# Start the Python application
if [ "$RUNNING_IN_DOCKER" = "true" ]; then
    echo "Running in Docker (using system python)..."
    exec python main.py
elif [ -d "venv" ]; then
    echo "Using virtual environment..."
    exec ./venv/bin/python main.py
else
    echo "Using system python..."
    exec python main.py
fi
