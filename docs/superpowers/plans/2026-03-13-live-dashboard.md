# Live Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three new public API endpoints and rewrite the live dashboard section into a three-band display (PRESENCE / WORLD / MACHINE).

**Architecture:** Backend adds `/public/awareness`, `/public/history` (ring buffer), and `/public/services` to `src/pxh/api.py`. Frontend rewrites `site/js/live.js` as a polling orchestrator, adds `site/js/charts.js` (canvas drawing) and `site/js/dashboard.js` (DOM bindings), and replaces the 4-card `#live` section in `site/index.html` with three layered bands.

**Tech Stack:** Python 3.11, FastAPI, pytest (backend); vanilla JS ES2020 IIFE, HTML5 canvas, SVG (frontend); collections.deque + threading.Lock for ring buffer.

**Security note:** All JS DOM updates use `textContent` or explicit `createElement`/`appendChild` — never `innerHTML` with server-provided content.

**Spec:** `docs/superpowers/specs/2026-03-13-live-dashboard-design.md`

---

## Chunk 1: Backend endpoints

### Task 1: `/public/awareness` endpoint + tests

**Files:**
- Modify: `src/pxh/api.py` — add endpoint after `public_sonar()` (~line 287)
- Test: `tests/test_public_api.py` — add `TestPublicAwareness` class

- [ ] **Step 1: Write failing tests**

Add this class at the end of `tests/test_public_api.py`:

```python
class TestPublicAwareness:
    def test_returns_200(self, public_client):
        resp = public_client.get("/api/v1/public/awareness")
        assert resp.status_code == 200

    def test_no_auth_required(self, public_client):
        resp = public_client.get("/api/v1/public/awareness")
        assert resp.status_code == 200

    def test_has_required_keys(self, public_client):
        resp = public_client.get("/api/v1/public/awareness")
        data = resp.json()
        for key in ("obi_mode", "person_present", "frigate_score",
                    "ambient_level", "ambient_rms", "weather",
                    "minutes_since_speech", "time_period", "ts"):
            assert key in data, f"missing key: {key}"

    def test_null_fields_when_no_awareness_file(self, public_client, state_dir):
        # No awareness.json → all fields null, no 500
        resp = public_client.get("/api/v1/public/awareness")
        data = resp.json()
        assert data["obi_mode"] is None
        assert data["person_present"] is False   # false (not null) when frigate absent
        assert data["weather"] is None

    def test_flattened_projection_from_awareness_file(self, public_client, state_dir):
        awareness = {
            "ts": "2026-03-13T01:00:00Z",
            "obi_mode": "calm",
            "time_period": "night",
            "minutes_since_speech": 4.0,
            "frigate": {
                "person_present": True,
                "score": 0.74,
                "event_count": 1,
            },
            "ambient_sound": {"rms": 340, "level": "quiet"},
            "weather": {
                "temp_C": 14.2,
                "wind_kmh": 12,
                "humidity_pct": 68,
                "summary": "Cloudy",
            },
        }
        (state_dir / "awareness.json").write_text(json.dumps(awareness))
        resp = public_client.get("/api/v1/public/awareness")
        data = resp.json()
        assert data["obi_mode"] == "calm"
        assert data["person_present"] is True
        assert abs(data["frigate_score"] - 0.74) < 0.01
        assert data["ambient_rms"] == 340
        assert data["ambient_level"] == "quiet"
        assert data["minutes_since_speech"] == pytest.approx(4.0, abs=0.1)
        assert data["time_period"] == "night"
        assert data["ts"] == "2026-03-13T01:00:00Z"

    def test_temp_c_lowercase_normalised(self, public_client, state_dir):
        # awareness.json stores temp_C (uppercase); endpoint must normalise to temp_c
        awareness = {
            "weather": {"temp_C": 14.2, "wind_kmh": 12, "humidity_pct": 68, "summary": "Cloudy"},
        }
        (state_dir / "awareness.json").write_text(json.dumps(awareness))
        resp = public_client.get("/api/v1/public/awareness")
        data = resp.json()
        assert data["weather"] is not None
        assert "temp_c" in data["weather"]
        assert abs(data["weather"]["temp_c"] - 14.2) < 0.01
        assert "temp_C" not in data["weather"]

    def test_person_present_false_when_frigate_key_absent(self, public_client, state_dir):
        # awareness.json with no frigate key at all
        (state_dir / "awareness.json").write_text(json.dumps({"obi_mode": "absent"}))
        data = public_client.get("/api/v1/public/awareness").json()
        assert data["person_present"] is False  # false, not null

    def test_person_present_false_when_frigate_is_none(self, public_client, state_dir):
        # awareness.json with frigate: null (offline)
        (state_dir / "awareness.json").write_text(json.dumps({"frigate": None}))
        data = public_client.get("/api/v1/public/awareness").json()
        assert data["person_present"] is False

    def test_weather_null_when_weather_key_absent(self, public_client, state_dir):
        (state_dir / "awareness.json").write_text(json.dumps({"obi_mode": "calm"}))
        data = public_client.get("/api/v1/public/awareness").json()
        assert data["weather"] is None

    def test_nested_null_for_missing_subkeys(self, public_client, state_dir):
        # ambient_sound present but missing level → null for that subfield
        awareness = {"ambient_sound": {"rms": 200}}
        (state_dir / "awareness.json").write_text(json.dumps(awareness))
        data = public_client.get("/api/v1/public/awareness").json()
        assert data["ambient_rms"] == 200
        assert data["ambient_level"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate
python -m pytest tests/test_public_api.py::TestPublicAwareness -v 2>&1 | tail -15
```

Expected: All tests FAIL with "404 Not Found" or similar.

- [ ] **Step 3: Implement `/public/awareness` in `src/pxh/api.py`**

Add this after the `public_sonar()` function (around line 287):

```python
@app.get("/api/v1/public/awareness")
async def public_awareness() -> Dict[str, Any]:
    """SPARK awareness snapshot: mode, Frigate, ambient, weather, time context. No auth."""
    try:
        awareness = json.loads((_public_state_dir() / "awareness.json").read_text())
    except Exception:
        awareness = {}

    # frigate can be None (offline) or a dict — handle both
    frigate = awareness.get("frigate") or {}
    frigate_present = awareness.get("frigate") is not None
    ambient = awareness.get("ambient_sound") or {}
    raw_weather = awareness.get("weather")

    if raw_weather is not None:
        weather_out: Any = {
            "temp_c": raw_weather.get("temp_C"),      # normalise uppercase → lowercase
            "wind_kmh": raw_weather.get("wind_kmh"),
            "humidity_pct": raw_weather.get("humidity_pct"),
            "summary": raw_weather.get("summary"),
        }
    else:
        weather_out = None

    return {
        "obi_mode": awareness.get("obi_mode"),
        "person_present": frigate.get("person_present", False) if frigate_present else False,
        "frigate_score": frigate.get("score"),
        "ambient_level": ambient.get("level"),
        "ambient_rms": ambient.get("rms"),
        "weather": weather_out,
        "minutes_since_speech": awareness.get("minutes_since_speech"),
        "time_period": awareness.get("time_period"),
        "ts": awareness.get("ts"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_public_api.py::TestPublicAwareness -v 2>&1 | tail -15
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pxh/api.py tests/test_public_api.py
git commit -m "feat(api): add /public/awareness endpoint with explicit field projection"
```

---

### Task 2: `/public/history` ring buffer + tests

