# Tool Expansion Brainstorm

## High-Value Additions
1. **px-diagnostics** – run an end-to-end hardware audit (servo motion, motor pulse, ultrasonic ping, grayscale read, camera test), aggregate results into a conversational summary via `tool_voice`. Dry-run mode exercises the reporting without moving hardware.
2. **px-dance** – choreograph a short routine combining circles, figure-eight segments, and timed voice prompts/music for demo mode. Include parameters for speed, duration, and playlist.
3. **px-calibrate** – guided workflow to centre steering, align camera servos, and update `/opt/picar-x/picar-x.conf` offsets with before/after snapshots.
4. **px-battery-watch** – monitor voltage trend; optionally trigger alerts/voice warnings when dropping below thresholds or charging completes.
5. **px-camera-check** – capture stills/pan sweep, run image stats (brightness, colour balance), and flag anomalies (blocked lens, dark scene).
6. **px-path-replay** – record motion sequences (from keyboard or previous run) and replay them with safety gates (dry-run preview included).
7. **px-scan-report** – combine LiDAR/ultrasonic sweeps with transcripts, producing a human-readable obstacle report.
8. **px-voice-log-digest** – pull daily summaries of Codex actions, including successes/failures, battery warnings, and environmental notes (extension of the current report with scheduling support).
9. **px-rest-gateway** – minimal HTTP/WebSocket bridge to expose status, logs, and command execution (with authentication & rate limits).
10. **px-autosafety** – enforce runtime guards: auto-stop on low battery, repeated obstacle detection, or missing heartbeat.

## Immediate Targets
1. **px-diagnostics** (automated health check)
2. **px-dance** (demo routine)
3. **px-battery-watch** (voltage trend & alerts)
4. **px-camera-check** (image quality validation)
5. **px-path-replay** (record & replay motions)
6. **px-rest-gateway** (HTTP/WebSocket bridge)
7. **px-autosafety** (runtime guardrail service)

Each tool will include pytest coverage, entry in `docs/TOOLS.md`, README instructions, and integration with the session state/logging infrastructure.
