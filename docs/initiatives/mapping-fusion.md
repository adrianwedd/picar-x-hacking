# Mapping & Fusion Initiative

## Goal
Deliver a reliable internal state estimate that underpins autonomy and collaborative mapping.

## Scope
- Prototype sensor fusion (EKF/particle) combining PiCam odometry, IMU, encoders, and ultrasonic beacons.
- Persist lightweight maps (occupancy grid or sparse landmarks) aligned to `state/maps/<session>.json`.
- Expose map summaries to Codex/Ollama prompts so agents plan with spatial context.
- Provide replay tooling to visualise runs and detect drift.

## Milestones
- [ ] Choose map & fusion representation with constraints (CPU, memory).
- [ ] Implement fusion prototype in `src/pxh/fusion/` with unit tests.
- [ ] Build map persistence helpers + CLI (`bin/map-inspect`).
- [ ] Integrate with voice loop context (map highlights in prompts).

## Dependencies
- Reliable timestamped sensor streams.
- Calibration data for encoders and IMU.

## Verification
- Simulation or dry-track walkthrough comparing predicted vs. actual positions.
- Map replay visual validated by operators.