**Files:**
- Modify: `src/pxh/api.py` — add ring buffer globals, `_collect_history_sample()`, background thread, endpoint
- Test: `tests/test_public_api.py` — add `TestPublicHistory` class

- [ ] **Step 1: Write failing tests**

Add at the end of `tests/test_public_api.py`:

```python
class TestPublicHistory:
    def test_returns_200(self, public_client):
        resp = public_client.get("/api/v1/public/history")
        assert resp.status_code == 200

    def test_no_auth_required(self, public_client):
        resp = public_client.get("/api/v1/public/history")
        assert resp.status_code == 200

    def test_returns_list(self, public_client):
        resp = public_client.get("/api/v1/public/history")
        assert isinstance(resp.json(), list)

    def test_endpoint_reads_from_ring_buffer(self, public_client):
        from pxh import api as _api
        # Pre-populate the buffer directly (bypasses background thread)
        with _api._history_lock:
            _api._history_buf.clear()
            _api._history_buf.append({
                "ts": "2026-03-13T00:00:00Z", "cpu_pct": 25.0, "ram_pct": 40.0,
                "cpu_temp_c": 52.0, "battery_pct": 80, "sonar_cm": 45.2, "ambient_rms": 340,
            })
        resp = public_client.get("/api/v1/public/history")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["cpu_pct"] == pytest.approx(25.0, abs=0.1)
        assert data[0]["sonar_cm"] == pytest.approx(45.2, abs=0.1)

    def test_maxlen_60_enforced(self, public_client):
        from pxh import api as _api
        with _api._history_lock:
            _api._history_buf.clear()
            for i in range(70):
                _api._history_buf.append({"ts": f"t{i:03}", "cpu_pct": float(i)})
        resp = public_client.get("/api/v1/public/history")
        data = resp.json()
        # deque(maxlen=60) keeps the last 60
        assert len(data) == 60
        assert data[0]["ts"] == "t010"   # oldest remaining
        assert data[-1]["ts"] == "t069"  # newest

    def test_collect_sample_sonar_null_when_stale(self, state_dir, monkeypatch):
        import time as _time
        # Write a stale sonar file (> 60s old)
        old_ts = _time.time() - 120
        (state_dir / "sonar_live.json").write_text(
            json.dumps({"ts": old_ts, "distance_cm": 30.0})
        )
        monkeypatch.setenv("PX_STATE_DIR", str(state_dir))
        from pxh import api as _api
        sample = _api._collect_history_sample(state_dir)
        assert sample["sonar_cm"] is None

    def test_collect_sample_sonar_present_when_fresh(self, state_dir, monkeypatch):
        import time as _time
        fresh_ts = _time.time() - 5
        (state_dir / "sonar_live.json").write_text(
            json.dumps({"ts": fresh_ts, "distance_cm": 55.0})
        )
        monkeypatch.setenv("PX_STATE_DIR", str(state_dir))
        from pxh import api as _api
        sample = _api._collect_history_sample(state_dir)
        assert sample["sonar_cm"] == pytest.approx(55.0, abs=0.1)

    def test_collect_sample_has_required_fields(self, state_dir, monkeypatch):
        monkeypatch.setenv("PX_STATE_DIR", str(state_dir))
        from pxh import api as _api
        sample = _api._collect_history_sample(state_dir)
        for field in ("ts", "cpu_pct", "cpu_temp_c", "ram_pct",
                      "battery_pct", "sonar_cm", "ambient_rms"):
            assert field in sample, f"missing field: {field}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_public_api.py::TestPublicHistory -v 2>&1 | tail -15
```

Expected: All tests FAIL (`_history_lock` / `_history_buf` / `_collect_history_sample` not defined).

- [ ] **Step 3: Implement ring buffer + endpoint in `src/pxh/api.py`**

Add the following block right after the `_jobs` registry block (~line 118), before the `_public_state_dir` helper:

```python
# ---------------------------------------------------------------------------
# History ring buffer (background thread, 30s interval)
# ---------------------------------------------------------------------------

import collections as _collections

_history_buf: "_collections.deque[Dict[str, Any]]" = _collections.deque(maxlen=60)
_history_lock = threading.Lock()


def _collect_history_sample(state_dir: "Path") -> "Dict[str, Any]":
    """Collect one vitals + sonar + ambient reading. Extracted for testability."""
    import time as _time

    sample: Dict[str, Any] = {"ts": utc_timestamp()}

    # CPU / RAM
    try:
        import psutil as _psutil
        sample["cpu_pct"] = round(_psutil.cpu_percent(interval=None), 1)
        sample["ram_pct"] = round(_psutil.virtual_memory().percent, 1)
    except Exception:
        sample["cpu_pct"] = None
        sample["ram_pct"] = None

    # CPU temperature
    try:
        raw = _THERMAL_ZONE.read_text().strip()
        sample["cpu_temp_c"] = round(int(raw) / 1000.0, 1)
    except Exception:
        sample["cpu_temp_c"] = None

    # Battery
    try:
        bdata = json.loads((state_dir / "battery.json").read_text())
        sample["battery_pct"] = bdata.get("pct")
    except Exception:
        sample["battery_pct"] = None

    # Sonar — age gate: null if > 60s
    try:
        sdata = json.loads((state_dir / "sonar_live.json").read_text())
        age = _time.time() - float(sdata["ts"])
        sample["sonar_cm"] = sdata["distance_cm"] if age <= 60 else None
    except Exception:
        sample["sonar_cm"] = None

    # Ambient RMS from awareness.json
    try:
        aw = json.loads((state_dir / "awareness.json").read_text())
        ambient = aw.get("ambient_sound") or {}
        sample["ambient_rms"] = ambient.get("rms")
    except Exception:
        sample["ambient_rms"] = None

    return sample


def _history_worker() -> None:
    """Background daemon thread: appends a reading every 30s to _history_buf."""
    import time as _time

    while True:
        _time.sleep(30)
        try:
            sample = _collect_history_sample(_public_state_dir())
            with _history_lock:
                _history_buf.append(sample)
        except Exception:
            pass


_history_thread = threading.Thread(
    target=_history_worker, daemon=True, name="history-worker"
)
_history_thread.start()
```

Then add the endpoint after `public_awareness()`:

```python
@app.get("/api/v1/public/history")
async def public_history() -> list:
    """Ring buffer of up to 60 vitals readings (~30 min history). No auth."""
    with _history_lock:
        return list(_history_buf)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_public_api.py::TestPublicHistory -v 2>&1 | tail -15
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pxh/api.py tests/test_public_api.py
git commit -m "feat(api): add /public/history ring buffer endpoint with background thread"
```

---

### Task 3: `/public/services` endpoint + tests

**Files:**
- Modify: `src/pxh/api.py` — add `_PUBLIC_SERVICES` set + helper + endpoint
- Test: `tests/test_public_api.py` — add `TestPublicServices` class

- [ ] **Step 1: Write failing tests**

Add at the end of `tests/test_public_api.py`:

