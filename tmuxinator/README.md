# Tmuxinator Dev Launchers

These tmuxinator profiles are the current development launcher for MoreTea while the robot, Nav stack, and voice stack are still changing frequently.

## Install

Install `tmux` and `tmuxinator` on each machine, then install the repo-tracked profiles into your local tmuxinator config:

```bash
cd /home/frentzen/FYP
./bootstrap_dev.sh
```

Or if you only want the tmuxinator profiles:

```bash
cd /home/frentzen/FYP
./tmuxinator/install_profiles.sh
```

This creates symlinks in:

```text
~/.config/tmuxinator/
```

so the standard commands work:

```bash
tmuxinator start moretea_robot
tmuxinator start moretea_voice
```

## Robot PC

Use:

```bash
tmuxinator start moretea_robot
```

Windows opened:

- `precheck`
- `bringup`
- `head_agent`
- `face_tracker`
- `arm`
- `online_access`
- `navigation`
- `robot_mcp`
- `eye_watch`

Notes:

- `tailscale up` stays manual and is shown as a reminder in `precheck`
- `robot_mcp` is launched after the Nav-related services
- if `8765` is busy, clear stale MCP processes before relaunching

Machine-specific robot settings can be overridden with environment variables before starting the profile:

```bash
export MORETEA_BASE_SERIAL_PORT=/dev/ttyESP32_motor
export MORETEA_MICRO_ROS_BAUDRATE=115200
export MORETEA_HEAD_SERIAL_PORT=/dev/ttyESP32_head
export MORETEA_HEAD_BAUDRATE=115200
export MORETEA_HEAD_PUBSUB_DIR=$HOME/Tinkering-Project-More-Tea/ros2_ws/src/head_pubsub
export MORETEA_ONLINE_ACCESS_DIR=$HOME/Tinkering-Project-More-Tea/online_access
```

This avoids editing the tmuxinator YAML just to match another machine’s ports or directories.

## OpenClaw PC

Before starting the voice profile, export the robot SSH details:

```bash
export ROBOT_USER=<robot-user>
export ROBOT_HOST=<robot-ip>
```

OpenClaw-side requirement:

- `autossh` installed so the visible tunnel pane can reconnect after short drops

Then run:

```bash
tmuxinator start moretea_voice
```

Windows opened:

- `precheck`
- `tunnel`
- `speaches`
- `barebone`
- `checks`

The `tunnel` window stays visible by design. It is the operator-facing source of truth for the OpenClaw-to-robot MCP link, so developers can see whether the tunnel is connected, retrying, or failed.

## Verification

After both profiles are up:

```bash
/home/frentzen/FYP/moretea-robot-mcp/scripts/probe_tunneled_mcp.sh
curl http://127.0.0.1:8000/v1/models
```

Then call MCP `health` first and confirm:

- `navigation_ready: true`
- `tour_navigation.nav2_import_ready: true`

`tour_navigation.nav2_active_check_bypassed: true` is acceptable in the current Humble setup.

Treat the tunnel as ready only when:

- the `tunnel` pane is running cleanly
- the MCP probe succeeds
- `health` succeeds before prompt testing

For the full cross-machine launch and troubleshooting guide, use:

- [RUNBOOK.md](/home/frentzen/FYP/RUNBOOK.md)
