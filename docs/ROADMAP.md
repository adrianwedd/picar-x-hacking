# Roadmap

## Near Term Enhancements
- **Wake-word & VAD front-end:** Gate Codex activation behind a lightweight wake word and voice-activity detector, updating session state with a listening flag.
- **REST / WebSocket bridge:** Expose helper commands and telemetry streaming via authenticated endpoints so remote dashboards can drive and observe safely.
- **tmux session manager:** Provide a wrapper that launches driving, logging, and monitoring panes automatically so sessions can survive SSH disconnects.
- **Enhanced transcript analytics:** Summarise `logs/tool-voice-transcript.log`, surface anomalies (battery low, repeated obstacles), and optionally fan out notifications.
- **Regression testing plan:** Build automated dry-run suites that pulse motion helpers, validate sensor ranges, and compare against golden logs to catch drift.

## Longer Term
- Harden deployment with CI pipelines, packaged releases, and configuration management for multi-car fleets.
- Integrate wake-word pipeline with physical indicators (LED / buzzer) and safety interlocks (dead-man switch, tip detection) before allowing autonomous missions.
- Support mission-oriented natural language plans executed by Codex with explicit confirmation gates and fallback stop conditions.
- Investigate alternative model backends (e.g., Ollama) for offline or cost-optimized operations once ARM builds are available.