```python
class TestPublicServices:
    def test_returns_200_without_auth(self, public_client):
        resp = public_client.get("/api/v1/public/services")
        assert resp.status_code == 200

    def test_returns_dict_not_list(self, public_client):
        data = public_client.get("/api/v1/public/services").json()
        assert isinstance(data, dict), "should be dict, not list"

    def test_has_all_five_services(self, public_client):
        data = public_client.get("/api/v1/public/services").json()
        for svc in ("px-mind", "px-alive", "px-wake-listen",
                    "px-battery-poll", "px-api-server"):
            assert svc in data, f"missing service: {svc}"

    def test_values_are_valid_status_strings(self, public_client):
        valid = {"active", "activating", "failed", "inactive", "unknown"}
        data = public_client.get("/api/v1/public/services").json()
        for svc, status in data.items():
            assert status in valid, f"{svc} has invalid status: {status!r}"

    def test_existing_auth_services_endpoint_requires_auth(self, public_client):
        # Auth-required endpoint at /api/v1/services must still require auth
        resp = public_client.get("/api/v1/services")
        assert resp.status_code == 401

    def test_existing_auth_services_returns_list_shape(self, public_client):
        resp = public_client.get(
            "/api/v1/services",
            headers={"Authorization": "Bearer test-token-abc123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "services" in data
        assert isinstance(data["services"], list)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_public_api.py::TestPublicServices -v 2>&1 | tail -15
```

Expected: First four FAIL with 404. Last two pass (existing endpoint untouched).

- [ ] **Step 3: Implement `/public/services` in `src/pxh/api.py`**

Add this block in the service management section (after line 518, before `_run_systemctl`):

```python
# Public services endpoint queries these five explicitly. px-battery-poll is not
# in _MANAGED_SERVICES (the auth'd endpoint doesn't control it) but the public
# dashboard needs to show its status.
_PUBLIC_SERVICES = frozenset({
    "px-mind", "px-alive", "px-wake-listen", "px-battery-poll", "px-api-server"
})
_PUBLIC_SERVICE_STATES = frozenset({"active", "activating", "failed", "inactive", "unknown"})


def _get_public_service_status(service: str) -> tuple:
    """Returns (service_name, normalised_status_string)."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=5,
        )
        state = result.stdout.strip()
        if state not in _PUBLIC_SERVICE_STATES:
            state = "unknown"
        return (service, state)
    except Exception:
        return (service, "unknown")
```

Then add the endpoint after `public_history()`:

```python
@app.get("/api/v1/public/services")
async def public_services_status() -> Dict[str, str]:
    """Public service status dict (no auth). Shape: {name: status_string}.
    IMPORTANT: does not modify /api/v1/services — different shape, used by web UI.
    """
    loop = asyncio.get_running_loop()
    pairs = await asyncio.gather(*[
        loop.run_in_executor(None, _get_public_service_status, svc)
        for svc in sorted(_PUBLIC_SERVICES)
    ])
    return dict(pairs)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_public_api.py::TestPublicServices -v 2>&1 | tail -15
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Run full public API test suite**

```bash
python -m pytest tests/test_public_api.py -v 2>&1 | tail -10
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pxh/api.py tests/test_public_api.py
git commit -m "feat(api): add /public/services public endpoint (dict-shaped, no auth)"
```

---

## Chunk 2: Frontend HTML + CSS

### Task 4: Three-band HTML layout in `site/index.html`

**Files:**
- Modify: `site/index.html` — replace `<section id="live">` with three-band layout; update script tags

- [ ] **Step 1: Replace the `#live` section**

Find `<section id="live" data-theme="warm">` (line ~47) through its closing `</section>` (line ~87) and replace entirely with:

```html
<!-- ══════════════════════════════════════════════════ LIVE STATUS -->
<section id="live" data-theme="warm">
  <div class="container">
    <h2>Live Status</h2>

    <!-- ─── BAND 1: PRESENCE ─────────────────────────────────────── -->
    <div class="band band-presence" id="band-presence">

      <!-- Mood Pulse -->
      <div class="presence-mood">
        <div id="mood-pulse" class="pulse-circle pulse-mid" aria-label="SPARK mood">
          <span id="mood-word">…</span>
        </div>
        <p id="obi-mode-line" class="obi-mode-text"></p>
      </div>

      <!-- Last Thought -->
      <div class="presence-thought">
        <blockquote id="last-thought" class="pull-quote">Nothing on my mind just now…</blockquote>
        <div class="thought-meta">
          <span id="thought-mood-word" class="thought-mood"></span>
          <span id="thought-salience" class="salience-dots" aria-label="thought importance"></span>
          <span id="thought-age" class="thought-age"></span>
        </div>
      </div>

      <!-- Proximity Arc -->
      <div class="presence-proximity">
        <svg id="sonar-arc" viewBox="0 0 120 65" width="120" height="65"
             aria-label="proximity sensor" role="img">
          <!-- drawn by charts.js -->
        </svg>
        <div id="frigate-indicator" class="frigate-row hidden">
          <span id="frigate-icon" aria-hidden="true">&#x1F464;</span>
          <span id="frigate-confidence" class="frigate-conf"></span>
        </div>
      </div>

    </div><!-- /band-presence -->

    <!-- ─── BAND 2: WORLD ─────────────────────────────────────────── -->
    <div class="band band-world" id="band-world">

      <!-- Ambient sound -->
      <div class="world-ambient">
        <span id="ambient-level-label" class="ambient-label">—</span>
        <canvas id="waveform-canvas" width="200" height="40"
                aria-label="ambient sound level visualisation"></canvas>
      </div>

      <!-- Weather strip -->
      <div class="world-weather" id="world-weather-strip">
        <span id="weather-temp"></span>
        <span id="weather-symbol" aria-hidden="true"></span>
        <span id="weather-wind"></span>
        <span id="weather-humidity"></span>
        <span id="weather-summary" class="weather-summary"></span>
      </div>

      <!-- Time context -->
      <div class="world-time">
        <span id="local-time" class="local-time"></span>
        <span id="time-period-badge" class="period-badge"></span>
        <p id="last-spoke" class="last-spoke"></p>
      </div>

    </div><!-- /band-world -->

    <!-- ─── MACHINE TOGGLE ────────────────────────────────────────── -->
    <div class="band-machine-toggle">
      <button id="machine-toggle" class="toggle-btn" type="button"
              aria-expanded="false" aria-controls="band-machine">
        show internals ↓
      </button>
    </div>

    <!-- ─── BAND 3: MACHINE ───────────────────────────────────────── -->
    <div class="band band-machine" id="band-machine" aria-hidden="true">
      <div class="metric-grid">

        <!-- CPU % -->
        <div class="metric-tile" id="tile-cpu" data-sparkline="cpu_pct">
          <div class="metric-label">CPU</div>
          <div class="metric-bar-wrap"><div class="metric-bar" id="bar-cpu"></div></div>
          <div class="metric-value" id="val-cpu">—</div>
        </div>

        <!-- CPU Temp (radial gauge) -->
        <div class="metric-tile" id="tile-temp">
          <div class="metric-label">CPU Temp</div>
          <svg id="gauge-temp" viewBox="0 0 80 45" width="80" height="45"
               aria-label="CPU temperature gauge"></svg>
          <div class="metric-value" id="val-temp">—</div>
        </div>

        <!-- RAM % -->
        <div class="metric-tile" id="tile-ram" data-sparkline="ram_pct">
          <div class="metric-label">RAM</div>
          <div class="metric-bar-wrap"><div class="metric-bar" id="bar-ram"></div></div>
          <div class="metric-value" id="val-ram">—</div>
        </div>

        <!-- Disk % -->
        <div class="metric-tile" id="tile-disk">
          <div class="metric-label">Disk</div>
          <div class="metric-bar-wrap"><div class="metric-bar" id="bar-disk"></div></div>
          <div class="metric-value" id="val-disk">—</div>
        </div>

        <!-- Battery -->
        <div class="metric-tile" id="tile-battery" data-sparkline="battery_pct">
          <div class="metric-label">Battery</div>
          <div class="metric-bar-wrap"><div class="metric-bar" id="bar-battery"></div></div>
          <div class="metric-value" id="val-battery">—</div>
        </div>

        <!-- Services -->
        <div class="metric-tile" id="tile-services">
          <div class="metric-label">Services</div>
          <div id="services-dots" class="services-dots"></div>
        </div>

      </div><!-- /metric-grid -->
    </div><!-- /band-machine -->

    <!-- Offline banner (below all bands) -->
    <div id="offline-banner" class="hidden offline-banner mt-sm">
      Pi offline — showing data from <span id="offline-ts"></span>
    </div>

    <p class="text-xs opacity-40 mt-sm text-right" id="last-updated">
      Connecting…
    </p>
  </div>
</section>
```

