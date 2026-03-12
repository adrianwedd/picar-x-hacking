# GitHub Pages Site — Design Spec
**Date:** 2026-03-12
**Project:** spark (picar-x-hacking)
**Status:** Draft

---

## Overview

A public-facing website for the SPARK / PiCar-X project hosted on GitHub Pages at `spark.wedd.au`. The site combines a project showcase, a live status dashboard, kid-friendly explainer content, and developer documentation. Live data is fetched from the Pi's REST API exposed via a Cloudflare Tunnel at `api.spark.wedd.au`.

---

## Goals

- Showcase the project to four audiences: makers/developers, potential clients, children (specifically Obi), and non-technical visitors
- Display SPARK's live mood, last thought, and system vitals in real time
- Render existing documentation (FAQ, how-brain-works, tools, roadmap) without duplication
- Degrade gracefully to cached "last known state" when the Pi is offline

---

## Infrastructure

### DNS

| Domain | Target | Method |
|---|---|---|
| `spark.wedd.au` | GitHub Pages | `site/CNAME` file + DNS A records → GitHub Pages IPs (185.199.108–111.153) |
| `api.spark.wedd.au` | Pi `localhost:8420` | Cloudflare Tunnel (CNAME → tunnel UUID, managed by cloudflared) |

**GH Pages HTTPS:** After adding the custom domain in repo Settings → Pages, "Enforce HTTPS" must be enabled. The site makes `fetch()` calls to `api.spark.wedd.au` (HTTPS); if the site ever loads over HTTP, mixed-content policy will block the calls.

### Cloudflare Tunnel

- `cloudflared` installed on the Pi (Debian package)
- Token stored in `.env` as `CF_TUNNEL_TOKEN` (gitignored)
- Run via token: `cloudflared tunnel run --token $CF_TUNNEL_TOKEN` — no local credentials file needed
- Systemd service: `cloudflared.service` (Restart=always), reads token from EnvironmentFile=`.env`
- Ingress: `api.spark.wedd.au` → `http://localhost:8420`
- DNS CNAME managed automatically by Cloudflare via the tunnel

### Static Site Hosting

- Served from `master` branch, `/site/` directory
- GH Pages configured: Source = `master`, folder = `/site`
- `site/CNAME` file contains `spark.wedd.au`
- No build step — plain HTML/CSS/JS committed directly

---

## Public API Endpoints

Three new unauthenticated read-only endpoints added to `src/pxh/api.py`. These sit alongside the existing authenticated endpoints. All return JSON; all are safe to expose publicly (no session mutation, no file paths, no credentials).

### CORS

