#!/usr/bin/env bash
set -euo pipefail

MCP_URL="${MCP_URL:-http://127.0.0.1:8765/mcp}"
MCP_ACCEPT_HEADER="${MCP_ACCEPT_HEADER:-Accept: text/event-stream}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-10}"
SLEEP_SECONDS="${SLEEP_SECONDS:-2}"
CONNECT_TIMEOUT_SECONDS="${CONNECT_TIMEOUT_SECONDS:-2}"
MAX_TIME_SECONDS="${MAX_TIME_SECONDS:-4}"

echo "Probing tunneled MCP endpoint"
echo "  url: ${MCP_URL}"
echo "  max attempts: ${MAX_ATTEMPTS}"
echo "  sleep between attempts: ${SLEEP_SECONDS}s"
echo

attempt=1
while (( attempt <= MAX_ATTEMPTS )); do
  echo "Attempt ${attempt}/${MAX_ATTEMPTS}: checking ${MCP_URL}"
  if output="$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout "${CONNECT_TIMEOUT_SECONDS}" \
    --max-time "${MAX_TIME_SECONDS}" \
    -H "${MCP_ACCEPT_HEADER}" \
    "${MCP_URL}" 2>&1)"; then
    http_code="${output}"
    if [[ "${http_code}" != "000" ]]; then
      echo "MCP endpoint reachable with HTTP ${http_code}."
      echo "Treating tunnel/backend as reachable. Next check: MCP health."
      exit 0
    fi
  else
    echo "Probe failed: ${output}"
  fi

  if (( attempt < MAX_ATTEMPTS )); then
    echo "Tunnel not ready yet. Retrying in ${SLEEP_SECONDS}s."
    sleep "${SLEEP_SECONDS}"
    echo
  fi

  ((attempt += 1))
done

echo "MCP probe failed after ${MAX_ATTEMPTS} attempts." >&2
echo "Check the visible tunnel pane, confirm the robot MCP server is up, and retry." >&2
exit 1
