# Diagnostics & Energy Sprint

## Goal
Predict issues before they bite: richer telemetry, health summaries, and battery intelligence for every run.

## Scope
- Extend `px-diagnostics` to capture voltage, current, temperature, audio checks, and servo/motor metrics.
- Persist weekly health snapshots (`logs/health/`), fold summaries into `state/session.json`.
- Add CLI/report helper to surface degradation trends and schedule maintenance reminders.
- Instrument energy sensing hardware (ADC or INA219) and normalise readings in software.

## Milestones
- [x] Define telemetry schema + state telemetry fields.
- [x] Upgrade `px-diagnostics` to emit predictive metrics (dry-run compatible).
- [x] Build `bin/px-health-report` for weekly summaries.
- [ ] Document hardware calibration + safe operating ranges.

## Dependencies
- Access to battery current sensor (or plan to integrate one).
- Logging storage budget (rotations for new health logs).

## Verification
- Unit/pytest coverage for new helpers.
- Sample logs demonstrating predicted maintenance alerts.
- Manual dry-run showing diagnostics continuing to operate safely.
