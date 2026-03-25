# MoreTea Robot MCP

`moretea-robot-mcp` is the active robot-side runtime for MoreTea.

It owns:

- robot-facing MCP tools
- ROS-facing capability wrappers
- robot-side launch and troubleshooting docs
- the shared tour stop catalog used by the current robot MCP path

It does not own:

- OpenClaw reasoning or long-term memory
- LiveKit voice orchestration
- high-level tour narration policy

## Current Architecture Role

Current control path:

```text
LiveKit -> OpenClaw -> native MCP client -> robot MCP server -> ROS 2 Humble
```

OpenClaw is the intended MCP consumer.  
This repo is the bounded execution surface on the robot PC.

## Current MCP Tool Surface

- `health`
- `express_emotion`
- `list_tour_stops`
- `start_navigation_to_stop`
- `get_navigation_action_status`
- `navigate_to_stop` as a compatibility wrapper
- `cancel_navigation`
- `get_navigation_status`

Temporary navigation note:

- the robot MCP server currently defaults to `MORETEA_BYPASS_NAV2_ACTIVE_WAIT=1`
- startup verifies ROS and `BasicNavigator` imports
- actual navigation readiness is confirmed at goal time
- `health` exposes `nav2_import_ready`, `nav2_active_check_bypassed`, `readiness_detail`, and `startup_error`

## Start Here

- [Workspace runbook](/home/frentzen/FYP/RUNBOOK.md)
  Exact cross-machine startup order, verification, and troubleshooting.
- [Adding a new robot feature](docs/ADDING_FEATURES.md)
  How to extend the robot through MCP tools.

## Key Files

- [server.py](/home/frentzen/FYP/moretea-robot-mcp/src/moretea_robot_mcp/server.py)
  MCP server and tool registration.
- [tour_navigation.py](/home/frentzen/FYP/moretea-robot-mcp/src/moretea_robot_mcp/tour_navigation.py)
  Current Humble navigation wrapper.
- [navigation_status.py](/home/frentzen/FYP/moretea-robot-mcp/src/moretea_robot_mcp/navigation_status.py)
  Read-only navigation observer.
- [ros_eye_publisher.py](/home/frentzen/FYP/moretea-robot-mcp/src/moretea_robot_mcp/ros_eye_publisher.py)
  Eye-expression publisher lifecycle.
- [tour_stops.yaml](/home/frentzen/FYP/moretea-robot-mcp/config/tour_stops.yaml)
  Shared stable tour stop catalog.

## Development Launch

Preferred dev launcher:

- [tmuxinator/README.md](/home/frentzen/FYP/tmuxinator/README.md)

Operator launch steps:

- [RUNBOOK.md](/home/frentzen/FYP/RUNBOOK.md)

## Local Verification

```bash
cd /home/frentzen/FYP/moretea-robot-mcp
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest -q tests/test_eye_control.py tests/test_ros_eye_publisher.py tests/test_navigation_status.py tests/test_tour_stops.py tests/test_tour_navigation.py tests/test_server.py
```
