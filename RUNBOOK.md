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

OpenClaw-side requirement:

- `autossh` installed so the visible `tunnel` pane can reconnect after short drops

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
- the tunnel stays attached to the current terminal or tmux pane
- the startup banner shows the robot host, SSH user, and forwarded ports
- `autossh` retries after short drops instead of leaving the tunnel dead silently

OpenClaw PC requirement:

- `autossh` must be installed for the visible tunnel workflow
- SSH key-based login to the robot PC is strongly recommended so reconnects do not get stuck on a password prompt

Install `autossh` on Ubuntu:

```bash
sudo apt update
sudo apt install autossh
autossh -V
```

Recommended one-time SSH setup:

```bash
ssh-keygen -t ed25519
ssh-copy-id <robot-user>@<robot-ip>
ssh <robot-user>@<robot-ip>
```

Expected result:

- the plain `ssh` login works without prompting for a password before you rely on `autossh`

Optional tunnel overrides:

- `LOCAL_PORT` to change the local forwarded port
- `REMOTE_PORT` to change the robot-side MCP port
- `SSH_SERVER_ALIVE_INTERVAL` to change the SSH keepalive interval
- `SSH_SERVER_ALIVE_COUNT_MAX` to change how many keepalive misses are tolerated

### Verify the tunneled MCP endpoint

```bash
cd /home/frentzen/FYP/moretea-robot-mcp
./scripts/probe_tunneled_mcp.sh
```

Acceptable probe result:

- reachable endpoint
- may return `406`
- must not be `ECONNREFUSED`

Optional probe overrides:

- `MCP_URL` to point at a different tunneled MCP endpoint
- `MAX_ATTEMPTS` to change how many probe retries run
- `SLEEP_SECONDS` to change the delay between retries
- `CONNECT_TIMEOUT_SECONDS` to change the per-attempt connect timeout
- `MAX_TIME_SECONDS` to change the total per-attempt curl timeout

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

Thinking cue check:

- the barebone worker now plays its short acceptance chirp through the local machine speaker
- no LiveKit room join is required to hear it during console/dev runs

Or combined:

```bash
cd /home/frentzen/FYP/agent-starter-python
./scripts/dev_voice_stack.sh
```

Before relying on robot tools:

- confirm the SSH tunnel terminal or tmux `tunnel` pane is running cleanly
- run `./scripts/probe_tunneled_mcp.sh` from `moretea-robot-mcp`
- call MCP `health`

Verify Speaches:

```bash
curl http://127.0.0.1:8000/v1/models
```

## OpenClaw Agent Config

The OpenClaw agent config lives in `rosclaw-docker/`:

- `openclaw.json` — tool allow-list, model params, gateway config
- `workspace-soul.md` — agent system prompt and navigation pattern
- `skills/SKILL.md` — tool-by-tool usage reference

After any change to these files, restart the container:

```bash
cd /home/frentzen/FYP/rosclaw-docker
docker compose restart rosclaw-isolated
```

Key config facts:
- Tools must be in the `tools.allow` list in `openclaw.json` to be callable
- `moretea_robot_navigate_to_stop` is removed — do not re-add it (blocked the HTTP connection)
- `moretea_robot_wait_for_navigation_action` is the replacement — event-driven, max 25s per call

---

## MCP Verification

Before testing OpenClaw prompts:

1. confirm the SSH tunnel terminal or tmux `tunnel` pane is running cleanly
2. run `./scripts/probe_tunneled_mcp.sh`
3. call `health`

Expected fields:

- `robot_control_ready: true`
- `navigation_ready: true`
- `tour_navigation.nav2_import_ready: true`
- `tour_navigation.startup_error: null`

In the current Humble setup it is acceptable to also see:

- `tour_navigation.nav2_active_check_bypassed: true`

That means the server is using the temporary startup bypass and real navigation truth is checked at goal time.

## Current Tool Checks

Robot motion:

- `move(angular_z=0.4, duration_s=2.0)` — timed velocity control
- `move_distance(distance_m=0.5)` — fixed-distance travel (closed-loop via odometry)
- `rotate_angle(angle_deg=90)` — rotate left 90° (closed-loop via odometry)
- `rotate_angle(angle_deg=-180)` — rotate right 180°
- `stop_motion()` — immediate halt

Robot emotion:

- `express_emotion("happy")`
- `express_emotion("confused")`

Robot navigation:

- `list_tour_stops()`
- `start_navigation_to_stop("fabrication_lab")` — returns immediately with `action_id`
- `wait_for_navigation_action(action_id, max_wait_s=90)` — polls up to 90 s; returns early on reroute/recovery events or timeout
- `get_navigation_action_status(action_id)` — one-shot status snapshot without blocking
- `cancel_navigation()`
- `get_navigation_status()`

Navigation pattern (mandatory for OpenClaw):

1. call `start_navigation_to_stop` → get `action_id`
2. tell the visitor you are heading there (≤10 words)
3. call `wait_for_navigation_action(action_id, max_wait_s=10)` — ONE call per turn:
   - `event="replan"` → speak `last_event_note` in ≤8 words, end turn
   - `event="recovery"` → speak `last_event_note` in ≤8 words, end turn
   - `timed_out=True` → give a short distance update, end turn
   - `event=None, timed_out=False` → navigation finished, report outcome, end turn
4. if visitor asks a question mid-navigation: call `get_navigation_action_status` (instant), answer, end turn — do NOT call `wait_for_navigation_action` unless they ask for a navigation update

Each turn ends after one wait call. Navigation continues in the background. This prevents LiveKit turn timeouts.

The `last_event_note` strings are already human-readable and suitable to speak directly.
Each poll cycle is 50 ms, so reroute events are surfaced within ~50 ms of occurring.

Note: `navigate_to_stop` is no longer exposed as an MCP tool — it blocked the HTTP connection for the full navigation duration and caused timeouts. The previous unlimited wait loop had the same problem and is now replaced with one wait call per turn.

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
- the SSH tunnel terminal or tmux `tunnel` pane is open and not repeatedly failing
- `./scripts/probe_tunneled_mcp.sh` works on the OpenClaw PC
- `health` works before you test prompts

### `autossh` is missing on the OpenClaw PC

Symptoms:

- the `tunnel` pane exits immediately with an `autossh is required` message

Fix:

- install `autossh` on the OpenClaw PC
- restart the `tunnel` pane or relaunch `tmuxinator start moretea_voice`

### Tunnel prompts for a password or fails with `Permission denied`

Symptoms:

- the `tunnel` pane asks for an SSH password
- reconnects are not automatic
- SSH eventually fails with `Permission denied`

Check:

- `ROBOT_USER` matches the actual SSH username on the robot PC
- `ROBOT_HOST` points at the robot PC IP or hostname
- plain `ssh <robot-user>@<robot-ip>` works from the OpenClaw PC
- SSH key-based login is configured so `autossh` can reconnect without manual input

### Tunnel is open but the robot MCP backend is unavailable

Symptoms:

- the `tunnel` pane stays open
- `./scripts/probe_tunneled_mcp.sh` fails or keeps retrying

Check:

- the robot MCP server is actually running on the robot PC
- the robot MCP server was restarted after Nav2 came up
- `health` works once the probe succeeds

### Tunnel repeatedly reconnects

Symptoms:

- the `tunnel` pane shows repeated reconnect attempts

Check:

- the robot PC is reachable over SSH
- the robot network is stable
- the robot MCP server is up after the SSH session recovers
