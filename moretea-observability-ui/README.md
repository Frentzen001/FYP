# MoreTea Observability UI

Standalone operator dashboard and aggregator API for the current three-machine MoreTea runtime:

- User laptop
  - `Speaches`
  - `LiveKit agent`
  - `MCP server`
- OpenClaw PC
  - `openclaw-docker`
  - `openclaw-ssh-tunnel`
- Robot PC
  - ROS 2 / navigation / sensors / robot control

## What this implements

The app now includes:

- a browser-facing aggregator API
- SSE live updates for the dashboard
- an OpenClaw-PC reporter script
- an OpenClaw CLI trace wrapper
- a normalized state model for machines, links, turns, tools, and robot state

The dashboard visualizes:

- machine topology and link health
- per-turn timeline events
- transcript and OpenClaw reply
- attention state
- MCP tool executions
- navigation / degraded-mode robot state
- robot readiness and telemetry
- face recognition / memory activity
- raw structured payload inspection

The normalized per-turn contract centers on:

- `tool_executions`
- `timeline_events`
- `session_structure`

The current implementation is wired for live data:

- user laptop runtime emits turn and voice/OpenClaw events
- robot MCP emits tool executions plus periodic robot snapshots
- OpenClaw PC reporter emits node/link health
- the browser reads only from the aggregator API

## Run locally

## Run the aggregator

From the workspace root:

```bash
cd /home/morerobot/FYP/moretea-observability-ui
uv sync
uv run python backend.py
```

Then open:

```text
http://127.0.0.1:4173
```

```text
http://127.0.0.1:4173
```

## Producers

### User laptop

Set these env vars for the LiveKit/OpenClaw bridge:

```env
MORETEA_OBSERVABILITY_ENABLED=1
MORETEA_OBSERVABILITY_BASE_URL=http://<aggregator-host>:4173
MORETEA_OBSERVABILITY_MACHINE_ID=user-laptop
```

The voice runtime will emit:

- transcript and attention events
- OpenClaw request/response lifecycle
- TTS playback events
- user-laptop service heartbeats

### Robot PC

Set these env vars for the robot MCP process:

```env
MORETEA_OBSERVABILITY_ENABLED=1
MORETEA_OBSERVABILITY_BASE_URL=http://<aggregator-host>:4173
MORETEA_OBSERVABILITY_MACHINE_ID=robot-pc
MORETEA_OBSERVABILITY_ROBOT_SNAPSHOT_INTERVAL_S=2
```

The MCP server will emit:

- tool start/finish events
- periodic robot readiness snapshots
- ROS/navigation/sensor/control service heartbeats

### OpenClaw PC

Run the reporter script on the OpenClaw PC:

```bash
cd /home/morerobot/FYP/moretea-observability-ui
MORETEA_OBSERVABILITY_BASE_URL=http://<aggregator-host>:4173 python3 openclaw_pc_reporter.py
```

Optional env vars:

```env
MORETEA_OPENCLAW_CONTAINER_NAME=moretea-openclaw
MORETEA_OPENCLAW_TUNNEL_PROBE_URL=http://127.0.0.1:8765/mcp
MORETEA_OPENCLAW_REPORT_INTERVAL_S=5
```

### OpenClaw CLI trace wrapper

For local CLI debugging, run OpenClaw through the wrapper so the output includes:

- `tool_executions`
- `timeline_events`
- `session_structure`

Example:

```bash
cd /home/morerobot/FYP/moretea-observability-ui
python3 openclaw_trace_cli.py -- openclaw agent --local --session-id main --verbose on --message "rotate 90 degrees" --json
```

This preserves the original assistant-visible payloads and adds structured trace fields parsed from the verbose agent logs.

## Current v1 limits

- explicit OpenClaw child-session visibility is still inferred unless a producer reports it directly
- built-in OpenClaw tools are only as visible as the current verbose logs allow; full child-tool result tracing still needs upstream OpenClaw runtime support
- the dashboard preserves the existing UI shell and focuses on observability, not control
- browser clients never talk to the three machines directly

## File layout

- [index.html](/home/morerobot/FYP/moretea-observability-ui/index.html)
  Main dashboard structure
- [styles.css](/home/morerobot/FYP/moretea-observability-ui/styles.css)
  Visual design and responsive layout
- [app.js](/home/morerobot/FYP/moretea-observability-ui/app.js)
  Live API rendering and SSE update handling
- [backend.py](/home/morerobot/FYP/moretea-observability-ui/backend.py)
  Aggregator API, normalized state store, and static-file serving
- [openclaw_pc_reporter.py](/home/morerobot/FYP/moretea-observability-ui/openclaw_pc_reporter.py)
  OpenClaw PC machine/link health producer
- [openclaw_trace_cli.py](/home/morerobot/FYP/moretea-observability-ui/openclaw_trace_cli.py)
  Local wrapper that enriches `openclaw agent --json` with tool/session trace fields
