# Learning Sandbox Prep

## Goal
Lay the groundwork for reinforcement learning and collaborative policy updates.

## Scope
- Stand up a lightweight simulation environment (Gazebo/Isaac or custom) matching PiCar-X constraints.
- Capture datasets (sensor + action logs) for offline training.
- Implement policy evaluation harness with safety gates before live deployment.
- Share policies and maps through a fleet knowledge hub.

## Milestones
- [ ] Select simulation stack + containerise for CI.
- [ ] Export driving datasets (with privacy/safety notes).
- [ ] Build evaluation script comparing policy output vs. safety heuristics.
- [ ] Prototype fleet sync tooling (git-lfs, rsync, or API).

## Dependencies
- Storage for datasets & models.
- Coordination with hardware team for safe deployment cadence.

## Verification
- CI job running sim smoke test.
- Example policy evaluated + gated prior to live run.
