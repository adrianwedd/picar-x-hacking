# PiCar-X Hacking Helpers

Helper scripts and documentation for experimenting with the SunFounder PiCar-X without touching the stock `~/picar-x` source tree.

## Safety Checklist
- Wheels off the ground on secure blocks before any motion tests.
- Verify an emergency stop option (Ctrl+C in the terminal or `sudo pkill -f picarx`) is within reach.
- Run `--dry-run` first to confirm intent and parameters.
- Keep the working area clear of people, pets, and loose cables.

## Environment & Dependencies
1. Activate the project virtual environment:
   ```bash
   source ~/picar-x-hacking/.venv/bin/activate
   ```
2. Install or update Python dependencies as needed (example: OpenAI CLI tooling):
   ```bash
   PIP_BREAK_SYSTEM_PACKAGES=1 pip install --upgrade openai
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

Each helper logs actions with ISO timestamps and exits cleanly on Ctrl+C.

## Logging Strategy
- Logs live under `~/picar-x-hacking/logs`. Individual helpers use dedicated files such as `px-circle.log`, `px-figure8.log`, and `px-scan.log`.
- Camera sweeps store captures in `logs/scans/<timestamp>/` alongside `px-scan.log` entries.
- Keep the directory under version control via `logs/.gitkeep`.
- Tail logs during testing:
  ```bash
  tail -f logs/px-circle.log
  ```

## Next Steps
See `docs/ROADMAP.md` for upcoming automation goals, including REST control surfaces, tmux automation, OpenAI CLI integration, telemetry streaming, and regression testing infrastructure.
