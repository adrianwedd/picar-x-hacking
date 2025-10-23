# Helper Tools

All helper scripts live in `~/picar-x-hacking/bin`. Each script is designed to be executed with the virtual environment active and supports `sudo -E` so environment variables propagate when run with elevated privileges.

| Script | Purpose |
| --- | --- |
| `px-env` | Prepares the helper environment by exporting `PROJECT_ROOT`, extending `PYTHONPATH` with local overrides and the upstream `~/picar-x` package, activating the project virtualenv, and ensuring the logs directory exists. Source this file from other helpers. |
| `px-circle` | Drives a gentle clockwise circle using five forward pulses with ~20° steering. Supports `--speed`, `--duration`, and `--dry-run` modes while logging to `logs/px-circle.log`. |
| `px-figure8` | Runs two sequential circles (right then left) to trace a figure eight. Shares the same flags as `px-circle` plus an optional `--rest` pause between legs and logs to `logs/px-figure8.log`. |
| `px-scan` | Sweeps the camera pan servo from -60° to +60° (configurable) and captures still images via `rpicam-still`, storing them under `logs/scans/<timestamp>/` with detailed logs in `logs/px-scan.log`. Supports `--dry-run` for planning. |
| `px-status` | Collects a telemetry snapshot: servo offsets and motor calibration (from `/opt/picar-x/picar-x.conf`), live ultrasonic and grayscale readings, an ADC-based battery estimate, and config file metadata. |
| `px-stop` | Emergency stop helper that double-calls `stop()`, centers steering and camera servos, and closes the Picar-X connection. |
| `tool-status` | Wrapper that runs `px-status`, parses the output for battery data, updates `state/session.json`, and appends structured logs. Intended for Codex automation. |
| `tool-circle` | Validates Codex parameters, enforces safety gates (`confirm_motion_allowed`), and runs `px-circle` with sanitized env vars while logging the outcome. |
| `tool-figure8` | Same safety wrapper pattern for `px-figure8`, with clamped duration/rest values before execution. |
| `tool-stop` | Safe halt wrapper that respects dry-run mode and resets the session state after invoking `px-stop`. |
| `tool-voice` | Logs and plays spoken responses; uses the player defined by `PX_VOICE_PLAYER` or falls back to `espeak`/`say` when available. Respects `PX_DRY` for silent rehearsals. |
| `px-wake` | Toggles the voice wake state (set/pulse/keyboard) and writes `listening` flags into `state/session.json` so the voice loop knows when to capture audio. |
| `tool-weather` | Fetches the latest Bureau of Meteorology observation for the configured product/station (default Grove AWS), falling back from HTTPS to FTP when required and producing a conversational summary for Codex/voice playback. Override with `PX_WEATHER_PRODUCT`, `PX_WEATHER_STATION`, or `PX_WEATHER_URL`. |
| `run-voice-loop` | Convenience launcher that exports `CODEX_CHAT_CMD` (default `codex exec --model gpt-5-codex --full-auto --search -`) and executes `codex-voice-loop` with supplied flags. |
| `px-voice-report` | Summarises `logs/tool-voice-transcript.log` (tool counts, voice success/failure, battery warnings) in text or JSON form. |
| `codex-voice-loop` | Supervisor that pipes transcripts through the Codex CLI, parses JSON tool requests, enforces allowlists/ranges, executes wrappers, and records a watchdog heartbeat in `state/session.json`. |

All motion-capable helpers include `--dry-run` (or honour `PX_DRY`) so you can review planned actions before spinning the wheels. Always confirm the car is on blocks prior to running live motion. Use `sudo -E bin/<script>` to ensure the virtualenv and path configuration remain intact under sudo.
