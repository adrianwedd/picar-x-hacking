# Live Dashboard — Design Spec
**Date:** 2026-03-13
**Project:** spark (picar-x-hacking)
**Status:** Draft

---

## Overview

Expand the public dashboard at `spark.wedd.au` from a 4-card stat grid into a rich, layered live display that communicates two things simultaneously: "this robot is alive right now" (ambient/emotional layer) and "look how much is going on under the hood" (technical layer). The technical layer is hidden by default behind a toggle, preserving the warm first impression for non-technical visitors.

---

## Goals

- Surface SPARK's inner state (mood, presence, thought) as the dominant visual signal
- Add environmental context (ambient sound, weather, time) as a secondary layer
- Expose system metrics with sparkline history as an opt-in technical layer
- Build 30-minute rolling history via backend ring buffer + localStorage accumulation
- Stay within existing constraints: vanilla JS, no CDN, strict CSP, dual warm/dark theme

---

## Architecture

### New Backend Additions

**`GET /api/v1/public/awareness`** — unauthenticated, CORS-enabled. Reads `state/awareness.json` directly and returns a subset safe for public exposure:

```json
{
  "obi_mode": "calm",
  "person_present": true,
  "frigate_score": 0.74,
  "ambient_level": "quiet",
  "ambient_rms": 340,
  "weather": { "temp_c": 14.2, "wind_kmh": 12, "humidity_pct": 68, "summary": "Cloudy" },
  "minutes_since_speech": 4,
  "time_period": "night",
  "ts": "2026-03-13T..."
}
```

**`GET /api/v1/public/history`** — unauthenticated, CORS-enabled. Returns a JSON array of up to 60 readings from an in-memory ring buffer (`collections.deque`, maxlen=60). A background thread appends one reading every 30s:

```json
[
  { "ts": "...", "cpu_pct": 23.4, "cpu_temp_c": 52.1, "ram_pct": 41.2,
    "battery_pct": 87, "sonar_cm": 45.2, "ambient_rms": 340 },
  ...
]
```

Ring buffer is lost on restart (acceptable — localStorage fills the gap immediately). No persistence needed.

**`GET /api/v1/services`** — promoted from auth-required to public. Returns service health dict `{service_name: status}` for `px-mind`, `px-alive`, `px-wake-listen`, `px-battery-poll`, `px-api-server`. Read-only, no credentials exposed.

### Frontend Structure

Three new files replace/extend the current `live.js`:

| File | Responsibility |
|------|---------------|
| `site/live.js` | Polling orchestrator — parallel fetches, state merge, drives renders |
| `site/charts.js` | All canvas drawing — sparklines, sonar arc, waveform bars, gauges |
| `site/dashboard.js` | DOM update functions — binds data to elements, manages toggle state |

`live.js` polls four endpoints in parallel every 30s with a 5s timeout each:
- `/api/v1/public/status`
- `/api/v1/public/vitals`
- `/api/v1/public/awareness`
- `/api/v1/public/sonar` (or sonar absorbed into awareness)
- `/api/v1/services`

Results merge into a single `state` object. Each endpoint failure degrades independently — awareness offline doesn't blank vitals. Accumulated readings appended to `localStorage` on every successful vitals+sonar poll.

---

## Section 1: PRESENCE Band

Always visible. The dominant "alive" signal.

**Three-column layout** (stacks vertically on mobile):

### Mood Pulse (left)
- Large filled circle (~120px diameter) in current theme accent colour
- Slow CSS `scale` pulse animation; speed maps to arousal from `mood` field:
  - peaceful/content → 4s cycle
  - curious/contemplative → 2.5s cycle
  - excited/active → 1.5s cycle
- Mood word in large type inside the circle
- Below: `obi_mode` as a human-readable line:
  - `absent` → "Obi's probably asleep"
  - `calm` → "Obi seems nearby"
  - `active` → "Obi is around"
  - `possibly-overloaded` → "Things seem busy"
  - `unknown` → omitted

### Last Thought (centre)
- Existing pull-quote, larger, more vertical breathing room
- Below the quote: mood word + salience as filled dots (●●●○○, 5-dot scale) + "X min ago"
- Salience dots encode importance visually without needing to explain the concept

### Proximity (right)
- 180° SVG fan arc, top-down view, fills from centre outward by distance:
  - < 40cm → full fan, warm accent colour
  - 40–100cm → partial fill, neutral
  - > 150cm → thin sliver, cool/muted colour
  - Unavailable → empty arc outline only
- Below arc: Frigate indicator — person icon (filled = detected, hollow = not) + confidence % when detected. Hidden entirely if Frigate is offline/unavailable.

