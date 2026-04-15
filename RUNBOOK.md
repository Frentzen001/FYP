# MoreTea Runbook

This is the canonical operator runbook for the current MoreTea launch path.

It covers the full cross-machine flow:

- robot bringup and Nav2
- robot-side MCP server
- SSH tunnel (MCP) from the remote desktop to robot PC
- Speaches on the remote desktop (GPU)
- SSH tunnel (Speaches) from the robot PC to remote desktop
- barebone OpenClaw voice worker on the robot PC
- MCP verification before voice prompts

**Audio split topology:**

```
Remote Desktop (GPU)              Robot PC
─────────────────────             ─────────────────────────────
Speaches :8000        ←── tunnel ── localhost:8000 (voice worker)
OpenClaw LLM                       openclaw_barebone.py
openclaw_tunnel.sh                 mic + speaker (local hardware)
  (→ Robot PC :8765)               ROS2 + Robot MCP :8765
```

The Speaches models (STT/TTS) run on the remote desktop GPU. The voice worker runs on the robot PC alongside the physical mic and speaker. An SSH tunnel makes `localhost:8000` on the robot PC transparently reach the remote desktop's Speaches.

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

Remote desktop (starts Speaches + MCP tunnel to robot):

```bash
export ROBOT_USER=<robot-user>
export ROBOT_HOST=<robot-ip>
tmuxinator start moretea_voice
```

Robot PC (starts ROS2, MCP, Speaches tunnel, voice worker):

```bash
export DESKTOP_HOST=<remote-desktop-ip>
export DESKTOP_USER=<ssh-username-on-desktop>
tmuxinator start moretea_robot
```

`autossh` requirements:

- remote desktop: `autossh` for the MCP tunnel pane (`openclaw_tunnel.sh`)
- robot PC: `autossh` for the Speaches tunnel pane (`speaches_tunnel.sh`)

Tmuxinator details:

- [tmuxinator/README.md](/home/frentzen/FYP/tmuxinator/README.md)

## Manual Launch Order

If you need to launch manually, keep this order:

**Remote desktop:**
1. Speaches (GPU)
2. MCP tunnel → Robot PC (port 8765)

**Robot PC:**
3. Robot bringup and Nav2
4. Robot MCP server
5. Speaches tunnel → Remote desktop (port 8000)
6. Barebone OpenClaw voice worker (after tunnel is up)
7. MCP `health` check before voice prompts

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

## Remote Desktop

### Open the MCP tunnel (remote desktop → robot PC)

```bash
cd /home/frentzen/FYP/moretea-robot-mcp
ROBOT_USER=<robot-user> ROBOT_HOST=<robot-ip> ./scripts/openclaw_tunnel.sh
```

Expected behavior:

- the command stays open
- the tunnel stays attached to the current terminal or tmux pane
- the startup banner shows the robot host, SSH user, and forwarded ports
- `autossh` retries after short drops instead of leaving the tunnel dead silently

Remote desktop requirement:

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

### Start Speaches (remote desktop)

Prerequisites:

- Docker installed and usable by the current user

```bash
cd /home/frentzen/FYP/agent-starter-python
./scripts/run_speaches.sh
```

Verify Speaches is ready:

```bash
curl http://127.0.0.1:8000/v1/models
```

### Start the Speaches tunnel (robot PC → remote desktop)

Run this on the **robot PC** after Speaches is up on the remote desktop:

```bash
cd /home/frentzen/FYP/moretea-robot-mcp
DESKTOP_HOST=<remote-desktop-ip> DESKTOP_USER=<ssh-user> ./scripts/speaches_tunnel.sh
```

Robot PC requirement:

- `autossh` must be installed
- SSH key-based login to the remote desktop is strongly recommended

Verify tunnel from robot PC:

```bash
curl http://127.0.0.1:8000/v1/models
```

### Start the voice worker (robot PC)

Prerequisites:

- Speaches tunnel is up (port 8000 reachable on robot PC)
- valid `agent-starter-python/.env.local` on the robot PC

Create it from the template if needed:

```bash
cd /home/frentzen/FYP/agent-starter-python
cp .env.example .env.local
```

Key values in `.env.local` on robot PC:

```env
USE_LOCAL_MODELS=1
LOCAL_STT_BASE_URL=http://127.0.0.1:8000/v1
LOCAL_TTS_BASE_URL=http://127.0.0.1:8000/v1
MORETEA_OPENCLAW_URL=http://<remote-desktop-ip>:<port>/v1
```

Start the worker:

```bash
cd /home/frentzen/FYP/agent-starter-python
./scripts/run_openclaw_barebone.sh
```

Thinking cue:

- the barebone worker plays its short acceptance chirp through the **robot PC speaker**
- this is the intended behavior — the cue plays on the same machine as the mic and speaker

Before relying on robot tools:

- confirm the MCP tunnel pane (remote desktop) is running cleanly
- run `./scripts/probe_tunneled_mcp.sh` from `moretea-robot-mcp` on remote desktop
- call MCP `health`

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
- Blocking physical actions are child-only: the main agent spawns a child session, and the child calls exactly one action tool plus `sessions_send`
- The canonical navigation action is `moretea_robot_navigate_to_stop`

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

## Observability Debugging

