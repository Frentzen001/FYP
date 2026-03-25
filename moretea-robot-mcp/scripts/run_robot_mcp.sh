#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

set +u
source /opt/ros/humble/setup.bash
set -u

export MORETEA_ROBOT_MCP_HOST="${MORETEA_ROBOT_MCP_HOST:-${MORETEA_EYE_MCP_HOST:-127.0.0.1}}"
export MORETEA_ROBOT_MCP_PORT="${MORETEA_ROBOT_MCP_PORT:-${MORETEA_EYE_MCP_PORT:-8765}}"
export MORETEA_ROBOT_MCP_PATH="${MORETEA_ROBOT_MCP_PATH:-${MORETEA_EYE_MCP_PATH:-/mcp}}"

cd "$ROOT_DIR"
exec uv run python -m moretea_robot_mcp.server
