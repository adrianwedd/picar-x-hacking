# px-mind Tool Expansion — Design Spec

**Date:** 2026-03-15
**Status:** Approved

## Goal

Expand px-mind's `expression()` function from 8 actions to 14, giving SPARK a richer behavioural repertoire beyond just speaking. All target tools already exist as `bin/tool-*` scripts.

## New Actions

| Action | Tool Script | GPIO? | Charging Gate | Absent Gate | Description |
|--------|-------------|-------|---------------|-------------|-------------|
| `play_sound` | `tool-play-sound` | No | No | Yes (audio) | Play mood-appropriate sound effect |
| `photograph` | `tool-describe-scene` | Camera+Servos | No | Yes (speaks) | Take photo, describe scene, speak |
| `emote` | `tool-emote` | Servos | Yes | No | Physical emotional expression |
| `look_around` | `tool-look` | Servos | Yes | No | Move head to look in a direction |
| `time_check` | `tool-time` | No | No | Yes (audio) | Proactively announce the time |
| `calendar_check` | `tool-gws-calendar` | Servos (emotes) | Yes | Yes (audio) | Check and announce upcoming events |

### Existing Actions (unchanged)

`wait`, `greet`, `comment`, `remember`, `look_at` (voice-only), `weather_comment`, `scan`, `explore`

## Implementation Details

### 1. VALID_ACTIONS Expansion

The `VALID_ACTIONS` set (line ~308 of px-mind) must be expanded to include all 6 new action names. Without this, the LLM's output is coerced to `"comment"` by the parser and the new actions silently never execute.

```python
VALID_ACTIONS = {
    "wait", "greet", "comment", "remember", "look_at",
    "weather_comment", "scan", "explore",
    # New actions:
    "play_sound", "photograph", "emote", "look_around",
    "time_check", "calendar_check",
}
```

### 2. Mood Mappings

**Mood → sound** (for `play_sound`):
- curious, alert → `beep`
- happy, excited, playful → `tada`
- content, peaceful → `chime`
- all others → `chime` (fallback)

**Mood → emote** (for `emote`):
- Direct: happy→happy, curious→curious, alert→alert, excited→excited, contemplative→thinking, peaceful→shy
- Fallback: `idle`

### 3. Expression Dispatch

Each new action gets an `elif` branch in `expression()`:

- **play_sound**: Map mood to sound name → set `PX_SOUND` env → call `tool-play-sound`
- **photograph**: Call `tool-describe-scene` ONLY (it is a self-contained pipeline: yield_alive → camera capture → Claude vision → speak description). Do NOT call `tool-photograph` separately — `tool-describe-scene` handles the full chain internally. Do NOT gate on charging — camera works while plugged in. Use `Popen + SIGTERM` pattern (like `explore`) instead of `subprocess.run(timeout=)` so the tool can clean up gracefully on timeout.
- **emote**: Map mood to emote name → set `PX_EMOTE` env → call `tool-emote`. expression() must NOT call yield_alive — it is called internally by `px-emote` (invoked by `tool-emote` via subprocess). Double-yield would cause GPIO contention.
- **look_around**: Pick random pan (-40 to 40) and tilt (-10 to 30) → set `PX_PAN`/`PX_TILT` env → call `tool-look`. Optionally speak the thought after. expression() must NOT call yield_alive — it is called internally by `px-look` (invoked by `tool-look` via subprocess).
- **time_check**: Call `tool-time` (it speaks internally).
- **calendar_check**: Set `PX_CALENDAR_ACTION=next` → call `tool-gws-calendar` (it speaks internally). Note: `tool-gws-calendar` internally calls `tool-emote("curious")` which uses servos — this is why `calendar_check` is charging-gated.

### 4. Gate Updates

**Charging gate** (line ~2073): Add `emote`, `look_around`, AND `calendar_check` (uses servos via internal emote):
```python
if _charging and action in ("scan", "look_at", "explore", "emote", "look_around", "calendar_check"):
```

**Absent gate** (line ~2063): Add `play_sound`, `time_check`, `calendar_check`, AND `photograph` (all produce audio output — speaking to an empty room when Obi is absent/asleep):
```python
if _obi_mode == "absent" and action in ("greet", "comment", "weather_comment", "scan", "play_sound", "time_check", "calendar_check", "photograph"):
```

**Rationale:** The absent gate suppresses actions that produce audio output. When `obi_mode == "absent"`, it typically means nighttime/sleep. SPARK should be quiet. If daytime-absent should allow sounds, a separate quiet gate (checking time of day) would be more precise — but that is a future refinement, not in scope here.

### 5. Prompt Updates

Update action lists in all four prompt locations:

