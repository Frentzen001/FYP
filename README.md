# MoreTea Workspace

MoreTea is a Garage@EEE companion robot built around:

- OpenClaw for reasoning, memory, and tool selection
- robot-side MCP servers for embodied capabilities
- ROS 2 Humble + Nav2 on the robot PC
- LiveKit as the current voice transport into OpenClaw

This repository root is the developer entrypoint for the workspace. It is intentionally short and link-driven.

## Current Robot MCP Highlights

Current robot-side MCP capabilities include:

- navigation primitives for tours and point-to-point movement
- eye-expression control
- `capture_image` for returning the latest buffered camera frame to OpenClaw as base64 JPEG
- `get_recognized_faces` for returning the latest face-recognition snapshot as structured names/confidences
- `register_face` for saving a newly met person's face through the robot-side ROS service

See [moretea-robot-mcp/README.md](/home/frentzen/FYP/moretea-robot-mcp/README.md) for the repo-local tool surface and implementation details.

## Active Repos

- [agent-starter-python](/home/frentzen/FYP/agent-starter-python/README.md)
  Voice-side runtime, LiveKit integration, OpenClaw bridge, local model setup.
- [moretea-robot-mcp](/home/frentzen/FYP/moretea-robot-mcp/README.md)
  Robot-side MCP tools, ROS-facing execution, launch runbook, feature extension guide.
- [tmuxinator](/home/frentzen/FYP/tmuxinator/README.md)
  Current development launcher for the robot PC and OpenClaw PC.

Archived or reference-only repos:

- [moretea-spine](/home/frentzen/FYP/moretea-spine/README.md)
- `rosclaw/`

## Canonical Docs

- [PRD.md](/home/frentzen/FYP/PRD.md)
  Product goals, architecture, ownership boundaries, functional requirements.
- [PROGRESS.md](/home/frentzen/FYP/PROGRESS.md)
  Current verified state, recent milestones, known gaps, next milestone.
- [TODO.md](/home/frentzen/FYP/TODO.md)
  Active engineering backlog.
- [RUNBOOK.md](/home/frentzen/FYP/RUNBOOK.md)
  Canonical operator launch, verification, and troubleshooting guide.
- [AGENTS.md](/home/frentzen/FYP/AGENTS.md)
  Cross-repo coding-agent guide for this workspace.

Repo-specific docs:

- [agent-starter-python/README.md](/home/frentzen/FYP/agent-starter-python/README.md)
- [agent-starter-python/AGENTS.md](/home/frentzen/FYP/agent-starter-python/AGENTS.md)
- [RUNBOOK.md](/home/frentzen/FYP/RUNBOOK.md)
- [moretea-robot-mcp/docs/ADDING_FEATURES.md](/home/frentzen/FYP/moretea-robot-mcp/docs/ADDING_FEATURES.md)
- [tmuxinator/README.md](/home/frentzen/FYP/tmuxinator/README.md)

## Start Here

If you are new to the workspace:

1. Read [PRD.md](/home/frentzen/FYP/PRD.md) for the architecture and ownership model.
2. Read [PROGRESS.md](/home/frentzen/FYP/PROGRESS.md) for what is actually working today.
3. Bootstrap the Python environments:
   - `./bootstrap_dev.sh`
4. Install the dev launchers from [tmuxinator/README.md](/home/frentzen/FYP/tmuxinator/README.md).
5. Use the repo-specific docs depending on what you are touching:
   - voice/runtime work: [agent-starter-python/README.md](/home/frentzen/FYP/agent-starter-python/README.md)
   - robot/MCP work: [moretea-robot-mcp/README.md](/home/frentzen/FYP/moretea-robot-mcp/README.md)
   - operator launch/debug: [RUNBOOK.md](/home/frentzen/FYP/RUNBOOK.md)

## Current Development Launch

The preferred dev workflow is tmuxinator:

- robot PC: `tmuxinator start moretea_robot`
- OpenClaw PC: `tmuxinator start moretea_voice`

See [tmuxinator/README.md](/home/frentzen/FYP/tmuxinator/README.md) for install and usage.
