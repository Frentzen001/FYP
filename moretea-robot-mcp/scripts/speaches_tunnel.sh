#!/usr/bin/env bash
set -euo pipefail

DESKTOP_HOST="${DESKTOP_HOST:?Set DESKTOP_HOST to the remote desktop IP or hostname}"
DESKTOP_USER="${DESKTOP_USER:?Set DESKTOP_USER to the SSH username on the remote desktop}"
LOCAL_PORT="${SPEACHES_LOCAL_PORT:-8000}"
REMOTE_PORT="${SPEACHES_REMOTE_PORT:-8000}"
SSH_SERVER_ALIVE_INTERVAL="${SSH_SERVER_ALIVE_INTERVAL:-15}"
SSH_SERVER_ALIVE_COUNT_MAX="${SSH_SERVER_ALIVE_COUNT_MAX:-3}"

if ! command -v autossh >/dev/null 2>&1; then
  echo "autossh is required for the visible tmux tunnel workflow." >&2
  echo "Install autossh on the robot PC, then rerun this script." >&2
  exit 1
fi

echo "Starting Speaches tunnel (robot PC -> remote desktop)"
echo "  desktop host: ${DESKTOP_HOST}"
echo "  desktop user: ${DESKTOP_USER}"
echo "  local port:   ${LOCAL_PORT}"
echo "  remote port:  ${REMOTE_PORT}"
echo "  keepalive: interval=${SSH_SERVER_ALIVE_INTERVAL}s count_max=${SSH_SERVER_ALIVE_COUNT_MAX}"
echo "Tunnel stays attached to this pane so reconnects and failures remain visible."
echo

export AUTOSSH_GATETIME="${AUTOSSH_GATETIME:-0}"
export AUTOSSH_LOGLEVEL="${AUTOSSH_LOGLEVEL:-7}"

exec autossh \
  -M 0 \
  -N \
  -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval="${SSH_SERVER_ALIVE_INTERVAL}" \
  -o ServerAliveCountMax="${SSH_SERVER_ALIVE_COUNT_MAX}" \
  "${DESKTOP_USER}@${DESKTOP_HOST}"