---

## Section 2: WORLD Band

Always visible. Sits below PRESENCE on a subtly differentiated background.

### Ambient Sound (left ~40%)
- Row of ~40 thin vertical canvas bars spanning the column width
- Animated every 2s independently of API poll
- Bar heights generated from current `ambient_rms` value as an organic distribution (seeded random, not real audio samples) — loud RMS → tall jagged bars, silent → nearly flat gentle drift
- `ambient_level` label to the left: "silent / quiet / moderate / loud"

### Weather Strip (centre ~35%)
- Single horizontal line: temperature + Unicode weather symbol (☀ ☁ 🌧 ❄) + wind + humidity + one-word summary
- Hidden entirely if weather data is unavailable (not broken-state placeholder)

### Time Context (right ~25%)
- Current AEDT time
- `time_period` as a soft badge: "morning" / "afternoon" / "evening" / "night"
- "Last spoke X min ago" (from `minutes_since_speech`) — human-readable, not a raw number. Shows "hasn't spoken recently" if > 30 min.

---

## Section 3: MACHINE Band

Hidden by default. Revealed by "show internals ↓" toggle. CSS `max-height` transition on expand/collapse. Toggle state persisted in `localStorage`.

**3×2 grid of metric tiles:**

| Tile | Visual | Sparkline |
|------|--------|-----------|
| CPU % | Horizontal bar + value | Click → 30-point sparkline |
| CPU temp | Radial gauge arc (SVG, 0–85°C); green → amber at 65° → red at 75° | None needed |
| RAM % | Horizontal bar + value | Click → 30-point sparkline |
| Disk % | Horizontal bar + value; colour-shifts at 80%/90% | None (changes too slowly) |
| Battery | Horizontal bar + voltage in small text; ⚡ when charging | Click → 30-point sparkline |
| Services | Row of named status dots (green/amber/red) for each systemd service | None |

**Inline sparkline behaviour:**
- Clicking an eligible tile appends a `<canvas>` directly below it
- Fetches `/public/history`, merges with localStorage history (deduped + sorted by ts), draws 30-point time series
- "last 30 min" label + min/max range shown below chart
- Clicking again collapses. Only one sparkline open at a time.

Toggle label flips to "hide internals ↑" when expanded.

---

## Data Flow

```
Every 30s:
  parallel fetch → /status, /vitals, /awareness, /services  (5s timeout each)
  merge → state object
  append vitals+sonar to localStorage ring (keep last 120 entries)
  render all three bands

Every 2s (independent):
  regenerate waveform bars from last known ambient_rms

On sparkline open:
  fetch /public/history → merge with localStorage → dedupe → sort → draw canvas

On page load:
  read localStorage → hydrate state immediately (zero-flash)
  then first poll fires
```

---

## Error Handling & Offline

- Each endpoint degrades independently — awareness offline doesn't blank vitals band
- PRESENCE band in offline state: hollow (unfilled) pulse circle, greyed thought text, no obi_mode line
- WORLD band collapses silently if awareness unavailable
- MACHINE band shows last known values with "X min ago" timestamp
- Existing "last updated" banner extended to show per-section staleness
- History endpoint failure → sparkline falls back to localStorage-only data; if localStorage also empty, tile shows "no history yet"

---

## Waveform Honesty Note

The ambient sound waveform is **not** a real audio waveform — we only have an RMS scalar, not audio samples. The animation generates a plausible organic shape seeded from the RMS value. This is clearly aesthetic, not misleading: we're showing "it's loud/quiet" in a visual way, not claiming to display actual microphone data. No label needed; the `level` text is the authoritative reading.

---

## Files Changed

| File | Change |
|------|--------|
| `src/pxh/api.py` | Add `/public/awareness`, `/public/history` endpoints; make `/services` public; add history background thread |
| `site/live.js` | Rewrite — add new endpoint polling, localStorage accumulation |
| `site/charts.js` | New — canvas drawing: sparklines, sonar arc SVG, waveform bars, gauge arc |
| `site/dashboard.js` | New — DOM update functions, toggle state management |
| `site/index.html` | Replace `#status` section with three-band layout |

---

## Testing

- Backend: pytest — `/public/awareness` returns correct subset of awareness.json; `/public/history` returns array; ring buffer maxlen enforced; `/services` accessible without auth
- Frontend: manual — verify each band renders correctly with live data; verify offline degradation per band; verify sparkline open/close; verify localStorage persistence across page reload; verify dark/warm theme both render correctly
- CSP: verify no inline styles introduced (all dynamic colour via CSS class swaps)
