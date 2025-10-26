# Safety Envelope

## Goal
Guarantee every autonomous action is reversible, observable, and fails safe.

## Scope
- Implement redundant halts: wake-word stop, gesture stop, hardware watchdog tied to Codex loop heartbeat.
- Record intervention logs with timestamps and context (what triggered, what stopped).
- Build regression scenarios (simulation/dry-run) that inject faults and confirm stop path works.
- Layer physical indicators (LED/audio) reflecting robot state.

## Milestones
- [ ] Wake-word + gesture stop prototypes integrated with `tool-stop`.
- [ ] Watchdog service monitoring voice loop and motion helpers.
- [ ] Regression test suite (`tests/test_safety.py`) covering triggered stops.
- [ ] LED/audio state feedback mapping documented.

## Dependencies
- Microphone/wake-word reliability under lab noise.
- GPIO control for indicators.

## Verification
- Demonstrated stops in rehearsal and documented logs.
- CI/pytest automation simulating heartbeat loss.
