# Adding A New Robot Feature

This guide is for new students who want to add hardware capabilities without understanding the whole stack.

The rule is simple:

- add the hardware feature on the robot as an MCP tool
- do not put hardware logic in LiveKit
- do not put ROS logic on the OpenClaw PC

Current control path:

```text
LiveKit -> OpenClaw native MCP client -> robot MCP server -> ROS 2
```

## What Belongs Where

### Robot PC

Owns:

- ROS 2 publishers, subscribers, services, and actions
- hardware-specific topic names and message types
- MCP tool implementations that touch the robot

### OpenClaw PC

Owns:

- reasoning
- memory
- tool selection
- native MCP connection to the robot server

### LiveKit

Owns:

- voice transport only

## Design Rule For New Features

Every new robot feature should follow this pattern:

1. define a clear tool contract
2. implement the ROS-facing code on the robot
3. expose that code as an MCP tool in `server.py`
4. test the tool locally on the robot
5. expose it to OpenClaw through the native MCP client

Examples of good tool contracts:

- `express_emotion(mood: str)`
- `get_navigation_status()`
- `set_head_angle(angle_deg: float)`
- `get_battery_status()`
- `set_arm_pose(pose_name: str)`

Examples of bad tool contracts:

- `do_robot_thing(payload: dict)`
- `raw_ros_command(topic: str, type: str, data: str)`

Make tools intention-based, not ROS-debug-based.

## Current Extension Points

Relevant files:

- [eye_control.py](/home/frentzen/FYP/moretea-robot-mcp/src/moretea_robot_mcp/eye_control.py)
- [navigation_status.py](/home/frentzen/FYP/moretea-robot-mcp/src/moretea_robot_mcp/navigation_status.py)
- [ros_eye_publisher.py](/home/frentzen/FYP/moretea-robot-mcp/src/moretea_robot_mcp/ros_eye_publisher.py)
- [server.py](/home/frentzen/FYP/moretea-robot-mcp/src/moretea_robot_mcp/server.py)
- [tests/test_eye_control.py](/home/frentzen/FYP/moretea-robot-mcp/tests/test_eye_control.py)
- [tests/test_ros_eye_publisher.py](/home/frentzen/FYP/moretea-robot-mcp/tests/test_ros_eye_publisher.py)
- [tests/test_navigation_status.py](/home/frentzen/FYP/moretea-robot-mcp/tests/test_navigation_status.py)

## Recommended Implementation Pattern

Assume you want to add a battery-status feature.

### 1. Create a dedicated robot module

Example file:

```text
src/moretea_robot_mcp/battery_status.py
```

This module should:

- own the ROS topic or service details
- return plain Python data structures
- avoid any MCP-specific code if possible

### 2. Keep ROS lifecycle ownership clear

Follow the same pattern as `ros_eye_publisher.py`:

- initialize ROS once
- own one node or service object
- avoid ad hoc background threads unless needed
- if you must cross threads, acknowledge completion explicitly

### 3. Expose one MCP tool in `server.py`

Register the tool in `server.py` with a small wrapper that calls the robot module.

Keep the MCP layer thin. It should:

- validate input
- call the robot-side implementation
- return a small structured result

It should not:

- contain hardware details
- contain OpenClaw policy
- contain prompt logic

### 4. Add focused tests

At minimum, add:

- contract tests for input validation and output shape
- local tests for the robot-side helper module where possible
- a manual runbook entry in `RUNBOOK.md` if the feature needs operator setup

### 5. Update OpenClaw Through Its Native MCP Client

Once the tool exists in the robot MCP server:

- keep the same SSH tunnel approach
- let OpenClaw discover and call the new tool directly
- avoid writing a new OpenClaw plugin for each robot feature

This is the main maintainability rule.

## Checklist For A New Feature

Before opening a PR, make sure all of these are true:

- the feature works locally on the robot without OpenClaw
- the MCP tool has a clear name and minimal arguments
- the tool returns a structured success or error result
- tests were added for validation and contract shape
- `RUNBOOK.md` was updated if operator steps changed
- OpenClaw can use the tool through its native MCP client

## Naming And Scope Guidance

Prefer small, explicit tool names:

- `express_emotion`
- `get_battery_status`
- `set_head_angle`
- `capture_image`

Avoid giant multi-purpose tools.

If a feature has multiple actions, split them into multiple tools unless they naturally belong together.

## What Not To Do

- do not add ROS topic publishing to the OpenClaw PC
- do not add robot logic to the LiveKit worker
- do not add feature-specific hacks to prompts when a tool is the right abstraction
- do not make students edit three repos for one robot feature if one robot MCP tool is enough

## Student Workflow Summary

For most future work, students should only need to know this:

1. implement robot behavior in `moretea-robot-mcp`
2. expose it as an MCP tool
3. test it locally on the robot
4. let the OpenClaw MCP client surface it to OpenClaw

If that rule stays true, the system will scale much more cleanly than the earlier mixed architecture.