- [ ] **Step 2: Update `<script>` tags at the bottom of `site/index.html`**

Find:
```html
<script src="js/highlight.min.js"></script>
<script src="js/init.js"></script>
<script src="js/live.js"></script>
<script src="js/nav.js"></script>
```

Replace with (charts.js and dashboard.js load before live.js — live.js depends on both):

```html
<script src="js/highlight.min.js"></script>
<script src="js/init.js"></script>
<script src="js/charts.js"></script>
<script src="js/dashboard.js"></script>
<script src="js/live.js"></script>
<script src="js/nav.js"></script>
```

- [ ] **Step 3: Verify structure renders**

Open `site/index.html` in browser. Verify the three bands are visible and the MACHINE band starts hidden.

- [ ] **Step 4: Commit**

```bash
git add site/index.html
git commit -m "feat(html): replace live section with three-band PRESENCE/WORLD/MACHINE layout"
```

---

### Task 5: CSS for dashboard components

**Files:**
- Modify: `site/css/warm.css` — append dashboard component styles
- Modify: `site/css/dark.css` — append dark theme overrides

- [ ] **Step 1: Append to `site/css/warm.css`**

```css
/* ── Live Dashboard — Bands ───────────────────────────────────── */

.band {
  border-radius: var(--radius);
  padding: 1.5rem;
  margin-bottom: 1rem;
}

.band-presence {
  display: grid;
  grid-template-columns: 1fr 2fr 1fr;
  gap: 1.5rem;
  align-items: start;
}

.band-world {
  display: grid;
  grid-template-columns: 2fr 1.75fr 1.25fr;
  gap: 1rem;
  align-items: center;
  background: rgba(0, 0, 0, 0.03);
}

.band-hidden { display: none; }

@media (max-width: 640px) {
  .band-presence,
  .band-world { grid-template-columns: 1fr; }
}

/* ── Mood Pulse ───────────────────────────────────────────────── */

.pulse-circle {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: var(--warm-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  font-weight: 600;
  color: #fff;
  text-align: center;
}

@keyframes pulse-slow {
  0%, 100% { transform: scale(1); }
  50%       { transform: scale(1.06); }
}
@keyframes pulse-mid {
  0%, 100% { transform: scale(1); }
  50%       { transform: scale(1.1); }
}
@keyframes pulse-fast {
  0%, 100% { transform: scale(1); }
  50%       { transform: scale(1.15); }
}

.pulse-slow { animation: pulse-slow 4s ease-in-out infinite; }
.pulse-mid  { animation: pulse-mid  2.5s ease-in-out infinite; }
.pulse-fast { animation: pulse-fast 1.5s ease-in-out infinite; }

.pulse-offline {
  animation: none;
  background: transparent;
  border: 3px solid var(--warm-muted);
  color: var(--warm-muted);
}

.obi-mode-text {
  font-size: 0.85rem;
  color: var(--warm-muted);
  margin-top: 0.5rem;
  text-align: center;
}

/* ── Last Thought ─────────────────────────────────────────────── */

.pull-quote {
  font-size: 1.15rem;
  font-style: italic;
  line-height: 1.6;
  margin: 0 0 0.75rem;
  padding: 0;
  border: none;
}

.thought-meta {
  font-size: 0.8rem;
  color: var(--warm-muted);
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.salience-dots { letter-spacing: 0.1em; color: var(--warm-accent); }
.thought-mood  { font-style: italic; }

/* ── Proximity Arc ────────────────────────────────────────────── */

.presence-proximity {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.frigate-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.85rem;
  color: var(--warm-muted);
}
.frigate-conf { font-size: 0.8rem; }

/* ── World Band: Ambient ───────────────────────────────────────── */

.world-ambient {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.ambient-label {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--warm-muted);
  white-space: nowrap;
}

/* ── World Band: Weather ──────────────────────────────────────── */

.world-weather {
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  color: var(--warm-text);
}
.weather-summary { color: var(--warm-muted); }

/* ── World Band: Time ─────────────────────────────────────────── */

.world-time { font-size: 0.85rem; text-align: right; }
.local-time { font-size: 1rem; font-weight: 600; }
.last-spoke { color: var(--warm-muted); margin: 0.25rem 0 0; font-size: 0.8rem; }

.period-badge {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  margin-left: 0.4rem;
}
.period-morning   { background: #fef3c7; color: #92400e; }
.period-afternoon { background: #dbeafe; color: #1e40af; }
.period-evening   { background: #ede9fe; color: #4c1d95; }
.period-night     { background: #1e293b; color: #94a3b8; }

/* ── Machine Band Toggle ─────────────────────────────────────── */

.band-machine-toggle { text-align: center; margin: 0.5rem 0; }
.toggle-btn {
  background: none;
  border: 1px solid var(--warm-muted);
  border-radius: 999px;
  padding: 0.3rem 1rem;
  font-size: 0.8rem;
  cursor: pointer;
  color: var(--warm-muted);
  transition: color 0.2s, border-color 0.2s;
}
.toggle-btn:hover { color: var(--warm-text); border-color: var(--warm-text); }

.band-machine {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.4s ease;
}
.band-machine.open { max-height: 800px; }

/* ── Metric Grid ─────────────────────────────────────────────── */

.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  padding: 1rem 0 0.5rem;
}
@media (max-width: 640px) {
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
}

.metric-tile {
  background: #fff;
  border-radius: var(--radius);
  padding: 0.9rem 1rem;
  box-shadow: 0 1px 6px rgba(0,0,0,0.06);
  cursor: default;
}
.metric-tile[data-sparkline] { cursor: pointer; }
.metric-tile[data-sparkline]:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.12); }

.metric-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--warm-muted);
  margin-bottom: 0.5rem;
}
.metric-value { font-size: 1.1rem; font-weight: 600; margin-top: 0.4rem; }

.metric-bar-wrap {
  height: 6px;
  background: rgba(0,0,0,0.08);
  border-radius: 3px;
  overflow: hidden;
}
.metric-bar {
  height: 100%;
  width: 0%;
  background: var(--warm-accent);
  border-radius: 3px;
  transition: width 0.4s ease;
}
.metric-bar.warn { background: #d97706; }
.metric-bar.crit { background: #dc2626; }

.metric-tile.disk-warn .metric-value { color: #d97706; }
.metric-tile.disk-crit .metric-value { color: #dc2626; }

.gauge-ok   .gauge-fill { stroke: #16a34a; }
.gauge-warn .gauge-fill { stroke: #d97706; }
.gauge-crit .gauge-fill { stroke: #dc2626; }

/* Arc fill colours (proximity arc in SVG) */
.arc-close { fill: var(--warm-accent); opacity: 0.85; }
.arc-mid   { fill: #64748b; opacity: 0.55; }
.arc-far   { fill: #94a3b8; opacity: 0.35; }

/* Services dots */
.services-dots { display: flex; flex-direction: column; gap: 0.3rem; margin-top: 0.25rem; }
.service-dot-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: var(--warm-muted);
}
.dot-ok   { color: #16a34a; }
.dot-warn { color: #d97706; }
.dot-err  { color: #dc2626; }

/* Sparkline canvas */
.sparkline-canvas { display: block; margin-top: 0.5rem; width: 100%; }
.sparkline-label  { font-size: 0.7rem; color: var(--warm-muted); margin-top: 0.2rem; }
```

