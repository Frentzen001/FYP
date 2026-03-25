# Workspace AGENTS.md

This file is the cross-repo coding-agent guide for the MoreTea workspace.

Use this first for workspace context.  
Use [agent-starter-python/AGENTS.md](/home/frentzen/FYP/agent-starter-python/AGENTS.md) for LiveKit-specific guidance.

## Active Repos

- [agent-starter-python](/home/frentzen/FYP/agent-starter-python/README.md)
  Active voice/runtime repo.
- [moretea-robot-mcp](/home/frentzen/FYP/moretea-robot-mcp/README.md)
  Active robot-side MCP runtime and docs.
- [tmuxinator](/home/frentzen/FYP/tmuxinator/README.md)
  Current development launcher profiles.

Archived or reference-only:

- [moretea-spine](/home/frentzen/FYP/moretea-spine/README.md)
- `rosclaw/`

Do not treat archived/reference repos as the source of truth for the current runtime unless the active docs explicitly point back to them.

## Architecture Snapshot

Current intended architecture:

- OpenClaw owns reasoning, memory, social identity, and high-level tool selection.
- Robot-side MCP servers own bounded execution and ROS-facing logic.
- ROS 2 Humble + Nav2 is the active robot runtime.
- LiveKit is the current voice transport into OpenClaw.
- tmuxinator is the current development launcher.

Important current behavior:

- OpenClaw is the intended MCP consumer.
- The robot MCP server currently uses a temporary Nav2 readiness bypass:
  - `MORETEA_BYPASS_NAV2_ACTIVE_WAIT=1`
  - actual navigation truth is confirmed at goal time
  - `health` is the first diagnostic check

## Canonical Doc Map

- [README.md](/home/frentzen/FYP/README.md)
  Human developer index for the workspace.
- [PRD.md](/home/frentzen/FYP/PRD.md)
  Canonical product and architecture document.
- [PROGRESS.md](/home/frentzen/FYP/PROGRESS.md)
  Current verified state and recent milestones.
- [TODO.md](/home/frentzen/FYP/TODO.md)
  Active backlog.
- [RUNBOOK.md](/home/frentzen/FYP/RUNBOOK.md)
  Canonical cross-machine launch, verification, and troubleshooting guide.
- [agent-starter-python/README.md](/home/frentzen/FYP/agent-starter-python/README.md)
  Voice/runtime setup and OpenClaw bridge guidance.
- [moretea-robot-mcp/README.md](/home/frentzen/FYP/moretea-robot-mcp/README.md)
  Robot MCP overview and tool surface.
- [ADDING_FEATURES.md](/home/frentzen/FYP/moretea-robot-mcp/docs/ADDING_FEATURES.md)
  Robot-feature extension guide.

## Documentation Rules

When the architecture or launch flow changes:

- update [PRD.md](/home/frentzen/FYP/PRD.md) only if product intent or ownership boundaries changed
- update [PROGRESS.md](/home/frentzen/FYP/PROGRESS.md) when verified behavior or current milestones changed
- update [RUNBOOK.md](/home/frentzen/FYP/RUNBOOK.md) when launch, verification, or troubleshooting changed
- update repo README files only for repo-local concepts and setup
- do not duplicate runbook steps into multiple README files
- do not create new PRD variants; `PRD.md` is canonical

## Known Traps

- There is no canonical `NEW_PRD.md`; use [PRD.md](/home/frentzen/FYP/PRD.md).
- `health` is the first MCP check before blaming OpenClaw, Nav2, or launch order.
- `navigate_to_stop` is a compatibility wrapper; action-style navigation is preferred.
- tmuxinator is for active development convenience, not production process management.
