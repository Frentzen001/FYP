# FYP Progress Report - MoreTea Pet Robot Assistant

**Project:** MoreTea - Garage@EEE Pet Robot Assistant  
**Stack:** LiveKit Agents (Python), ROS 2 Humble, Nav2  
**Last updated:** 22 March 2026 (rev 7)

## Overview
The project has moved from a monolithic voice-tour prototype to a layered robot assistant architecture. This revision adds configurable self-hosted STT, LLM, and TTS support for an RTX 4060 laptop workflow while preserving the existing hosted LiveKit inference path as a fallback. The documented starter stack is now `Ollama` for LLM plus `Speaches` for STT and TTS.

## Architecture In Repo

```text
src/
  main.py
  agent.py
  agent/
    __init__.py
    base_agent.py
    concierge_agent.py
    tour_agent.py
  runtime/
    model_config.py
    session_runtime.py
  domain/
    interaction_domain.py
    safety_domain.py
    tour_domain.py
  services/
    navigation_service.py
    knowledge_service.py
    engagement_service.py
    affect_service.py
    memory_service.py
    telemetry_service.py
  integrations/
    ros2_connector.py
  content/
    robot_persona.yaml
    garage_policies.yaml
    garage_faq.yaml
    tour_stops.yaml
  knowledge.py
  ros2_connector.py
```

Compatibility intentionally preserved:
- `src/agent.py` still works for existing taskfile, Docker, and README commands.
- `import agent` and `from agent import Assistant` still work.
- `import ros2_connector` still works for the older ROS2 test surface.

## Completed In Rev 7

### 1. Configurable local model stack
- Added `runtime/model_config.py` to centralize hosted versus local model configuration.
- Added environment-driven selection of local STT, LLM, and TTS endpoints via `USE_LOCAL_MODELS` and `LOCAL_*` settings.
- Added a hosted fallback switch through `LOCAL_MODEL_FALLBACK_TO_LIVEKIT`.

### 2. Runtime model selection and health probing
- Updated `SessionRuntime` to choose the model stack at startup instead of hard-wiring LiveKit Inference.
- Added local service health probes before session startup for LLM, STT, and TTS.
- Added telemetry events for local model health and final model-stack selection.
- Fixed hosted fallback to use the runtime's configured LiveKit credentials rather than relying on process-level environment state.

### 3. Concrete self-hosted setup guidance
- Documented `Ollama` as the recommended local LLM provider.
- Documented `Speaches` as the recommended OpenAI-compatible STT and TTS server.
- Added step-by-step README instructions for starting services, downloading models, configuring `.env.local`, and verifying health endpoints.

### 4. Test coverage updates
- Added `tests/test_model_config.py`.
- Added coverage for local model default config, startup health checks, hosted fallback, and fallback-disabled failure mode.

## Verification Snapshot
Executed successfully in this pass:
- `uv run python -m compileall src`
- `uv run python -m pytest tests/test_session_runtime.py tests/test_model_config.py -v`

Passing counts from verified local runs:
- 8 runtime and model-config tests passed in this revision

Previously verified and still relevant:
- `uv run python -m pytest tests/test_tour_domain.py tests/test_engagement_service.py tests/test_navigation_service.py tests/test_session_runtime.py tests/test_knowledge_service.py -v`
- `uv run python -m pytest tests/test_ros2_connector.py -v`

Cloud-backed eval status:
- `tests/test_agent.py` remains updated for the current Concierge and Tour flow.
- Full eval execution is still pending a clean rerun in an environment with working model access.

## Current Gaps
- The documented `Ollama + Speaches` stack still needs an end-to-end live validation run on the target laptop.
- Real waypoint coordinates in `src/content/tour_stops.yaml` are still placeholders.
- Physical robot testing with Nav2 is still required.
- Recovery and replan narration still needs tuning on real robot feedback.
- End-to-end latency with the RTX 4060 local stack is not yet benchmarked.
- The current memory layer is session-scoped only, not persistent across sessions.

## Recommended Next Work
- Run the documented `Ollama + Speaches` setup on the RTX 4060 laptop and verify the health endpoints, selected models, and startup telemetry.
- Benchmark local voice latency: first transcript, first token, first audio, and end-to-end turn time.
- Replace placeholder tour-stop coordinates using the actual Garage map.
- Run end-to-end robot tests for start, stop, pause, resume, retry, skip, and degraded behaviour.
- Validate recovery and replan announcements on real robot feedback, then tune wording if needed.
- Rerun `tests/test_agent.py` once the chosen inference path is fully available.