- [ ] **Step 2: Append to `site/css/dark.css`**

```css
/* ── Live Dashboard — Dark Theme Overrides ────────────────────── */

[data-theme="dark"] .band-world {
  background: rgba(255,255,255,0.03);
}

[data-theme="dark"] .pulse-circle {
  background: var(--dark-accent);
  color: var(--dark-bg);
}

[data-theme="dark"] .metric-tile {
  background: #1a1d22;
  box-shadow: 0 1px 6px rgba(0,0,0,0.3);
}

[data-theme="dark"] .metric-bar-wrap {
  background: rgba(255,255,255,0.1);
}

[data-theme="dark"] .metric-bar { background: var(--dark-accent); }

[data-theme="dark"] .toggle-btn {
  border-color: var(--dark-muted);
  color: var(--dark-muted);
}
[data-theme="dark"] .toggle-btn:hover {
  color: var(--dark-text);
  border-color: var(--dark-text);
}

[data-theme="dark"] .arc-close { fill: var(--dark-accent); }
```

- [ ] **Step 3: Visual check in both themes**

Verify PRESENCE/WORLD bands render correctly in warm theme. Use DevTools to set `data-theme="dark"` on `<section>` and check dark overrides apply.

- [ ] **Step 4: Commit**

```bash
git add site/css/warm.css site/css/dark.css
git commit -m "feat(css): add three-band dashboard styles (pulse, bands, metrics, sparkline)"
```

---

## Chunk 3: Frontend JavaScript

### Task 6: `site/js/charts.js` — Canvas and SVG drawing

**Files:**
- Create: `site/js/charts.js`

- [ ] **Step 1: Create `site/js/charts.js`**

All SVG elements are created via `createElementNS` + `setAttribute`. No `innerHTML` with dynamic data.

```javascript
// charts.js — Canvas/SVG drawing for the live dashboard.
// Exposes: window.SparkCharts
window.SparkCharts = (function () {
  'use strict';

  // ── Waveform bars ────────────────────────────────────────────────────────
  function drawWaveform(canvas, rms) {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const BAR_COUNT = 40;
    const BAR_W = Math.floor(W / BAR_COUNT) - 1;
    const MAX_H = H - 4;
    const BASE_H = 3;

    // Deterministic pseudo-random seeded from rms
    let s = Math.round(rms || 0) + 1;
    function rand() {
      s = (s * 1664525 + 1013904223) & 0xffffffff;
      return (s >>> 16) / 65535;
    }

    const amplitude = Math.min(1, Math.max(0, (rms || 0) / 1500));
    ctx.fillStyle = getComputedStyle(document.documentElement)
      .getPropertyValue('--warm-accent').trim() || '#e8875a';

    for (let i = 0; i < BAR_COUNT; i++) {
      const barH = BASE_H + Math.round(rand() * MAX_H * amplitude);
      ctx.fillRect(i * (BAR_W + 1), H - barH, Math.max(1, BAR_W), barH);
    }
  }

  // ── Proximity fan arc (SVG) ──────────────────────────────────────────────
  function drawProximityArc(svgEl, sonarCm) {
    if (!svgEl) return;

    let angleDeg, colorClass;
    if (sonarCm === null || sonarCm === undefined) {
      angleDeg = 0; colorClass = 'arc-unavailable';
    } else if (sonarCm < 40) {
      angleDeg = 180; colorClass = 'arc-close';
    } else if (sonarCm <= 100) {
      angleDeg = 90; colorClass = 'arc-mid';
    } else if (sonarCm <= 150) {
      angleDeg = Math.round(90 - (sonarCm - 100) * (70 / 50));
      colorClass = 'arc-far';
    } else {
      angleDeg = 20; colorClass = 'arc-far';
    }

    // Clear all child elements without innerHTML
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);

    const CX = 60, CY = 60, R = 55;
    const NS = 'http://www.w3.org/2000/svg';

    // Outline arc
    const outline = document.createElementNS(NS, 'path');
    outline.setAttribute('d', _arcPath(CX, CY, R, 0, 180));
    outline.setAttribute('fill', 'none');
    outline.setAttribute('stroke', '#d1c4b8');
    outline.setAttribute('stroke-width', '2');
    svgEl.appendChild(outline);

    if (angleDeg > 0) {
      const fill = document.createElementNS(NS, 'path');
      fill.setAttribute('d', _arcPath(CX, CY, R, 0, angleDeg) + ' L ' + CX + ' ' + CY + ' Z');
      fill.setAttribute('class', 'arc-fill ' + colorClass);
      svgEl.appendChild(fill);
    }
  }

  function _arcPath(cx, cy, r, startDeg, endDeg) {
    const toRad = d => (d - 90) * Math.PI / 180;
    const sx = cx + r * Math.cos(toRad(startDeg));
    const sy = cy + r * Math.sin(toRad(startDeg));
    const ex = cx + r * Math.cos(toRad(endDeg));
    const ey = cy + r * Math.sin(toRad(endDeg));
    const large = (endDeg - startDeg) > 180 ? 1 : 0;
    return 'M ' + sx + ' ' + sy + ' A ' + r + ' ' + r + ' 0 ' + large + ' 1 ' + ex + ' ' + ey;
  }

  // ── CPU Temperature Gauge Arc (SVG) ─────────────────────────────────────
  function drawGaugeArc(svgEl, tempC) {
    if (!svgEl) return;
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);

    const NS = 'http://www.w3.org/2000/svg';
    const CX = 40, CY = 42, R = 35;

    // Background track
    const track = document.createElementNS(NS, 'path');
    track.setAttribute('d', _arcPath(CX, CY, R, 0, 180));
    track.setAttribute('fill', 'none');
    track.setAttribute('stroke', '#e5e7eb');
    track.setAttribute('stroke-width', '6');
    track.setAttribute('stroke-linecap', 'round');
    svgEl.appendChild(track);

    if (tempC !== null && tempC !== undefined) {
      const pct = Math.min(1, Math.max(0, tempC / 85));
      const fillAngle = Math.round(pct * 180);

      let gaugeClass = 'gauge-ok';
      if (tempC >= 75) gaugeClass = 'gauge-crit';
      else if (tempC >= 65) gaugeClass = 'gauge-warn';
      svgEl.setAttribute('class', gaugeClass);

      const fill = document.createElementNS(NS, 'path');
      fill.setAttribute('d', _arcPath(CX, CY, R, 0, Math.max(1, fillAngle)));
      fill.setAttribute('fill', 'none');
      fill.setAttribute('class', 'gauge-fill');
      fill.setAttribute('stroke-width', '6');
      fill.setAttribute('stroke-linecap', 'round');
      svgEl.appendChild(fill);
    }
  }

  // ── Sparkline ────────────────────────────────────────────────────────────
  function drawSparkline(canvas, points, field) {
    if (!canvas || !points || points.length < 2) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const vals = points.map(p => p[field]).filter(v => v !== null && v !== undefined);
    if (vals.length < 2) return;

    const minV = Math.min(...vals);
    const maxV = Math.max(...vals);
    const range = maxV - minV || 1;

    const toX = i => (i / (points.length - 1)) * (W - 4) + 2;
    const toY = v => H - 4 - ((v - minV) / range) * (H - 8);

    ctx.beginPath();
    ctx.strokeStyle = getComputedStyle(document.documentElement)
      .getPropertyValue('--warm-accent').trim() || '#e8875a';
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';

    let first = true;
    points.forEach((p, i) => {
      const v = p[field];
      if (v === null || v === undefined) return;
      if (first) { ctx.moveTo(toX(i), toY(v)); first = false; }
      else ctx.lineTo(toX(i), toY(v));
    });
    ctx.stroke();

    // Range labels
    ctx.fillStyle = '#999';
    ctx.font = '9px sans-serif';
    ctx.fillText(minV.toFixed(0), 2, H - 1);
    ctx.fillText(maxV.toFixed(0), 2, 9);
  }

  return { drawWaveform, drawProximityArc, drawGaugeArc, drawSparkline };
})();
```

