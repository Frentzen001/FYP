# MoreTea FYP

MoreTea is a pet robot assistant for Garage@EEE. The project combines LiveKit Agents, ROS 2, and Nav2 to provide Garage QnA, guided tours, wake and sleep interaction, and embodied robot behaviour.

## What This Repo Contains
- `PRD`: product scope, target behaviour, architecture direction, and functional requirements.
- `PROGRESS.md`: current implementation status, completed refactor work, and verification history.
- `TODO.md`: active engineering backlog after the latest software-first milestone.
- `agent-starter-python/`: the working application repo.

## Current Architecture Snapshot
- `agent-starter-python/src/main.py`: primary LiveKit worker entrypoint.
- `agent-starter-python/src/agent.py`: compatibility entrypoint preserved for existing commands.
- `agent-starter-python/src/agent/`: `base_agent.py`, `concierge_agent.py`, `tour_agent.py`.
- `agent-starter-python/src/runtime/`: session orchestration, startup health checks, and dependency wiring.
- `agent-starter-python/src/domain/`: interaction, safety, and tour state machines.
- `agent-starter-python/src/services/`: navigation, knowledge, engagement, affect, memory, and telemetry services.
- `agent-starter-python/src/content/`: YAML content for persona, policies, FAQs, and tour stops.
- `agent-starter-python/src/ros2_connector.py`: ROS 2 and Nav2 connector with compatibility preserved for existing tests.

## Current Status
The repo is past the architectural refactor stage and through the planned software-first milestone.

Implemented now:
- startup health checks and structured startup telemetry
- early degraded stationary-concierge mode when navigation is unavailable
- manual always-awake runtime flag via `MORETEA_ALWAYS_AWAKE`
- session memory capture for explicit user names and high-level interaction preference
- memory-aware instruction assembly and prompt-budget checks
- expanded Garage FAQ content and richer tour-stop narration
- configurable local STT, LLM, and TTS selection with hosted fallback
- documented `Ollama + Speaches` local setup path in `agent-starter-python/README.md`
- updated unit coverage for runtime and prompt behaviour
- updated `tests/test_agent.py` for the Concierge and Tour flow

Still pending:
- real Garage waypoint calibration in `tour_stops.yaml`
- hardware validation of Nav2 outcomes, recovery events, and wake behaviour
- successful rerun of cloud-backed `tests/test_agent.py` once LiveKit model quota is available
- TTS tuning and additional polish on robot character behaviour

## Verification Snapshot
Verified in this pass:
- `uv run python -m compileall src`
- `uv run python -m pytest tests/test_tour_domain.py tests/test_engagement_service.py tests/test_navigation_service.py tests/test_session_runtime.py tests/test_knowledge_service.py -v`
- `uv run python -m pytest tests/test_ros2_connector.py -v`

Updated but not fully verified end-to-end:
- `tests/test_agent.py`
  Current environment hit LiveKit gateway token-credit quota during execution, so the eval file was updated but not fully validated.

For setup, run commands, and developer notes, use `agent-starter-python/README.md`.
