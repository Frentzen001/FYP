#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_PID=""
WATCH_PID=""

cleanup() {
  if [[ -n "$WATCH_PID" ]]; then
    kill "$WATCH_PID" 2>/dev/null || true
    wait "$WATCH_PID" 2>/dev/null || true
  fi
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if [[ "${MORETEA_START_WATCHER:-1}" == "1" ]]; then
  "$ROOT_DIR/scripts/watch_eye_expression.sh" &
  WATCH_PID="$!"
fi

"$ROOT_DIR/scripts/run_robot_mcp.sh" &
SERVER_PID="$!"

wait "$SERVER_PID"
