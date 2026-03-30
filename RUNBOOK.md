# MoreTea Runbook

This is the canonical operator runbook for the current MoreTea launch path.

It covers the full cross-machine flow:

- robot bringup and Nav2
- robot-side MCP server
- SSH tunnel from the OpenClaw PC
- Speaches
- barebone OpenClaw voice worker
- MCP verification before voice prompts

For repo-local concepts, use:

- [agent-starter-python/README.md](/home/frentzen/FYP/agent-starter-python/README.md)
- [moretea-robot-mcp/README.md](/home/frentzen/FYP/moretea-robot-mcp/README.md)

## Preferred Development Launch

Use tmuxinator for daily development.

Fresh clone bootstrap:

```bash
cd /home/frentzen/FYP
./bootstrap_dev.sh
```

Install the profiles once on each machine:

```bash
cd /home/frentzen/FYP
./tmuxinator/install_profiles.sh
```

Robot PC:

```bash
tmuxinator start moretea_robot
```

OpenClaw PC:

```bash
export ROBOT_USER=<robot-user>
export ROBOT_HOST=<robot-ip>
tmuxinator start moretea_voice
```

Tmuxinator details:

- [tmuxinator/README.md](/home/frentzen/FYP/tmuxinator/README.md)

## Manual Launch Order

If you need to launch manually, keep this order:

1. Robot bringup and Nav2
2. Robot MCP server
3. SSH tunnel from the OpenClaw PC
4. Speaches on the OpenClaw PC
5. barebone OpenClaw worker
6. MCP `health` check before voice prompts

## Robot PC

### Prerequisites

- ROS 2 Humble
- Nav2 already running
- Python environment synced with `uv sync`
- robot ROS packages present on the machine:
  - `linorobot2_bringup`
  - `linorobot2_navigation`
  - `micro_ros_agent`
  - `moretea_arm`

### BasicNavigator import preflight

```bash
source /opt/ros/humble/setup.bash
cd /home/frentzen/FYP/moretea-robot-mcp
uv run python - <<'PY'
from nav2_simple_commander.robot_navigator import BasicNavigator
print("BasicNavigator import OK")
PY
```

If this fails, repair the environment:

```bash
cd /home/frentzen/FYP/moretea-robot-mcp
uv sync
```

### Start the robot MCP server

```bash
cd /home/frentzen/FYP/moretea-robot-mcp
pkill -f moretea_robot_mcp.server || true
./scripts/run_robot_mcp.sh
```

Optional eye-expression watcher:

```bash
cd /home/frentzen/FYP/moretea-robot-mcp
./scripts/watch_eye_expression.sh
```

### Current Nav2 startup behavior

Current default:

- `MORETEA_BYPASS_NAV2_ACTIVE_WAIT=1`

This means:

- startup verifies ROS and `BasicNavigator` imports
- startup does not hard-block on `waitUntilNav2Active()`
- real navigation truth is confirmed at goal time

If you want strict startup waiting for debugging:

```bash
cd /home/frentzen/FYP/moretea-robot-mcp
MORETEA_BYPASS_NAV2_ACTIVE_WAIT=0 ./scripts/run_robot_mcp.sh
```

## OpenClaw PC

### Open the SSH tunnel

```bash
cd /home/frentzen/FYP/moretea-robot-mcp
ROBOT_USER=<robot-user> ROBOT_HOST=<robot-ip> ./scripts/openclaw_tunnel.sh
```

Expected behavior:

- the command stays open
- the tunnel remains quiet unless it fails

### Verify the tunneled MCP endpoint

```bash
curl -i -H 'Accept: text/event-stream' http://127.0.0.1:8765/mcp
```

Acceptable probe result:

- reachable endpoint
- may return `406`
- must not be `ECONNREFUSED`

### Start the voice-side tools

Prerequisites:

- Docker installed and usable by the current user
- valid `agent-starter-python/.env.local`

Create it from the template if needed:

```bash
cd /home/frentzen/FYP/agent-starter-python
cp .env.example .env.local
```

Speaches:

```bash
cd /home/frentzen/FYP/agent-starter-python
./scripts/run_speaches.sh
```

Barebone worker:

```bash
cd /home/frentzen/FYP/agent-starter-python
./scripts/run_openclaw_barebone.sh
```

Or combined:

```bash
cd /home/frentzen/FYP/agent-starter-python
./scripts/dev_voice_stack.sh
```

Verify Speaches:

```bash
curl http://127.0.0.1:8000/v1/models
```

## MCP Verification

Before testing OpenClaw prompts, call `health` first.

Expected fields:

- `robot_control_ready: true`
- `navigation_ready: true`
- `tour_navigation.nav2_import_ready: true`
- `tour_navigation.startup_error: null`

In the current Humble setup it is acceptable to also see:

- `tour_navigation.nav2_active_check_bypassed: true`

That means the server is using the temporary startup bypass and real navigation truth is checked at goal time.

## Current Tool Checks

Robot emotion:

- `express_emotion("happy")`
- `express_emotion("confused")`

Robot navigation:

- `list_tour_stops()`
- `start_navigation_to_stop("fabrication_lab")`
- `get_navigation_action_status(action_id)`
- `cancel_navigation()`
- `get_navigation_status()`

Compatibility tool:

- `navigate_to_stop("fabrication_lab")`

Use action-style navigation as the preferred path.

## Troubleshooting

### Port `8765` is already in use

Clear stale MCP processes and restart:

```bash
cd /home/frentzen/FYP/moretea-robot-mcp
pkill -f moretea_robot_mcp.server || true
./scripts/run_robot_mcp.sh
```

### Eye tools work but navigation does not

Check in this order:

1. Nav2 is already running on the robot.
2. `BasicNavigator` import preflight passes.
3. the MCP server was restarted after Nav2 was up.
4. `health` shows:
   - `navigation_ready: true`
   - `tour_navigation.nav2_import_ready: true`

If `nav2_active_check_bypassed` is `true`, do a short real `start_navigation_to_stop` test next.

### Non-loopback bind is rejected

The server fails closed unless you explicitly allow a non-loopback bind.

Default recommendation:

- keep the MCP server on `127.0.0.1`
- use SSH tunneling from the OpenClaw PC

If you intentionally want a non-loopback bind:

```bash
export MORETEA_ROBOT_MCP_ALLOW_NONLOCAL=1
```

### OpenClaw cannot see robot tools

Check:

- the robot MCP server is up
- the SSH tunnel is open
- `curl` to `http://127.0.0.1:8765/mcp` works on the OpenClaw PC
- `health` works before you test prompts
