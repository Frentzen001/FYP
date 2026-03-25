#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Missing required command: $name" >&2
    return 1
  fi
}

require_cmd uv

echo "Syncing Python dependencies..."
(cd "$ROOT_DIR/agent-starter-python" && uv sync)
(cd "$ROOT_DIR/moretea-robot-mcp" && uv sync)

echo
echo "Installing tmuxinator profiles if tmuxinator is available..."
if command -v tmuxinator >/dev/null 2>&1; then
  "$ROOT_DIR/tmuxinator/install_profiles.sh"
else
  echo "tmuxinator is not installed yet. Install tmux + tmuxinator, then run:"
  echo "  cd $ROOT_DIR && ./tmuxinator/install_profiles.sh"
fi

echo
echo "Bootstrap complete."
echo
echo "Manual system prerequisites still required:"
echo "  - ROS 2 Humble and your robot ROS packages on the robot PC"
echo "  - Docker for Speaches on the OpenClaw PC"
echo "  - tmux + tmuxinator if you want the one-command dev launcher"
echo "  - valid .env.local for agent-starter-python"
echo
echo "Next docs:"
echo "  - $ROOT_DIR/RUNBOOK.md"
echo "  - $ROOT_DIR/tmuxinator/README.md"
