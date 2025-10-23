# PiCar-X Hacking Helpers

Helper scripts and documentation for experimenting with the SunFounder PiCar-X without touching the stock `~/picar-x` source tree.

## Safety Checklist
- Wheels off the ground on secure blocks before any motion tests.
- Verify an emergency stop option (Ctrl+C in the terminal, `sudo -E bin/tool-stop`, or a physical kill switch) is within reach.
- Confirm `state/session.json` has `confirm_motion_allowed: true` only after a human inspection.
- Run `--dry-run` first to confirm intent and parameters.
- Keep the working area clear of people, pets, and loose cables.

## Environment & Dependencies
1. Activate the project virtual environment:
   ```bash
   source ~/picar-x-hacking/.venv/bin/activate
   ```
2. Install or update Python dependencies as needed (example: OpenAI/Codex CLI tooling):
   ```bash
   PIP_BREAK_SYSTEM_PACKAGES=1 pip install --upgrade openai-codex
   ```
   The `PIP_BREAK_SYSTEM_PACKAGES` warning is expected on Raspberry Pi OS; it simply acknowledges that the venv can access system packages.
3. When running helpers that touch hardware, prefix the command with `sudo -E` so the virtualenv and environment variables persist.

## Helper Usage
All helpers live in `~/picar-x-hacking/bin` and automatically source `px-env`.

- `px-status` – capture a telemetry snapshot:
  ```bash
  sudo -E bin/px-status --dry-run
  sudo -E bin/px-status
  ```
  After the live run, compare the reported voltage and percentage with a multimeter reading to validate the heuristic and note any correction factor for future tuning.
- `px-circle` – gentle clockwise circle in five pulses:
  ```bash
  sudo -E bin/px-circle --dry-run --speed 30
  sudo -E bin/px-circle --speed 35 --duration 6
  ```
- `px-figure8` – two back-to-back circles (right then left):
  ```bash
  sudo -E bin/px-figure8 --dry-run --rest 2
  sudo -E bin/px-figure8 --speed 35 --duration 6 --rest 1.5
  ```
- `px-scan` – camera pan sweep with still captures:
  ```bash
  sudo -E bin/px-scan --dry-run --min-angle -50 --max-angle 50 --step 10
  sudo -E bin/px-scan --min-angle -60 --max-angle 60 --step 10
  ```
- `px-stop` – emergency halt and servo reset:
  ```bash
  sudo -E bin/px-stop
  ```
- `px-wake` – manage the wake-word state for the voice loop:
- `px-frigate-stream` – push an H.264 stream to Frigate/go2rtc (default `pi5-hailo.local`):
  ```bash
  PX_DRY=1 bin/px-frigate-stream --dry-run
  bin/px-frigate-stream --host pi5-hailo.local --stream picar-x
  ```
  Streams via `rpicam-vid` + `ffmpeg` into `rtsp://HOST:PORT/api/stream?push=NAME`. Configure Frigate/go2rtc to pull the same name.
- `px-diagnostics` – run a quick health check (status, optional motion, weather) and announce results:
  ```bash
  PX_DRY=1 bin/px-diagnostics --no-motion --short
  bin/px-diagnostics --no-motion
  ```
  Reports land in `logs/tool-diagnostics.log` and announce through `tool-voice`.
- `px-dance` – choreographed demo (voice intro, circle, figure-eight, finale):
  ```bash
  PX_DRY=1 bin/px-dance --voice "Demo routine"
  bin/px-dance --speed 30 --duration 4
  ```
  Uses existing motion helpers under the hood and logs to `logs/tool-dance.log`.

  ```bash
  bin/px-wake --set on   # enable listening
  bin/px-wake --set off  # disable
  bin/px-wake --pulse 5  # enable for 5 seconds
  ```
  (`px-wake --keyboard` lets you simulate the wake word from the terminal; the loop checks `state/session.json` for `listening: true` before consuming microphone input.)
