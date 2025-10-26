# Interaction Studio

## Goal
Create a natural, local-first operator experience through voice, gestures, and mission editing.

## Scope
- Build richer status summaries from Ollama (mission briefings, anomaly highlights).
- Prototype gesture/QR recognition using PiCam + lightweight models.
- Define conversational mission templates (“patrol room”, “diagnose battery”, etc.).
- Log all interactions to structured transcripts for audit.

## Milestones
- [ ] Extend `tool_voice` summaries + add mission template catalog.
- [ ] Implement gesture recognition pipeline with dry-run stubs.
- [ ] Add conversational prompts + UI toggles for mission editing.
- [ ] Document operator playbooks in `docs/ops/`.

## Dependencies
- Stable perception pipeline (vision models + camera capture).
- Ollama runtime performance targets (tuned defaults).

## Verification
- Demo script (recorded or live) showing multi-modal interaction.
- Tests ensuring mission templates resolve to safe tool sequences.
