#!/usr/bin/env bash
# SETUP-04: run the service (uvicorn --reload) and the web app (pnpm dev) together.
#
#   scripts/dev.sh           start both; one Ctrl-C stops both
#   scripts/dev.sh --print   show the commands it would run, then exit
#
# Env files are passed by PATH only; this script never opens or prints them.
#   service: service/.env (override with BOOR_SERVICE_ENV_FILE), handed to
#            uvicorn --env-file if it exists
#   web:     Next.js loads web/.env.local itself
# Ports: SERVICE_PORT (default 8000), WEB_PORT (default 3000).
# BOOR_DEV_SERVICE_CMD / BOOR_DEV_WEB_CMD replace the commands (used by tests).
#
# Portable to macOS's bash 3.2 (no `wait -n`).
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_PORT="${SERVICE_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
SERVICE_ENV_FILE="${BOOR_SERVICE_ENV_FILE:-$ROOT/service/.env}"

service_cmd="uv run uvicorn boor_service.api:app --reload --port $SERVICE_PORT"
if [ -f "$SERVICE_ENV_FILE" ]; then
  service_cmd="$service_cmd --env-file $SERVICE_ENV_FILE"
fi
web_cmd="pnpm dev --port $WEB_PORT"
service_cmd="${BOOR_DEV_SERVICE_CMD:-$service_cmd}"
web_cmd="${BOOR_DEV_WEB_CMD:-$web_cmd}"

if [ "${1:-}" = "--print" ]; then
  echo "service (in $ROOT/service): $service_cmd"
  echo "web     (in $ROOT/web): $web_cmd"
  exit 0
fi

# Each child gets its own process group so cleanup can stop its whole tree
# (uvicorn's reloader worker, Next's dev server workers).
set -m

service_pid=""
web_pid=""
cleaned_up=0

stop_group() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
}

cleanup() {
  [ "$cleaned_up" = 1 ] && return 0
  cleaned_up=1
  echo "[dev] stopping service and web..." >&2
  stop_group "$service_pid"
  stop_group "$web_pid"
  # Give them a few seconds to exit cleanly, then force it.
  local i=0
  while [ $i -lt 50 ]; do
    if ! kill -0 -- "-$service_pid" 2>/dev/null && ! kill -0 -- "-$web_pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.1
    i=$((i + 1))
  done
  kill -KILL -- "-$service_pid" "-$web_pid" 2>/dev/null || true
}

trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

(cd "$ROOT/service" && exec bash -c "$service_cmd") &
service_pid=$!
(cd "$ROOT/web" && exec bash -c "$web_cmd") &
web_pid=$!

echo "[dev] service -> http://localhost:$SERVICE_PORT (pid $service_pid)" >&2
echo "[dev] web     -> http://localhost:$WEB_PORT (pid $web_pid)" >&2
echo "[dev] Ctrl-C stops both." >&2

# Supervise: when either child exits, stop the other. `sleep & wait` keeps the
# loop interruptible so Ctrl-C is handled immediately.
while kill -0 "$service_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do
  sleep 1 &
  wait $! 2>/dev/null
done

if kill -0 "$service_pid" 2>/dev/null; then
  wait "$web_pid"; status=$?; who=web
else
  wait "$service_pid"; status=$?; who=service
fi
echo "[dev] $who exited (status $status)" >&2
cleanup
exit "$status"