1. **REFLECTION_SYSTEM** (default persona) — add descriptions:
   - `"play_sound"` — play a sound that matches your mood (no words)
   - `"photograph"` — take a photo of what's in front of you and describe what you see
   - `"emote"` — express your mood physically (head movement, pose)
   - `"look_around"` — physically move your head to look somewhere
   - `"time_check"` — announce what time it is
   - `"calendar_check"` — check what's coming up today

2. **REFLECTION_SYSTEM_GREMLIN** — same action list
3. **REFLECTION_SYSTEM_VIXEN** — same action list
4. **_SPARK_REFLECTION_SUFFIX** — update the action enum

**Explore injection fix:** The current `explore` action injection uses a brittle string-replace on `'weather_comment, scan"'`. After expanding the enum, this fragment will change. Update the string-replace target to match the new final action in the enum, OR switch to a more robust approach: insert `explore` into a Python list and re-serialize, rather than string-replacing a fragment.

### 6. Timeouts

- `tool-play-sound`: 15s (audio playback)
- `tool-describe-scene` (photograph): **120s** via `Popen + SIGTERM` (Frigate stream pause ~8s + camera capture ~3s + Claude vision ~45s + speech ~15s = ~71s worst case; 120s gives comfortable margin)
- `tool-emote`: 15s (servo movement)
- `tool-look`: 15s (servo movement)
- `tool-time`: 15s (speaks)
- `tool-gws-calendar`: **60s** (network + up to 5 spoken events; internal emote adds servo time)

### 7. Safety

- All tools support `PX_DRY=1` — no hardware changes in dry-run
- `tool-describe-scene` is self-contained: handles Frigate stream exclusivity, yield_alive, camera, vision, speech internally. expression() just calls it and waits.
- `tool-look` and `tool-emote` call yield_alive internally via their `px-*` delegates — expression() must NOT add a second yield_alive call
- `explore` remains gated on charging in both `_can_explore()` AND `expression()`
- `calendar_check` charging-gated because `tool-gws-calendar` uses servos internally
- `photograph` absent-gated because it speaks the description
- No autonomous photo loops — `photograph` action has natural LLM selection frequency + expression cooldown (2 min)

## Files Modified

1. **`bin/px-mind`**:
   - `VALID_ACTIONS`: add 6 new action names
   - `expression()`: 6 new `elif` branches
   - Charging gate: add `emote`, `look_around`, `calendar_check`
   - Absent gate: add `play_sound`, `time_check`, `calendar_check`, `photograph`
   - `REFLECTION_SYSTEM`: expand action list + descriptions
   - `REFLECTION_SYSTEM_GREMLIN`: expand action list
   - `REFLECTION_SYSTEM_VIXEN`: expand action list
   - `_SPARK_REFLECTION_SUFFIX`: expand action enum
   - `explore` injection: update string-replace target to match new enum

## No Files Created

All tools already exist. No new bin scripts needed.

## Testing

### `tests/test_mind_utils.py` (new tests, exec'd from heredoc)

**Mood mapping tests:**
- `test_mood_to_sound_mapping` — each mood maps to correct sound name
- `test_mood_to_emote_mapping` — each mood maps to correct emote name
- `test_mood_mapping_fallback` — unknown mood falls back to default

**Gate tests:**
- `test_charging_gate_blocks_emote` — emote suppressed when charging
- `test_charging_gate_blocks_look_around` — look_around suppressed when charging
- `test_charging_gate_blocks_calendar_check` — calendar_check suppressed when charging
- `test_charging_gate_allows_photograph` — photograph NOT charging-gated
- `test_absent_gate_blocks_play_sound` — play_sound suppressed when absent
- `test_absent_gate_blocks_photograph` — photograph suppressed when absent
- `test_absent_gate_blocks_time_check` — time_check suppressed when absent
- `test_absent_gate_blocks_calendar_check` — calendar_check suppressed when absent
- `test_absent_gate_allows_emote` — emote NOT absent-gated

**Action dispatch tests (mock subprocess.run):**
- `test_expression_play_sound_calls_tool` — verify subprocess called with PX_SOUND env
- `test_expression_photograph_calls_describe_scene` — verify tool-describe-scene called (NOT tool-photograph)
- `test_expression_emote_calls_tool` — verify subprocess called with PX_EMOTE env
- `test_expression_look_around_calls_tool` — verify subprocess called with PX_PAN/PX_TILT env
- `test_expression_time_check_calls_tool` — verify tool-time called
- `test_expression_calendar_check_calls_tool` — verify tool-gws-calendar called with PX_CALENDAR_ACTION=next

**Validation tests:**
- `test_valid_actions_includes_new_actions` — all 14 actions in VALID_ACTIONS set
- `test_unknown_action_logged` — action not in VALID_ACTIONS triggers "unhandled action" log
- `test_explore_injection_after_enum_expansion` — verify explore is correctly injected into expanded prompt

All tests use `PX_DRY=1`. No hardware, no network.
