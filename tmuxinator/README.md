# Tmuxinator Dev Launchers

These tmuxinator profiles are the current development launcher for MoreTea while the robot, Nav stack, and voice stack are still changing frequently.

## Install

Install `tmux` and `tmuxinator` on each machine, then install the repo-tracked profiles into your local tmuxinator config:

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

## OpenClaw PC

Before starting the voice profile, export the robot SSH details:

```bash
export ROBOT_USER=<robot-user>
export ROBOT_HOST=<robot-ip>
```

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

## Verification

After both profiles are up:

```bash
curl -i -H 'Accept: text/event-stream' http://127.0.0.1:8765/mcp
curl http://127.0.0.1:8000/v1/models
```

Then call MCP `health` first and confirm:

- `navigation_ready: true`
- `tour_navigation.nav2_import_ready: true`

`tour_navigation.nav2_active_check_bypassed: true` is acceptable in the current Humble setup.

For the full cross-machine launch and troubleshooting guide, use:

- [RUNBOOK.md](/home/frentzen/FYP/RUNBOOK.md)