- [ ] **Step 2: Verify `window.SparkCharts` is defined**

Open browser DevTools console on `site/index.html`:
```javascript
Object.keys(window.SparkCharts)
// Expected: ["drawWaveform", "drawProximityArc", "drawGaugeArc", "drawSparkline"]
```

- [ ] **Step 3: Commit**

```bash
git add site/js/charts.js
git commit -m "feat(js): add charts.js — waveform, proximity arc, gauge, sparkline canvas drawing"
```

---

### Task 7: `site/js/dashboard.js` — DOM binding functions

**Files:**
- Create: `site/js/dashboard.js`

All DOM updates use `textContent` or safe DOM construction — no `innerHTML` with server-supplied data.

- [ ] **Step 1: Create `site/js/dashboard.js`**

```javascript
// dashboard.js — DOM update functions for the three-band live dashboard.
// Depends on: charts.js (SparkCharts). Exposes: window.SparkDashboard.
window.SparkDashboard = (function () {
  'use strict';

  const $ = id => document.getElementById(id);

  // ── Presence band ────────────────────────────────────────────────────────

  const PULSE_CLASSES = {
    peaceful: 'pulse-slow', content: 'pulse-slow',
    curious: 'pulse-mid', contemplative: 'pulse-mid',
    excited: 'pulse-fast', active: 'pulse-fast',
  };
  const OBI_MODE_TEXT = {
    absent: "Obi's probably asleep",
    calm: 'Obi seems nearby',
    active: 'Obi is around',
    'possibly-overloaded': 'Things seem busy',
  };

  function renderPresence(state) {
    const mood = (state.mood || '').toLowerCase();
    const pulse = $('mood-pulse');
    if (pulse) {
      pulse.classList.remove('pulse-slow', 'pulse-mid', 'pulse-fast', 'pulse-offline');
      pulse.classList.add(state.mood ? (PULSE_CLASSES[mood] || 'pulse-mid') : 'pulse-offline');
      const word = $('mood-word');
      if (word) word.textContent = state.mood || '—';
    }

    const modeLine = $('obi-mode-line');
    if (modeLine) modeLine.textContent = OBI_MODE_TEXT[state.obi_mode] || '';

    const quote = $('last-thought');
    if (quote) quote.textContent = state.last_thought || 'Nothing on my mind just now…';

    const thoughtMood = $('thought-mood-word');
    if (thoughtMood) thoughtMood.textContent = state.mood || '';

    const salienceDots = $('thought-salience');
    if (salienceDots && typeof state.salience === 'number') {
      const filled = Math.round(state.salience * 5);
      salienceDots.textContent = '●'.repeat(filled) + '○'.repeat(5 - filled);
    } else if (salienceDots) {
      salienceDots.textContent = '';
    }

    const ageEl = $('thought-age');
    if (ageEl && state.ts) {
      const mins = Math.round((Date.now() - new Date(state.ts).getTime()) / 60000);
      ageEl.textContent = mins <= 1 ? 'just now' : (mins + ' min ago');
    }

    SparkCharts.drawProximityArc($('sonar-arc'), state.sonar_cm != null ? state.sonar_cm : null);

    const frigateRow = $('frigate-indicator');
    if (frigateRow) {
      if (state.person_present === null || state.person_present === undefined) {
        frigateRow.classList.add('hidden');
      } else {
        frigateRow.classList.remove('hidden');
        const icon = $('frigate-icon');
        // Use Unicode code points as textContent — safe, not innerHTML
        if (icon) icon.textContent = state.person_present ? '\uD83D\uDC64' : '\uD83D\uDC65';
        const conf = $('frigate-confidence');
        if (conf) {
          conf.textContent = (state.person_present && state.frigate_score != null)
            ? Math.round(state.frigate_score * 100) + '%' : '';
        }
      }
    }
  }

  // ── World band ───────────────────────────────────────────────────────────

  const WEATHER_SYMBOL_MAP = [
    ['sunny', '☀'], ['clear', '☀'], ['cloudy', '☁'], ['overcast', '☁'],
    ['rain', '🌧'], ['shower', '🌧'], ['drizzle', '🌧'],
    ['snow', '❄'], ['frost', '❄'], ['fog', '🌫'],
  ];

  function _weatherSymbol(summary) {
    if (!summary) return '';
    const s = summary.toLowerCase();
    for (const [key, sym] of WEATHER_SYMBOL_MAP) {
      if (s.includes(key)) return sym;
    }
    return '';
  }

  function renderWorld(state) {
    const label = $('ambient-level-label');
    if (label) label.textContent = state.ambient_level || '—';

    const weatherStrip = $('world-weather-strip');
    if (weatherStrip) {
      if (!state.weather) {
        weatherStrip.classList.add('hidden');
      } else {
        weatherStrip.classList.remove('hidden');
        const w = state.weather;
        const temp = $('weather-temp');
        if (temp) temp.textContent = w.temp_c != null ? (w.temp_c + '°C') : '';
        const sym = $('weather-symbol');
        if (sym) sym.textContent = _weatherSymbol(w.summary);
        const wind = $('weather-wind');
        if (wind) wind.textContent = w.wind_kmh != null ? (w.wind_kmh + ' km/h') : '';
        const hum = $('weather-humidity');
        if (hum) hum.textContent = w.humidity_pct != null ? (w.humidity_pct + '%') : '';
        const sumEl = $('weather-summary');
        // First sentence only — strip at period to keep it short
        if (sumEl) sumEl.textContent = (w.summary || '').split('.')[0];
      }
    }

    const timeEl = $('local-time');
    if (timeEl) {
      timeEl.textContent = new Date().toLocaleTimeString('en-AU', {
        hour: '2-digit', minute: '2-digit', timeZone: 'Australia/Hobart',
      });
    }

    const badge = $('time-period-badge');
    if (badge) {
      badge.classList.remove('period-morning', 'period-afternoon', 'period-evening', 'period-night');
      if (state.time_period) {
        badge.classList.add('period-' + state.time_period);
        badge.textContent = state.time_period;
      } else {
        badge.textContent = '';
      }
    }

    const lastSpoke = $('last-spoke');
    if (lastSpoke) {
      if (typeof state.minutes_since_speech === 'number') {
        const m = Math.round(state.minutes_since_speech);
        lastSpoke.textContent = m > 30 ? "hasn't spoken recently" : ('Last spoke ' + m + ' min ago');
      } else {
        lastSpoke.textContent = '';
      }
    }
  }

  // ── Machine band ─────────────────────────────────────────────────────────

  function _setBar(barId, pct, warnAt, critAt) {
    const bar = $(barId);
    if (!bar) return;
    bar.classList.remove('warn', 'crit');
    if (pct == null) { bar.style.width = '0%'; return; }
    bar.style.width = Math.min(100, Math.max(0, pct)) + '%';
    if (pct >= critAt) bar.classList.add('crit');
    else if (pct >= warnAt) bar.classList.add('warn');
  }

  function renderMachine(state) {
    _setBar('bar-cpu', state.cpu_pct, 70, 90);
    const valCpu = $('val-cpu');
    if (valCpu) valCpu.textContent = state.cpu_pct != null ? (state.cpu_pct + '%') : '—';

    SparkCharts.drawGaugeArc($('gauge-temp'), state.cpu_temp_c != null ? state.cpu_temp_c : null);
    const valTemp = $('val-temp');
    if (valTemp) valTemp.textContent = state.cpu_temp_c != null ? (state.cpu_temp_c + '°C') : '—';

    _setBar('bar-ram', state.ram_pct, 75, 90);
    const valRam = $('val-ram');
    if (valRam) valRam.textContent = state.ram_pct != null ? (state.ram_pct + '%') : '—';

    _setBar('bar-disk', state.disk_pct, 80, 90);
    const valDisk = $('val-disk');
    if (valDisk) valDisk.textContent = state.disk_pct != null ? (state.disk_pct + '%') : '—';
    const tileDisk = $('tile-disk');
    if (tileDisk) {
      tileDisk.classList.remove('disk-warn', 'disk-crit');
      if (state.disk_pct >= 90) tileDisk.classList.add('disk-crit');
      else if (state.disk_pct >= 80) tileDisk.classList.add('disk-warn');
    }

    _setBar('bar-battery', state.battery_pct, 15, 10);
    const valBattery = $('val-battery');
    if (valBattery) {
      const pct = state.battery_pct != null ? (state.battery_pct + '%') : '—';
      valBattery.textContent = pct + (state.charging ? ' ⚡' : '');
    }

    // Services dots — built with createElement, not innerHTML
    const dotsContainer = $('services-dots');
    if (dotsContainer && state.services) {
      // Remove existing children
      while (dotsContainer.firstChild) dotsContainer.removeChild(dotsContainer.firstChild);

      const DOT_CLASS  = { active: 'dot-ok', activating: 'dot-warn', failed: 'dot-err',
                           inactive: 'dot-warn', unknown: 'dot-warn' };
      const DOT_SYMBOL = { active: '●', activating: '◐', failed: '●',
                           inactive: '○', unknown: '○' };

      for (const [svc, status] of Object.entries(state.services)) {
        const row = document.createElement('div');
        row.className = 'service-dot-row';

        const dotSpan = document.createElement('span');
        dotSpan.className = DOT_CLASS[status] || 'dot-warn';
        dotSpan.textContent = DOT_SYMBOL[status] || '○';

        const nameSpan = document.createElement('span');
        nameSpan.textContent = svc.replace('px-', '');

        row.appendChild(dotSpan);
        row.appendChild(nameSpan);
        dotsContainer.appendChild(row);
      }
    }
  }

  // ── MACHINE toggle ───────────────────────────────────────────────────────

  const MACHINE_KEY = 'spark_machine_open';

  function initToggle() {
    const btn = $('machine-toggle');
    const band = $('band-machine');
    if (!btn || !band) return;

    function setOpen(open) {
      band.classList.toggle('open', open);
      band.setAttribute('aria-hidden', String(!open));
      btn.setAttribute('aria-expanded', String(open));
      btn.textContent = open ? 'hide internals ↑' : 'show internals ↓';
      localStorage.setItem(MACHINE_KEY, open ? 'true' : 'false');
    }

    setOpen(localStorage.getItem(MACHINE_KEY) === 'true');
    btn.addEventListener('click', () => setOpen(!band.classList.contains('open')));
  }

  // ── Shared helpers ───────────────────────────────────────────────────────

  function setOnline(online, cachedAt) {
    const banner = $('offline-banner');
    if (!banner) return;
    banner.classList.toggle('hidden', online);
    if (!online && cachedAt) {
      const offlineTs = $('offline-ts');
      if (offlineTs) offlineTs.textContent = new Date(cachedAt).toLocaleString('en-AU');
    }
  }

  function setLastUpdated(text) {
    const el = $('last-updated');
    if (el) el.textContent = text;
  }

  return { renderPresence, renderWorld, renderMachine, initToggle, setOnline, setLastUpdated };
})();
```

