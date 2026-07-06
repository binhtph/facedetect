#!/bin/sh
set -eu

uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
api_pid="$!"

node /app/docker/web-server.mjs &
web_pid="$!"

trap 'kill "$api_pid" "$web_pid" 2>/dev/null || true; exit 0' INT TERM

nginx -g "daemon off;" &
nginx_pid="$!"

wait "$nginx_pid"
