# PRD: MoreTea Modular Companion Robot

## 1. Executive Summary

MoreTea is a socially aware companion robot for the Garage@EEE makerspace. Its job is to greet visitors, answer makerspace questions, guide tours, and safely embody actions in the physical space without turning the voice runtime into a monolith.

The canonical architecture for this phase is:

- OpenClaw as the cognitive core for conversation, long-term memory, policy, and skill selection
- robot-side MCP servers as the modular execution boundary for robot capabilities
- a body runtime for voice, transport, interruption handling, and degraded local operation
- ROS 2 Humble + Nav2 as the active robot runtime on the robot PC

The system must stay modular enough that future contributors can add new robot skills by extending MCP servers with bounded tools, instead of patching ad hoc logic into the voice worker or duplicating control logic across machines.

## 2. Problem, Audience, And Product Goals

### Problem

Garage@EEE relies on repeated human onboarding for tours, wayfinding, and common operational questions. That does not scale well during busy periods and creates repetitive work for committee members.

### Audience

- first-time visitors
- students exploring the space
- members asking routine questions
- future student contributors extending the robot

### Product Goals

MoreTea should:

- answer common Garage@EEE questions without obvious hallucinations
- guide users through a multi-stop tour with resumable progress
- stay unobtrusive when not being engaged, then respond naturally when addressed
- explain failures, pauses, reroutes, and degraded operation clearly
- remain useful as a stationary concierge when movement is unavailable
- remember durable social context on the OpenClaw side
- remain understandable and extensible for future contributors

### Success Metrics

- MoreTea can answer common Garage@EEE questions with reliable prompt-grounded content.
- MoreTea can complete a configured tour using stable stop IDs and recover from navigation failure with clear user-facing explanation.
- MoreTea can degrade into a non-moving concierge when Nav2, ROS, or movement tools are unavailable.
- MoreTea can expose robot capabilities through stable MCP-facing contracts rather than one-off voice-worker logic.
- A future contributor can add a new robot capability by extending MCP servers and tests without restructuring the whole system.

## 3. System Architecture

### 3.1 Layered Model

The system is organized into four layers:

- product layer: MoreTea as a companion, concierge, and tour guide for Garage@EEE
- control layer: OpenClaw agent, memory, policy, and high-level orchestration
- skill layer: robot-side MCP servers exposing bounded robot capabilities
- embodiment layer: ROS 2 Humble, Nav2, sensors, drivers, and device-specific runtime

This layered model is the primary modularity rule for the project.

### 3.2 Control Ownership

OpenClaw is the owner of:

- conversation
- long-term memory
- social identity and persona
- tour policy and sequencing
- skill selection and high-level reasoning

Robot-side MCP servers are the owner of:

- robot execution surfaces
- ROS-facing capability wrappers
- bounded navigation, expression, perception, and future manipulation tools
- structured, JSON-safe capability contracts

The body runtime is the owner of:

- microphone and speaker transport
- local interruption and barge-in handling
- local degraded emergency operation
- ephemeral runtime state mirroring

The body runtime must not be the production owner of the robot tool graph.

### 3.3 Deployment Topology

Current active topology:

- OpenClaw PC
  - dedicated `moretea` OpenClaw agent
  - native MCP client
  - persistent memory and higher-level reasoning
- robot PC
  - robot-side MCP servers
  - ROS 2 Humble
  - Nav2 and hardware integration
- body runtime
  - LiveKit or equivalent voice/runtime transport into OpenClaw

In the current implementation phase, the robot PC exposes MCP endpoints on a trusted LAN or tunneled path. OpenClaw consumes these MCP tools directly.

### 3.4 Current Implementation Versus Target Architecture

Current implementation milestone:

- OpenClaw is already the intended MCP consumer.
- The robot PC exposes stable MCP tools such as:
  - `express_emotion(mood)`
  - `list_tour_stops()`
  - `navigate_to_stop(stop_id)`
  - `cancel_navigation()`
  - `get_navigation_status()`
- ROS 2 Humble is the active supported runtime.

Target long-term architecture:

- OpenClaw remains the owner of full tour sequencing, narration, retries, interruption recovery, and memory-aware personalization.
- Robot-side MCP servers remain bounded execution surfaces and do not become the owner of long-term identity or durable social memory.
- Additional robot capabilities such as perception or manipulation should follow the same MCP extension model.

The PRD must distinguish these two so contributors do not confuse the current milestone with final system ownership.

## 4. Functional Requirements

### FR-1: Garage Concierge QnA

MoreTea must answer common Garage@EEE questions about facilities, policies, programmes, and locations using grounded content and explicit prompt or memory context.

### FR-2: Tour Guiding

MoreTea must support multi-stop tours using stable stop identifiers and configurable stop content.

Requirements:

- stop content must be defined in structured source files
- tour stop IDs must be stable across systems
- the robot must be able to move to individual stops through MCP tools
- OpenClaw must remain capable of owning overall tour policy, narration, retry, and interruption behavior

### FR-3: Wake, Attention, And Idle Behavior

MoreTea must remain unobtrusive when not engaged, respond when addressed, and return to an idle/passive state after inactivity.

This behavior may evolve beyond strict wakeword gating, but it must remain deterministic and understandable to future developers.

### FR-4: Embodied Behavior