- [ ] **Step 2: Verify in DevTools console**

```javascript
Object.keys(window.SparkDashboard)
// Expected: ["renderPresence", "renderWorld", "renderMachine", "initToggle", "setOnline", "setLastUpdated"]
```

- [ ] **Step 3: Commit**

```bash
git add site/js/dashboard.js
git commit -m "feat(js): add dashboard.js — DOM bindings, CSS class swaps, MACHINE toggle"
```

---

### Task 8: Rewrite `site/js/live.js` — polling orchestrator

**Files:**
- Modify: `site/js/live.js` — complete rewrite

- [ ] **Step 1: Rewrite `site/js/live.js`**

Replace the entire file contents with:

```javascript
// live.js — polling orchestrator for the three-band live dashboard.
// Depends on: charts.js (SparkCharts), dashboard.js (SparkDashboard).
// All fetch URLs are absolute (CSP connect-src requires https://spark-api.wedd.au).
(function () {
  'use strict';

  const API         = 'https://spark-api.wedd.au/api/v1/public';
  const CACHE_KEY   = 'spark_last_known';
  const HISTORY_KEY = 'spark_history';
  const HISTORY_MAX = 120;   // 120 × 30s = 60 min local buffer
  const POLL_MS     = 30_000;
  const TIMEOUT_MS  = 5_000;

  let state = {};
  let lastSuccessMs = null;
  let _openSparklineTile = null;

  // ── localStorage helpers ─────────────────────────────────────────────────

  function loadHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; }
    catch (_) { return []; }
  }

  function saveHistory(arr) {
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(arr)); }
    catch (_) {}
  }

  function accumulate(reading) {
    let hist = loadHistory();
    // Dedup by ts — skip if this exact ts already in history
    if (hist.some(e => e.ts === reading.ts)) return;
    hist.push(reading);
    if (hist.length > HISTORY_MAX) hist = hist.slice(-HISTORY_MAX);
    saveHistory(hist);
  }

  // ── Fetch with timeout ───────────────────────────────────────────────────

  async function fetchWithTimeout(url) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const resp = await fetch(url, { signal: ctrl.signal });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    } finally {
      clearTimeout(timer);
    }
  }

  // ── Poll cycle ────────────────────────────────────────────────────────────

  async function poll() {
    const [statusR, vitalsR, sonarR, awarenessR, servicesR] = await Promise.allSettled([
      fetchWithTimeout(API + '/status'),
      fetchWithTimeout(API + '/vitals'),
      fetchWithTimeout(API + '/sonar'),
      fetchWithTimeout(API + '/awareness'),
      fetchWithTimeout(API + '/services'),
    ]);

    let anySuccess = false;

    if (statusR.status === 'fulfilled') {
      Object.assign(state, statusR.value);
      anySuccess = true;
    }
    if (vitalsR.status === 'fulfilled') {
      Object.assign(state, vitalsR.value);
      anySuccess = true;
    }
    if (sonarR.status === 'fulfilled') {
      state.sonar_cm = sonarR.value.sonar_cm != null ? sonarR.value.sonar_cm : null;
      anySuccess = true;
    }
    if (awarenessR.status === 'fulfilled') {
      const a = awarenessR.value;
      state.obi_mode             = a.obi_mode;
      state.person_present       = a.person_present;
      state.frigate_score        = a.frigate_score;
      state.ambient_level        = a.ambient_level;
      state.ambient_rms          = a.ambient_rms;
      state.weather              = a.weather;
      state.minutes_since_speech = a.minutes_since_speech;
      state.time_period          = a.time_period;
      anySuccess = true;
    }
    if (servicesR.status === 'fulfilled') {
      state.services = servicesR.value;
      anySuccess = true;
    }

    if (anySuccess) {
      lastSuccessMs = Date.now();
      accumulate({
        ts:          state.ts || new Date().toISOString(),
        cpu_pct:     state.cpu_pct     != null ? state.cpu_pct     : null,
        cpu_temp_c:  state.cpu_temp_c  != null ? state.cpu_temp_c  : null,
        ram_pct:     state.ram_pct     != null ? state.ram_pct     : null,
        battery_pct: state.battery_pct != null ? state.battery_pct : null,
        sonar_cm:    state.sonar_cm    != null ? state.sonar_cm    : null,
        ambient_rms: state.ambient_rms != null ? state.ambient_rms : null,
      });
      try {
        localStorage.setItem(CACHE_KEY, JSON.stringify(
          Object.assign({}, state, { fetchedAt: new Date().toISOString() })
        ));
      } catch (_) {}
      SparkDashboard.setOnline(true, null);
      SparkDashboard.setLastUpdated('Updated just now');
    } else {
      // All failed — fall back to cache
      const raw = localStorage.getItem(CACHE_KEY);
      if (raw) {
        try {
          const cached = JSON.parse(raw);
          Object.assign(state, cached);
          SparkDashboard.setOnline(false, cached.fetchedAt);
          SparkDashboard.setLastUpdated('Using cached data');
        } catch (_) {}
      } else {
        SparkDashboard.setOnline(false, null);
        SparkDashboard.setLastUpdated('Pi unreachable — no cached data');
      }
    }

    _updateDot();
    renderAll();
  }

  function renderAll() {
    SparkDashboard.renderPresence(state);
    SparkDashboard.renderWorld(state);
    SparkDashboard.renderMachine(state);
  }

  // ── Status dot ───────────────────────────────────────────────────────────

  function _updateDot() {
    const dot = document.getElementById('status-dot');
    if (!dot) return;
    dot.classList.remove('green', 'amber', 'red');
    if (lastSuccessMs === null) { dot.classList.add('red'); return; }
    const age = Date.now() - lastSuccessMs;
    dot.classList.add(age < 60_000 ? 'green' : age < 300_000 ? 'amber' : 'red');
  }

  // ── Waveform 2s tick ─────────────────────────────────────────────────────

  function tickWaveform() {
    const canvas = document.getElementById('waveform-canvas');
    if (canvas) SparkCharts.drawWaveform(canvas, state.ambient_rms || 0);
  }

  // ── Sparklines ───────────────────────────────────────────────────────────

  function _mergeHistory(remote) {
    const local = loadHistory();
    const byTs = {};
    for (const e of [...local, ...remote]) byTs[e.ts] = e;
    return Object.values(byTs).sort((a, b) => a.ts < b.ts ? -1 : 1);
  }

  async function openSparkline(tile) {
    const field = tile.dataset.sparkline;
    if (!field) return;

    if (_openSparklineTile === tile.id) {
      _closeSparkline(tile);
      return;
    }
    if (_openSparklineTile) {
      const prev = document.getElementById(_openSparklineTile);
      if (prev) _closeSparkline(prev);
    }
    _openSparklineTile = tile.id;

    let remote = [];
    try { remote = await fetchWithTimeout(API + '/history'); } catch (_) {}

    const points = _mergeHistory(remote).slice(-60);

    let wrap = tile.querySelector('.sparkline-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'sparkline-wrap';

      const canvas = document.createElement('canvas');
      canvas.className = 'sparkline-canvas';
      canvas.width = (tile.offsetWidth || 160) - 20;
      canvas.height = 40;

      const lbl = document.createElement('div');
      lbl.className = 'sparkline-label';

      wrap.appendChild(canvas);
      wrap.appendChild(lbl);
      tile.appendChild(wrap);
    }

    const canvas = wrap.querySelector('canvas');
    const lbl = wrap.querySelector('.sparkline-label');

    if (points.length < 2) {
      lbl.textContent = 'no history yet';
      if (canvas) canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
    } else {
      SparkCharts.drawSparkline(canvas, points, field);
      lbl.textContent = 'last ' + Math.round(points.length * 0.5) + ' min';
    }
  }

  function _closeSparkline(tile) {
    const wrap = tile.querySelector('.sparkline-wrap');
    if (wrap) wrap.parentNode.removeChild(wrap);
    if (_openSparklineTile === tile.id) _openSparklineTile = null;
  }

  function initSparklines() {
    document.querySelectorAll('[data-sparkline]').forEach(tile => {
      tile.addEventListener('click', () => openSparkline(tile));
    });
  }

  // ── Hydrate from cache (zero-flash on load) ───────────────────────────────

  function hydrateFromCache() {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return;
    try { Object.assign(state, JSON.parse(raw)); renderAll(); }
    catch (_) {}
  }

  // ── Init ─────────────────────────────────────────────────────────────────

  SparkDashboard.initToggle();
  initSparklines();
  hydrateFromCache();
  poll();
  setInterval(poll, POLL_MS);
  setInterval(tickWaveform, 2_000);
  setInterval(_updateDot, 10_000);

})();
```

