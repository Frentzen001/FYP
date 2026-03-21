# MoreTea Engineering Backlog

## High Priority
- [ ] Run the documented `Ollama + Speaches` setup end to end on the RTX 4060 laptop.
- [ ] Verify `LOCAL_LLM_HEALTH_URL` and `LOCAL_STT_HEALTH_URL`/`LOCAL_TTS_HEALTH_URL` pass before startup.
- [ ] Measure RTX 4060 local voice latency for first transcript, first token, first audio, and end-to-end turn time.
- [ ] Validate and replace placeholder coordinates in `agent-starter-python/src/content/tour_stops.yaml` using the real Garage@EEE map.
- [ ] Run physical robot tests for `NavigationService` and `TourDomain` with Nav2 active.
- [ ] Validate recovery and replan announcements on real robot feedback and tune the wording if the signals are noisy.
- [ ] Rerun `agent-starter-python/tests/test_agent.py` successfully using the selected working model path.

## Medium Priority
- [ ] Decide whether the final local STT model should stay on `Systran/faster-distil-whisper-small.en` or move to a larger Whisper variant after latency testing.
- [ ] Tune the TTS voice for the pet robot character after the local service path is stable.
- [ ] Add startup health checks for robot-side readiness beyond import/runtime availability if more hardware signals become available.
- [ ] Extend memory beyond the current session if persistent user context becomes a real product need.
- [ ] Add a manual operator command for clearing degraded state during demos if needed.

## Lower Priority
- [ ] Add an operator dashboard for robot mode, current stop, and health state.
- [ ] Add a REST or API surface after runtime contracts stabilise.
- [ ] Explore richer multi-agent workflows after the current single runtime plus tour handoff is proven on hardware.
- [ ] Explore vision-based person awareness after the voice-first assistant is stable.

## Done In The Latest Pass
- [x] Added environment-driven local versus hosted model stack selection.
- [x] Added local model service health checks before session startup.
- [x] Added hosted fallback for local model startup failures.
- [x] Added `.env.example` entries for local model URLs, model IDs, health checks, and fallback settings.
- [x] Added `tests/test_model_config.py` to cover local model config and fallback behaviour.
- [x] Documented a concrete `Ollama + Speaches` local setup path in the project README.
- [x] Updated README, PRD, progress, and backlog docs to reflect the local self-hosted inference path.
