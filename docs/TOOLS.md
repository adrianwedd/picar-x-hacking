# Helper Tools

All helper scripts live in `~/picar-x-hacking/bin`. Each script is designed to be executed with the virtual environment active and supports `sudo -E` so environment variables propagate when run with elevated privileges.

| Script | Purpose |
| --- | --- |
| `px-env` | Prepares the helper environment by exporting `PROJECT_ROOT`, extending `PYTHONPATH` with local overrides and the upstream `~/picar-x` package, activating the project virtualenv, and ensuring the logs directory exists. Source this file from other helpers. |
| `px-circle` | Drives a gentle clockwise circle using five forward pulses with ~20° steering. Supports `--speed`, `--duration`, and `--dry-run` modes while logging to `logs/px-circle.log`. |
| `px-figure8` | Runs two sequential circles (right then left) to trace a figure eight. Shares the same flags as `px-circle` plus an optional `--rest` pause between legs and logs to `logs/px-figure8.log`. |
| `px-scan` | Sweeps the camera pan servo from -60° to +60° (configurable) and captures still images via `rpicam-still`, storing them under `logs/scans/<timestamp>/` with detailed logs in `logs/px-scan.log`. Supports `--dry-run` for planning. |
| `px-status` | Collects a telemetry snapshot: servo offsets and motor calibration (from `/opt/picar-x/picar-x.conf`), live ultrasonic and grayscale readings, an ADC-based battery estimate, and config file metadata. |

All motion-capable helpers include `--dry-run` so you can review planned actions before spinning the wheels. Always confirm the car is on blocks prior to running live motion. Use `sudo -E bin/<script>` to ensure the virtualenv and path configuration remain intact under sudo.
