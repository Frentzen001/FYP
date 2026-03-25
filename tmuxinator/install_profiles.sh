#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_DIR="$ROOT_DIR/profiles"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/tmuxinator"

if ! command -v tmuxinator >/dev/null 2>&1; then
  echo "tmuxinator is not installed. Install tmux and tmuxinator first." >&2
  echo "Example: sudo apt install -y tmux && gem install tmuxinator" >&2
  exit 1
fi

mkdir -p "$CONFIG_DIR"

for profile in moretea_robot moretea_voice; do
  src="$PROFILE_DIR/${profile}.yml"
  dest="$CONFIG_DIR/${profile}.yml"
  ln -sfn "$src" "$dest"
  echo "Installed $dest -> $src"
done

cat <<'EOF'

Profiles installed.

Robot PC:
  tmuxinator start moretea_robot

OpenClaw PC:
  export ROBOT_USER=<robot-user>
  export ROBOT_HOST=<robot-ip>
  tmuxinator start moretea_voice
EOF