MoreTea should express simple social behavior through bounded robot actions such as eye expressions and future physical gestures.

### FR-5: Failure Transparency

MoreTea must inform users when the robot:

- cannot move
- is rerouting or paused
- skips or cancels a stop
- has entered degraded mode

### FR-6: Degraded Concierge Mode

If movement or higher-level robot control is unavailable, MoreTea must remain useful as a stationary concierge.

### FR-7: Startup Health Reporting

The system must expose structured health reporting so operators and coding agents can tell whether voice, robot capabilities, navigation, and content are ready.

### FR-8: Personalization And Durable Memory

Long-term user facts, preferences, and identity continuity belong on the OpenClaw side. Robot-side services may expose ephemeral operational state but must not become the source of truth for durable memory.

### FR-9: Configurable Runtime Stack

The system should support a practical self-hosted and hosted mix for STT, LLM, and TTS, but model-stack choice is a configuration concern rather than the core architectural boundary.

### FR-10: Easy Skill Extension

Future contributors must be able to add new robot skills without modifying core conversation orchestration.

The preferred extension path is:

- add or extend MCP server capabilities
- define stable tool contracts
- add simulation-safe tests
- then expose the new capability to OpenClaw

## 5. MCP Extension Model

MCP is the primary modular extension surface for robot skills in this phase.

### 5.1 Rules For New Skills

Every new robot-facing skill should:

- be exposed through a bounded MCP tool or MCP skill surface
- return structured, JSON-safe responses
- have explicit success and failure payloads
- be auditable and simulation-testable before hardware rollout
- keep ROS and device-specific logic on the robot side

Examples of capability concepts:

- `express_emotion(mood)`
- `list_tour_stops()`
- `navigate_to_stop(stop_id)`
- `cancel_navigation()`
- `get_navigation_status()`
- future perception tools
- future arm or manipulation tools

### 5.2 Ownership Boundaries

OpenClaw consumes MCP capabilities.

MCP servers do not own:

- long-term memory
- durable identity
- overall tour narrative policy
- free-form social reasoning

MCP servers do own:

- bounded action execution
- capability-specific validation
- structured operational status
- ROS-facing and hardware-facing logic

### 5.3 Source Of Truth

The source of truth for robot capability contracts should live with the robot-side MCP repo and its documentation.

The source of truth for high-level agent behavior, persona, and memory policy should live with the OpenClaw-side configuration and supporting docs.

## 6. Security And Trust Model

- OpenClaw control endpoints must remain on a trusted LAN or private subnet only.
- Robot-side MCP endpoints are private robot-control surfaces and must not be exposed publicly.
- Non-loopback control surfaces must use authentication or a protected transport boundary.
- Dangerous robot actions must remain bounded by deterministic safety checks independent of LLM output.
- Body-to-brain and brain-to-robot control traffic must use explicit structured protocols such as MCP, Redis, gRPC, ROS-compatible transport, or similarly auditable interfaces.
- Simulation-only client-side tool execution must not be mistaken for the production control path.

## 7. Technical Constraints And Assumptions

- Active robot runtime for this phase: ROS 2 Humble + Nav2
- Active robot execution boundary: robot-side MCP servers
- Intended OpenClaw integration path: native MCP client
- Knowledge can remain prompt-grounded and content-driven where practical, especially for small Garage@EEE datasets
- RESpeaker-class microphones may be treated as standard audio devices; wake and attention behavior is a software/runtime concern
- Local self-hosted inference remains desirable for cost and latency control, but it is a secondary concern relative to clean skill boundaries and safe robot control

## 8. Milestones

### Milestone 1: Stable Connectivity And Control Split

Goal: prove the OpenClaw-to-robot MCP control boundary on the trusted network.

Validation:

- OpenClaw can consume the robot MCP endpoint
- tool calls can reach the robot PC reliably
- control ownership is not duplicated in the voice worker

### Milestone 2: Stable Robot Capability Surface

Goal: stabilize the current MCP tool contract for expression, navigation status, and single-stop navigation.

Validation:

- `health`, `express_emotion`, `list_tour_stops`, `navigate_to_stop`, `cancel_navigation`, and `get_navigation_status` work with structured outputs
- degraded startup and missing-dependency cases are explicit

### Milestone 3: Full Tour Orchestration On Top Of MCP

Goal: let OpenClaw own full guided-tour behavior while relying on robot MCP primitives for execution.

Validation:

- OpenClaw can run a multi-stop tour using stable stop IDs
- tour narration and retry logic remain outside the robot execution layer
- movement failures and reroutes are explained clearly

### Milestone 4: Durable Identity And Memory

Goal: make MoreTea socially consistent across sessions.

Validation:

- MoreTea remembers user names or preferences across sessions
- robot-side state remains operational and ephemeral

### Milestone 5: Student Skill Sandbox

Goal: allow safe future extension by students and maintainers.

Validation:

- contributors can add a new bounded robot skill through MCP with tests and docs
- unsafe or under-tested capabilities are blocked from direct production rollout

## 9. Immediate Next Steps

- keep `NEW_PRD.md` as the canonical product and architecture source of truth
- treat the legacy `PRD` file as archived and redirect readers here
- continue stabilizing OpenClaw consumption of the existing robot MCP tools
- keep tour stop content and stop IDs structured and shared across systems
- document new robot skills in the MCP repo as they are added
