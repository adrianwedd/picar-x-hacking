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
- Upgrade diagnostics to log predictive signals (battery, servo current, audio health) with weekly summaries.
- Extend energy sensing (voltage/current/temperature) and pipe metrics into `state/session.json`.
- Ship safety fallbacks: gesture-driven stop prototype, wake-word emergency halt, watchdog heartbeats.
- Harden logging paths (done: `LOG_DIR` override) and ensure Ollama-based voice loop remains auditable.

### Growth (1–3 Months)
- Implement modular sensor fusion and persistent mapping; expose map context to Codex/Ollama tools.
- Expand interaction layer with richer voice summaries, mission templates, and gesture recognition.
- Stand up simulation CI sweeps (Gazebo/Isaac or lightweight custom sim) to test planners and RL policies offline.
- Build predictive maintenance alerts using historical logs.

### Visionary (3+ Months)
- Deploy reinforcement learning “dream buffer” and policy sharing across fleet units.
- Create autonomous docking workflows, payload auto-detection, and multi-car choreographed demos.
- Establish a central knowledge base syncing maps/logs, enabling collaborative autonomy.
- Explore quantised/accelerated model variants to keep on-device AI sustainable.

## Current Initiatives
Active execution tracks and their living plans live under `docs/initiatives/`:
- **Diagnostics & Energy Sprint:** Predictive health telemetry and reporting.
- **Mapping & Fusion Initiative:** Foundational state estimation and map persistence.
- **Interaction Studio:** Voice/gesture UX powered by local LLMs.
- **Safety Envelope:** Redundant fail-safes and regression simulations.
- **Learning Sandbox Prep:** Simulation pipelines and data capture for RL.

Each initiative doc captures scope, milestones, dependencies, and verification steps. Update them as deliverables land or priorities shift.
