# MoreTea Engineering Backlog

## High Priority
- [ ] Configure a dedicated `moretea` OpenClaw agent instead of using `main`.
- [ ] Keep delegated OpenClaw mode as the primary production control path.
- [ ] Replace the simulated executor in `moretea-spine/src/moretea_spine/sim/rosclaw.py` with a real ROSClaw Mode B adapter over rosbridge.
- [ ] Stand up rosbridge on the Jetson and verify the RTX desktop can reach it over the same Wi-Fi.
- [ ] Run the first end-to-end delegated smoke test: body turn -> OpenClaw -> ROSClaw -> rosbridge -> robot or simulator.
- [ ] Define the initial `SOUL.md` for the dedicated MoreTea agent.
- [ ] Decide how MoreTea persistent memory should be stored and summarized behind the dedicated OpenClaw agent.

## Medium Priority
- [ ] Connect the new `moretea-spine` body runtime to real LiveKit microphone input instead of transcript-only harness input.
- [ ] Add a real Redis backend implementation alongside the in-memory mirror used by the current tests.
- [ ] Add explicit action-state reconciliation from OpenClaw or ROSClaw back into the body runtime in delegated mode.
- [ ] Add delegated-mode gateway smoke tests that fail clearly when auth, agent routing, or endpoint config is wrong.
- [ ] Enable `/v1/responses` only if you still want real-gateway client-tool simulation or contract testing.
- [ ] Validate barge-in latency with real speech, local TTS, and real ROS action cancellation.
- [ ] Define landmark-to-pose mapping from the real Garage@EEE map for `move_to_landmark(name)`.
- [ ] Validate emotion and arm-pose commands against the actual robot hardware interfaces.

## Lower Priority
- [ ] Add an operator dashboard for robot mode, current action, fallback status, and gateway connectivity.
- [ ] Add richer VLM or sensor snapshot flows once the core voice-action loop is stable.
- [ ] Explore student skill and CI workflows after the ROSClaw transport path is proven on hardware.
- [ ] Revisit whether any functionality from `agent-starter-python` should be migrated into `moretea-spine` after the new control path stabilizes.

## Done Recently
- [x] Created the new `moretea-spine` codebase for the distributed robot spine.
- [x] Cloned the upstream ROSClaw repository into the workspace.
- [x] Added the body runtime with interrupt handling and local fallback mode.
- [x] Added delegated OpenClaw mode so production control stays inside OpenClaw and ROSClaw.
- [x] Kept client-tool mode only as a simulation and contract-testing path.
- [x] Added explicit agent targeting and clearer gateway compatibility errors.