- `tool-weather` – fetch the latest Bureau of Meteorology observation for the configured station (defaults to Grove AWS while Cygnet feed is offline). The helper automatically falls back from HTTPS to the public FTP catalogue when required and includes a conversational summary for the voice agent:
  ```bash
  PX_DRY=1 bin/tool-weather          # plan only
  PX_DRY=0 bin/tool-weather          # live fetch
  PX_WEATHER_STATION=95977 PX_DRY=0 bin/tool-weather  # override station (e.g., Grove)
  ```
  On success the observation is logged to `logs/tool-weather.log`, cached in `state/session.json` under `last_weather`, and ready for speech output.

Each helper logs actions with ISO timestamps and exits cleanly on Ctrl+C.

## State Files
- Runtime state lives in `state/session.json` (ignored by git). Copy the template before first use:
  ```bash
  cp state/session.template.json state/session.json
  ```
- The supervisor and tool wrappers update this file with battery data, weather snapshots, last motions, and a watchdog heartbeat on every loop turn.

## Codex Voice Assistant
The Codex-driven loop keeps context in `state/session.json`, validates every tool call, and defaults to dry-run for safety.
The loop automatically speaks weather summaries using `espeak` (or another player set via `PX_VOICE_PLAYER`) whenever `tool_weather` succeeds, and each turn captures a prompt/action record in `logs/tool-voice-transcript.log` for auditing. Install an ALSA-compatible TTS engine if you want audible responses.


1. Configure the Codex CLI command (example assumes `codex chat` accepts stdin):
   ```bash
   export CODEX_CHAT_CMD="codex exec --model gpt-5-codex --full-auto --search -"
   ```
2. (Optional) Select an audio player for spoken responses:
   ```bash
   export PX_VOICE_PLAYER="/usr/bin/say"
   ```
3. Use `px-wake` (or any other wake controller) to set `listening: true` before the loop listens on the microphone. The supervisor polls this flag and stays idle until it is raised.
4. Run the loop in dry-run mode first:
   ```bash
   bin/run-voice-loop --dry-run --auto-log
   ```
   `bin/run-voice-loop` sets up `CODEX_CHAT_CMD` automatically (defaults to `codex exec --model gpt-5-codex --full-auto --search -`). Override the variable before launch if you need a different Codex command.
   Type a prompt at `You>` and the supervisor will call the Codex CLI, parse the JSON tool request, and execute the corresponding wrapper in dry-run mode.
5. When moving beyond dry-run, manually flip `confirm_motion_allowed` to `true` in `state/session.json` *after* confirming the car is on blocks. The wrappers will refuse motion otherwise.
6. Use `--exit-on-stop` if you want the loop to terminate after a successful `tool-stop` invocation. Turn-by-turn transcripts live in `logs/tool-voice-transcript.log`; they include the prompt excerpt, Codex action, tool results, and auto-generated speech status.
7. Use `bin/px-session` to launch a tmux workspace with the voice loop, wake controller, and transcript tail in separate panes. Run `bin/px-session --plan` to inspect the layout before attaching.

The system prompt consumed by Codex lives in `docs/prompts/codex-voice-system.md`; adjust it if you add tools or new safety rules.

## Logging Strategy
- Logs live under `~/picar-x-hacking/logs`. Individual helpers use dedicated files such as `px-circle.log`, `px-figure8.log`, and `px-scan.log`.
- Tool wrappers emit JSON lines to `logs/tool-*.log`; the voice supervisor writes to `logs/tool-voice-loop.log` when `--auto-log` is enabled and to `logs/tool-voice-transcript.log` on every turn (prompt excerpt, Codex action, tool payload).
- Generate quick summaries with `bin/px-voice-report --json` to inspect tool counts, voice success rate, and the latest weather narration.
- Camera sweeps store captures in `logs/scans/<timestamp>/` alongside `px-scan.log` entries.
- Keep the directory under version control via `logs/.gitkeep`.
- Tail logs during testing:
  ```bash
  tail -f logs/px-circle.log
  ```

## Next Steps
See `docs/ROADMAP.md` for upcoming automation goals, including REST control surfaces, tmux automation, OpenAI/Codex CLI integration, telemetry streaming, and regression testing infrastructure.