For failed motion or navigation child actions, the observability aggregator is the required debug path.

Start the aggregator:

```bash
cd /home/frentzen/FYP/moretea-observability-ui
uv sync
uv run python backend.py
```

Then enable producers:

User-laptop / voice runtime:

```bash
export MORETEA_OBSERVABILITY_ENABLED=1
export MORETEA_OBSERVABILITY_BASE_URL=http://127.0.0.1:4173
export MORETEA_OBSERVABILITY_MACHINE_ID=user-laptop
```

Robot MCP:

```bash
export MORETEA_OBSERVABILITY_ENABLED=1
export MORETEA_OBSERVABILITY_BASE_URL=http://127.0.0.1:4173
export MORETEA_OBSERVABILITY_MACHINE_ID=robot-pc
export MORETEA_OBSERVABILITY_ROBOT_SNAPSHOT_INTERVAL_S=2
```

Optional OpenClaw PC reporter:

```bash
cd /home/frentzen/FYP/moretea-observability-ui
MORETEA_OBSERVABILITY_BASE_URL=http://127.0.0.1:4173 python3 openclaw_pc_reporter.py
```

After reproducing one failed action such as `rotate 5 degrees`, inspect:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path("/tmp/moretea-observability-state.json")
data = json.loads(p.read_text())
turn = data["turns"][0]
print(json.dumps({
    "tool_executions": turn.get("tool_executions", []),
    "timeline_events": turn.get("timeline_events", []),
    "session_structure": turn.get("session_structure", {}),
}, indent=2))
PY
```

The expected chain for a healthy child rotate flow is:

- main `moretea_robot_health`
- main `sessions_spawn`
- child lifecycle: `spawned` -> `running` -> `completed`
- robot-side `rotate_angle` tool execution
- child `sessions_send`

If the child reports success without any matching tool result, the snapshot should show `child_session_report_without_tool_result`.

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
- `navigate_to_stop("fabrication_lab")` — child-only blocking tool; returns a terminal result
- `cancel_navigation()`
- `get_navigation_status()` — optional status/debug snapshot

Navigation pattern (mandatory for OpenClaw):

1. main agent calls `list_tour_stops()`
2. main agent acknowledges the destination in one short sentence
3. main agent calls `sessions_spawn(...)`
4. child agent calls `navigate_to_stop(stop_id)` exactly once
5. child agent calls `sessions_send(...)` exactly once with the terminal result
6. if a visitor asks for a progress update mid-navigation, call `get_navigation_status()` and answer briefly

Do not manage `action_id`, prompt-level polling, replan handling, or retry loops in OpenClaw prompt logic.

Robot motion pattern (mandatory for OpenClaw):

1. main agent calls `health()`
2. if `motion_confirmable` is false, refuse motion
3. otherwise main agent calls `sessions_spawn(...)`
4. child agent calls either `move_distance(...)` or `rotate_angle(...)` exactly once
5. child agent calls `sessions_send(...)` exactly once with the terminal result

Never call `move_distance` or `rotate_angle` from the main interactive turn.

Containerized OpenClaw CLI tracing:

```bash
cd /home/frentzen/FYP/moretea-observability-ui
python3 openclaw_trace_cli.py -- docker exec moretea-openclaw openclaw agent --local --session-id main --verbose on --message "rotate 5 degrees" --json
```

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

If `nav2_active_check_bypassed` is `true`, do a short real `navigate_to_stop` test next from a child session.

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

### `autossh` is missing on the remote desktop or robot PC

Symptoms:

- the `tunnel` pane exits immediately with an `autossh is required` message

Fix (remote desktop — MCP tunnel):

- install `autossh` on the remote desktop
- restart the `tunnel` pane or relaunch `tmuxinator start moretea_voice`

Fix (robot PC — Speaches tunnel):

- install `autossh` on the robot PC
- restart the `speaches_tunnel` pane or relaunch `tmuxinator start moretea_robot`

### Speaches tunnel is up but voice worker cannot reach STT/TTS

Symptoms:

- `curl http://127.0.0.1:8000/v1/models` on the robot PC fails or times out
- voice worker logs STT/TTS connection errors

Check:

- Speaches is running on the remote desktop (`curl http://127.0.0.1:8000/v1/models` on remote desktop)
- the `speaches_tunnel` pane is open and not repeatedly failing
- `DESKTOP_HOST` and `DESKTOP_USER` are set correctly
- SSH key-based login from robot PC → remote desktop works without a password prompt

### Tunnel prompts for a password or fails with `Permission denied`

Symptoms:

- a `tunnel` pane asks for an SSH password
- reconnects are not automatic
- SSH eventually fails with `Permission denied`

For the MCP tunnel (remote desktop → robot PC):

- `ROBOT_USER` matches the actual SSH username on the robot PC
- `ROBOT_HOST` points at the robot PC IP or hostname
- plain `ssh <robot-user>@<robot-ip>` works from the remote desktop without a password

For the Speaches tunnel (robot PC → remote desktop):

- `DESKTOP_USER` matches the actual SSH username on the remote desktop
- `DESKTOP_HOST` points at the remote desktop IP or hostname
- plain `ssh <desktop-user>@<desktop-ip>` works from the robot PC without a password

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
