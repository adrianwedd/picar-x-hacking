# Roadmap

## Near Term Enhancements
- **REST bridge:** Expose the helper suite over HTTP for remote control and telemetry streaming, with authentication and rate-limiting baked in.
- **tmux session manager:** Provide a wrapper that launches driving, logging, and monitoring panes automatically so sessions can be resumed after SSH disconnects.
- **OpenAI CLI integration:** Allow natural-language prompts (via `openai api chat.completions.create`) to be translated into helper invocations with explicit confirmation gates.
- **Telemetry streaming:** Feed ultrasonic, grayscale, and camera data into a lightweight MQTT or WebSocket stream for dashboards and alerting.
- **Regression testing plan:** Build automated hardware-in-the-loop scripts that replay motions in dry-run mode, validate sensor ranges, and flag calibration drift.

## Longer Term
- Harden the deployment with CI pipelines, packaged releases, and configuration management for multi-car fleets.
- Add safety interlocks (dead-man switch, tipping detection) before enabling autonomous behaviors.
