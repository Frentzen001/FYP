# MoreTea Progress

**Last updated:** 25 March 2026  
**Current stack:** OpenClaw, native MCP client, robot-side MCP servers, LiveKit voice runtime, ROS 2 Humble

## Current Verified State

### Architecture

- OpenClaw is the intended cognitive core.
- Robot-side MCP servers are the current execution boundary.
- `agent-starter-python` is the active voice/runtime repo.
- `moretea-robot-mcp` is the active robot/runtime repo.
- `moretea-spine` is archived and not part of the current runtime.

### Robot MCP

Verified in the current robot MCP path:

- `health`
- `express_emotion`
- `list_tour_stops`
- `start_navigation_to_stop`
- `get_navigation_action_status`
- `navigate_to_stop` as compatibility wrapper
- `cancel_navigation`
- `get_navigation_status`

Current navigation note:

- the MCP server defaults to `MORETEA_BYPASS_NAV2_ACTIVE_WAIT=1`
- startup no longer hard-blocks on `waitUntilNav2Active()`
- `health` exposes `nav2_import_ready`, `nav2_active_check_bypassed`, `readiness_detail`, and `startup_error`

### Voice / Launch

- the current barebone voice entrypoint is [openclaw_barebone.py](/home/frentzen/FYP/agent-starter-python/src/openclaw_barebone.py)
- Speaches is the current local STT/TTS path
- tmuxinator is now the preferred development launcher:
  - `tmuxinator start moretea_robot`
  - `tmuxinator start moretea_voice`

## Recent Milestones

### 1. Tmuxinator dev launchers

Added repo-tracked tmuxinator profiles plus an installer so development startup is repeatable across the robot PC and OpenClaw PC.

### 2. Temporary Nav2 readiness bypass

The robot MCP server now starts even when the robot’s Humble Nav2 stack does not expose the full standard lifecycle-managed readiness surface expected by `BasicNavigator`.

### 3. Action-style robot navigation contract

The robot MCP server now exposes:

- `start_navigation_to_stop`
- `get_navigation_action_status`
- `cancel_navigation`

while keeping `navigate_to_stop` as a compatibility tool.

### 4. Humble robot-side MCP tour/navigation baseline

The robot MCP repo now owns:

- shared tour stop catalog
- navigation primitives
- eye-expression control
- launch/runbook docs

## Current Gaps

- real end-to-end OpenClaw use of the navigation tools still needs more hardware validation
- Nav2 readiness remains a temporary bypass, not the final architecture
- real Garage waypoint calibration still needs validation
- cloud-backed LiveKit eval coverage is still incomplete
- tour policy remains split between current MCP primitives and longer-term OpenClaw ownership goals

## Next Milestone

Stabilize the real end-to-end tour flow on hardware:

- OpenClaw uses the current MCP navigation and robot tools reliably
- navigation behavior is verified in the Garage
- current docs stay aligned with the actual launch and runtime path