CORS is handled via FastAPI's `CORSMiddleware` added to the app, **not** via inline response headers. Configuration:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://spark.wedd.au"],
    allow_methods=["GET"],
    allow_headers=[],
)
```

This applies to all routes including the public endpoints, and correctly handles `OPTIONS` preflight requests.

### `GET /api/v1/public/status`

```json
{
  "persona": "spark",
  "mood": "curious",
  "last_thought": "I wonder if Obi knows that octopuses have three hearts.",
  "last_action": "comment",
  "ts": "2026-03-12T04:00:00Z",
  "listening": false
}
```

Source: `state/session.json` (for `persona`, `listening`) + the persona-scoped thoughts file (for `mood`, `last_thought`, `last_action`, `ts`).

**Persona-scoped thoughts:** `px-mind` writes to `state/thoughts-{persona}.jsonl` when a persona is active (e.g. `thoughts-spark.jsonl`), falling back to `state/thoughts.jsonl` when no persona is set. The endpoint must replicate this logic: read `session.persona`, then read from `state/thoughts-{persona}.jsonl` if set, else `state/thoughts.jsonl`.

**Null safety:** if the resolved thoughts file is empty or missing, all thought fields return `null`. If any field is absent from the last entry, it returns `null`. The endpoint never raises a `KeyError` — all field reads use `.get()` with `None` default.

### `GET /api/v1/public/vitals`

```json
{
  "cpu_pct": 12.3,
  "ram_pct": 54.1,
  "cpu_temp_c": 61.2,
  "battery_pct": 78,
  "disk_pct": 42.0,
  "ts": "2026-03-12T04:00:00Z"
}
```

Source: `psutil` + `/sys/class/thermal/thermal_zone0/temp` + `state/battery.json`. Disk usage path is `/` (SD card root). Called on demand — `ts` is generated at request time via `utc_timestamp()`. No server-side cache.

**psutil dependency:** `psutil` is NOT currently in the venv. Add `psutil` to `requirements.txt` and run `pip install psutil` in the venv as part of implementation.

**battery_pct key mapping:** `state/battery.json` uses key `"pct"` (not `"battery_pct"`). The endpoint reads `data["pct"]` and returns it as `"battery_pct"` in the response — same pattern as the `distance_cm` → `sonar_cm` mapping for sonar.

### `GET /api/v1/public/sonar`

```json
{
  "sonar_cm": 142.5,
  "age_seconds": 8,
  "source": "sonar_live"
}
```

Source: `state/sonar_live.json`. The file uses key `distance_cm` — the endpoint maps this to `sonar_cm` in the response. `age_seconds` = seconds since `ts` field in the file. `source` = `"sonar_live"` when fresh, `"unavailable"` when file is missing or age > 60s.

**sonar_live.json `ts` format:** The `ts` field is a Unix float (from `time.time()`), e.g. `1773297087.25`. Age is computed as `time.time() - data["ts"]`, not via `datetime.fromisoformat()`.

**Null values when unavailable:** When `source` is `"unavailable"`, both `sonar_cm` and `age_seconds` are `null`. The JS sonar card must handle `null` gracefully (display `"—"` rather than `"null cm"`).

**Note on thresholds:** px-mind treats sonar as stale at >15s (cognitive loop freshness). The public endpoint uses 60s (tolerates px-alive restart cycles of ~10s + network latency). These thresholds are deliberately different — the public endpoint is for display, not navigation decisions.

---

## Site Structure

Single-page scroll. Seven anchor sections. No page reloads. Fixed nav bar.

```
spark.wedd.au
├── #hero          Warm, illustrated. Live mood + last thought.
├── #live          Live dashboard: vitals, sonar, mood. Graceful offline fallback.
├── #how-it-works  Dark/technical. Architecture diagram. Three-layer brain. Voice pipeline.
├── #spark-brain   Warm, kid-friendly. Adapted from how-sparks-brain-works.md.
├── #faq           Mixed tone. Accordion. Adapted from faq.md.
├── #docs          Dark/technical. Tools + scripts reference. Collapsible. Syntax highlighted.
└── #roadmap       Dark. Checklist style. Adapted from ROADMAP.md.
```

---

## File Layout

```
site/
├── index.html           Main document — all sections inline
├── CNAME                spark.wedd.au
├── css/
│   ├── base.css         Reset, custom properties, nav, typography
│   ├── warm.css         Cream/amber/coral palette — hero, spark-brain, faq
│   ├── dark.css         Near-black, green-tinted mono — how-it-works, docs, roadmap
│   └── highlight.min.css  Pinned highlight.js theme (committed locally, no CDN)
└── js/
    ├── live.js          API polling (30s interval), localStorage cache, offline banner
    ├── nav.js           Scroll spy, active anchor highlighting
    └── highlight.min.js   Pinned highlight.js bundle (committed locally, no CDN)
```

---

## Dual Aesthetic

CSS custom properties defined per theme. Each `<section>` carries `data-theme="warm"` or `data-theme="dark"`.

**Warm theme** (hero, spark-brain, faq):
- Background: `#fdf6ec` (cream)
- Accent: `#e8875a` (coral/amber)
- Text: `#2d2d2d`
- Cards: `border-radius: 16px`, subtle drop shadow
- Typography: system serif for headings, sans for body

**Dark theme** (how-it-works, docs, roadmap):
- Background: `#0d0f12`
- Accent: `#4ade80` (terminal green)
- Text: `#e2e8f0`
- Code blocks: `#111318` background, green tint
- Typography: monospace headings, mono body for code, sans for prose

**Nav:** floats above both themes. Dark background (`#0d0f12`), always visible. Contains:
- Logo: "SPARK ●" where ● is the live status dot (green/amber/red)
- Anchor links: Home · Live · How It Works · Brain · FAQ · Docs · Roadmap

---

## Key Components

### Hero

- Full-width warm section
- SPARK name in large serif, one-liner tagline below
- Live mood: animated word bubble, updates every 30s from `/public/status`
- Last thought: pull-quote style, italic, coral accent bar on left
- Tagline: *"I programmed the soul. Claude writes the diary."*

### Live Dashboard

- 2×2 grid of stat cards (CPU, RAM, battery, sonar)
- Each card: large number, label, colour-shift indicator (green→amber→red)
- Below grid: last thought + mood tag + timestamp
- "Last updated X seconds ago" footer line
- Offline banner: `"Pi offline — showing data from [locale timestamp]"` (formatted via `toLocaleString('en-AU')`)
- Data cached to `localStorage` key `spark_last_known` on every successful fetch

### Architecture Diagram

- The ASCII flow diagram from `how-sparks-brain-works.md` redrawn as a styled `<pre>` block
- Dark section background, green connector characters, monospace labels
- No SVG / no external assets

