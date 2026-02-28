# Roadmap

## Strategic Pillars
- **Autonomy Core:** Sensor fusion, self-calibrating SLAM, shared maps, and predictive path planning so the PiCar-X navigates confidently in new environments.
- **Learning Engine:** On-device reinforcement learning with a simulation “dream buffer,” transfer learning across hardware revisions, and policy evaluation loops.
- **Energy & Health:** Complete power telemetry, motor/servo health forecasts, and predictive diagnostics that surface anomalies before they become failures.
- **Safety Guardian:** Redundant stops (wake-word, gestures, watchdog), rehearsed emergency behaviors, and auditable logs for every intervention.
- **Perception Suite:** Lightweight DeepSeek vision heads, rolling 3D reconstruction, anomaly detection, and real-time narration.
- **Interaction Layer:** Conversational UX using local LLMs, gesture/QR triggers, mission editing, and human-friendly state summaries.
- **Tooling & Ops:** Rich diagnostics, simulation-backed CI, fleet knowledge sharing, and resilient operator tooling (tmux, dashboards).
- **Stretch Concepts:** Autonomous docking, adaptive payload detection, choreographed multi-vehicle missions, and expressive status outputs.

## Time Horizons
### Foundation (0–1 Month)
- ✅ Upgrade diagnostics to log predictive signals (battery, sensors, audio health) — `px-diagnostics`, `px-health-report`, `logs/tool-health.log`
- ✅ Extend energy sensing (voltage/temperature) and pipe metrics into `state/session.json`
- ✅ Boot health service: captures throttle/voltage at boot, resets motors — `bin/boot-health`, `picar-boot-health.service`
- ✅ Ship safety fallbacks: wake-word halt, threaded watchdog heartbeats in voice loop
- ✅ Harden logging paths (`LOG_DIR` override, `FileLock` on all writes, isolated test fixtures)
- ✅ Source control: repo at `adrianwedd/picar-x-hacking`, Pi authenticated via SSH key
- ✅ Critical bug fixes: `update_session` deadlock, `tool-voice` dry-mode audio, `voice_loop` JSON parsing
- ⬜ Gesture-driven stop prototype
- ⬜ Weekly battery/health summary reports

### Growth (1–3 Months)
- ⬜ Implement modular sensor fusion and persistent mapping; expose map context to Codex/Ollama tools
- ⬜ Expand interaction layer with richer voice summaries, mission templates, and gesture recognition
- ⬜ Stand up simulation CI sweeps (Gazebo/Isaac or lightweight custom sim) to test planners and RL policies offline
- ⬜ Build predictive maintenance alerts using historical logs
- ⬜ Investigate Robot Hat power-on PWM state — root cause of wheel spinning at boot

### Visionary (3+ Months)
- ⬜ Deploy reinforcement learning “dream buffer” and policy sharing across fleet units
- ⬜ Create autonomous docking workflows, payload auto-detection, and multi-car choreographed demos
- ⬜ Establish a central knowledge base syncing maps/logs, enabling collaborative autonomy
- ⬜ Explore quantised/accelerated model variants to keep on-device AI sustainable

## Current Initiatives
Active execution tracks and their living plans live under `docs/initiatives/`:
- **Diagnostics & Energy Sprint:** Predictive health telemetry and reporting — boot-health service now running.
- **Mapping & Fusion Initiative:** Foundational state estimation and map persistence.
- **Interaction Studio:** Voice/gesture UX powered by local LLMs.
- **Safety Envelope:** Redundant fail-safes and regression simulations — watchdog thread and motor reset on boot now in place.
- **Learning Sandbox Prep:** Simulation pipelines and data capture for RL.

Each initiative doc captures scope, milestones, dependencies, and verification steps. Update them as deliverables land or priorities shift.