- [ ] **Step 2: End-to-end manual verification checklist**

With `bin/px-api-server` running on the Pi (and Cloudflare tunnel active), open `https://spark.wedd.au`:

- [ ] **PRESENCE**: Mood pulse visible with CSS animation; `obi_mode` line appears; last thought quoted; proximity arc drawn in SVG
- [ ] **WORLD**: Waveform bars animate every 2s independently; weather strip shows or hides correctly; time updates each poll
- [ ] **MACHINE toggle**: Starts hidden; "show internals ↓" reveals it; persists on reload via `localStorage`
- [ ] **Metric tiles**: CPU/RAM/Battery bars fill; CPU temp gauge arc drawn; disk % shown; services dots listed
- [ ] **Sparklines**: Click CPU tile → canvas appears; click again → closes; clicking a second closes the first; "no history yet" when `spark_history` empty
- [ ] **Offline**: Kill `px-api-server`; PRESENCE band goes hollow; cached data shown with banner
- [ ] **CSP**: DevTools console zero CSP violations; no blocked fetch requests
- [ ] **Both themes**: `data-theme="dark"` section renders with dark overrides

- [ ] **Step 3: Commit**

```bash
git add site/js/live.js
git commit -m "feat(js): rewrite live.js — 5-endpoint poll, spark_history, sparklines, offline"
```

---

## Post-implementation: Full test run

- [ ] **Run full non-hardware test suite**

```bash
source .venv/bin/activate
python -m pytest -m "not live" -v 2>&1 | tail -20
```

Expected: All non-hardware tests pass.

- [ ] **Run public API tests specifically**

```bash
python -m pytest tests/test_public_api.py -v 2>&1 | tail -15
```

Expected: All tests pass (3 new test classes: TestPublicAwareness, TestPublicHistory, TestPublicServices).
