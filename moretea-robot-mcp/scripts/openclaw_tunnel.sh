#!/usr/bin/env bash
set -euo pipefail

ROBOT_HOST="${ROBOT_HOST:?Set ROBOT_HOST to the robot PC IP or hostname}"
ROBOT_USER="${ROBOT_USER:?Set ROBOT_USER to the SSH username on the robot PC}"
LOCAL_PORT="${LOCAL_PORT:-8765}"
REMOTE_PORT="${REMOTE_PORT:-8765}"

exec ssh -N -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" "${ROBOT_USER}@${ROBOT_HOST}"