### Docs Section

- `TOOLS.md` and `SCRIPTS.md` content copied into `index.html` at commit time
- **Accepted trade-off:** content is duplicated from markdown sources. The "not duplicated" success criterion below is removed. The markdown files remain the edit-source; `index.html` is updated when they change.
- Syntax highlighting via highlight.js pinned version (committed to `site/js/highlight.min.js` — no CDN dependency)
- Each tool wrapped in `<details><summary>tool-name</summary>...</details>` for collapse

### FAQ

- `faq.md` questions rendered as `<details><summary>Question</summary>Answer</details>` accordion
- Warm section, conversational typography

### Roadmap

- `ROADMAP.md` rendered with checkboxes styled as ✅/⬜
- Dark section, grouped by time horizon

---

## Live Data Behaviour

```
On page load:
  1. Attempt fetch /public/status, /public/vitals, /public/sonar in parallel
     Each fetch has a 5s AbortController timeout.
  2a. All succeed → update UI, cache to localStorage with ISO timestamp
  2b. Any fail or timeout → load from localStorage, show offline banner
      Banner text: "Pi offline — showing data from [toLocaleString('en-AU')]"

Every 30s:
  Repeat fetch cycle. Update UI or refresh staleness indicator.

Status dot logic:
  Green  = last successful fetch < 60s ago   (normal — polls every 30s)
  Amber  = last successful fetch 60s–5min ago (Pi flapping / 2+ missed polls)
  Red    = last successful fetch > 5min ago OR never fetched
```

---

## Cloudflare Tunnel Setup (Pi-side)

The tunnel token is already stored in `.env` as `CF_TUNNEL_TOKEN`.

1. Install cloudflared: `curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb && sudo dpkg -i cloudflared.deb`
2. Run via token (no login/credentials file needed): `cloudflared tunnel run --token $CF_TUNNEL_TOKEN`
3. Systemd service at `/etc/systemd/system/cloudflared.service`:
   ```ini
   [Unit]
   Description=Cloudflare Tunnel
   After=network.target

   [Service]
   EnvironmentFile=/home/pi/picar-x-hacking/.env
   ExecStart=/usr/bin/cloudflared tunnel run --token ${CF_TUNNEL_TOKEN}
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
4. `sudo systemctl enable --now cloudflared`

DNS (`api.spark.wedd.au` CNAME) is configured via the Cloudflare dashboard — already handled by the tunnel token.

---

## Content Security Policy

`index.html` includes a `<meta http-equiv="Content-Security-Policy">` tag:

```
default-src 'self';
script-src 'self';
style-src 'self';
img-src 'self' data:;
connect-src https://api.spark.wedd.au;
```

`img-src 'self' data:` allows same-origin images and data URIs (e.g. inline favicon). No external image sources are permitted.

highlight.js is committed locally (`site/js/highlight.min.js`) — no CDN `script-src` needed. This prevents a compromised CDN from executing code in the page.

**Inline style restriction:** `style-src 'self'` blocks inline `style="..."` attributes and JS `element.style.*` assignments. All dynamic colour changes (e.g. stat card green→amber→red) must be implemented via CSS classes toggled from JS (`element.classList.add('warn')`), not inline styles. No exceptions — adding `'unsafe-inline'` would negate the CSP meaningfully.

## Tests

Add tests to `tests/test_api.py` (or equivalent) covering all three public endpoints:
- Happy path: endpoint returns correct field names and types
- Persona-scoped thoughts: `/public/status` reads `thoughts-spark.jsonl` when `session.persona = "spark"`
- Empty/missing thoughts file: `/public/status` returns `null` fields without error
- Missing `sonar_live.json`: `/public/sonar` returns `source: "unavailable"`, `sonar_cm: null`
- Missing `battery.json`: `/public/vitals` returns `battery_pct: null` without error
- `psutil` import failure: `/public/vitals` returns `null` for cpu/ram/disk fields rather than 500-erroring

Use the `isolated_project` fixture (sets `PX_STATE_DIR` to a temp dir) to control state file presence.

---

## Out of Scope

- Authentication on the public site
- Writing/mutating state from the public site
- Photo/video streaming (existing `/photos` endpoint remains auth-gated)
- Mobile app
- CMS or admin interface

---

## Success Criteria

- `spark.wedd.au` loads in < 2s on a cold browser
- Live dashboard updates reflect Pi state within 30s
- Site remains fully readable when Pi is offline (cached data shown, locale-formatted timestamp)
- Passes basic accessibility: semantic HTML, contrast ratios, keyboard navigation
- HTTPS enforced on GH Pages; all API calls over HTTPS only
