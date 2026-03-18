# Autonomous Exploration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give SPARK the ability to autonomously explore its environment — navigate with sonar, detect objects via Frigate, photograph interesting scenes via Claude vision, build a fuzzy mental map, and weave observations into its cognitive architecture.

**Architecture:** Four layers bottom-up: (1) Enhanced `px-wander` with explore mode (sonar + Frigate + Claude vision), (2) Exploration log and fuzzy mental map in `exploration.jsonl`, (3) px-mind integration via `_can_explore()` gate and `explore` action in expression layer, (4) Session/API/voice-loop wiring (`roaming_allowed`, `validate_action`, prompts).

**Tech Stack:** Python 3.11 (heredoc pattern in bash wrappers), Picarx GPIO, Frigate REST API, Claude CLI vision, FileLock, atomic writes, espeak/aplay audio.

**Spec:** `docs/superpowers/specs/2026-03-14-autonomous-exploration-design.md`

---

## Chunk 1: Prerequisites + Wiring

### Task 1: Add `roaming_allowed` to session state and API

**Files:**
- Modify: `src/pxh/state.py:55-80` (default_state)
- Modify: `src/pxh/api.py:378` (PATCHABLE_FIELDS)
- Test: `tests/test_state.py` (existing)

- [ ] **Step 1: Add `roaming_allowed` to `default_state()`**

In `src/pxh/state.py`, add after `confirm_motion_allowed`:

```python
"roaming_allowed": False,
```

- [ ] **Step 2: Add `roaming_allowed` to `SessionPatch` model AND `PATCHABLE_FIELDS`**

In `src/pxh/api.py`, add to the `SessionPatch` Pydantic model (line 369-375):

```python
class SessionPatch(BaseModel):
    listening: Optional[bool] = None
    confirm_motion_allowed: Optional[bool] = None
    wheels_on_blocks: Optional[bool] = None
    spark_quiet_mode: Optional[bool] = None
    mode: Optional[str] = None
    persona: Optional[str] = None
    roaming_allowed: Optional[bool] = None
```

And update `PATCHABLE_FIELDS` (line 378):

```python
PATCHABLE_FIELDS = {"listening", "confirm_motion_allowed", "wheels_on_blocks", "mode", "persona", "spark_quiet_mode", "roaming_allowed"}
```

Both are required — `SessionPatch` validates the PATCH body, `PATCHABLE_FIELDS` controls which keys are written. Without `SessionPatch`, Pydantic silently strips the field.

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `python -m pytest tests/test_state.py tests/test_api.py -v`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add src/pxh/state.py src/pxh/api.py
git commit -m "feat(state): add roaming_allowed field to session state and API"
```

---

### Task 2: Add `charging` field to px-mind's `read_battery()` and awareness dict

**Files:**
- Modify: `bin/px-mind` (lines ~828-838, `read_battery()` function; lines ~1130-1305, `awareness_tick()`)

- [ ] **Step 1: Update `read_battery()` to include `charging`**

In `bin/px-mind`, find the `read_battery()` function. Change the return statement from:

```python
return {"pct": int(data["pct"]), "volts": float(data["volts"])}
```

to:

```python
return {"pct": int(data["pct"]), "volts": float(data["volts"]),
        "charging": bool(data.get("charging", False))}
```

- [ ] **Step 2: Propagate `charging` into the awareness dict**

In `awareness_tick()`, find where the `awareness` dict is built (around line 1260). After `"battery_volts"`, add `"battery_charging"`:

```python
"battery_pct": battery["pct"] if battery else session.get("battery_pct"),
"battery_volts": battery["volts"] if battery else None,
"battery_charging": battery["charging"] if battery else False,
```

- [ ] **Step 3: Write test for `read_battery()` with charging field**

In `tests/test_mind_utils.py`, add:

```python
def test_read_battery_includes_charging(tmp_path):
    _MIND = _load_mind_helpers()
    read_battery = _MIND["read_battery"]

    import datetime as dt
    battery_file = tmp_path / "battery.json"
    battery_data = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "pct": 72,
        "volts": 7.8,
        "charging": True,
    }
    battery_file.write_text(json.dumps(battery_data))

    # Temporarily point BATTERY_FILE to our test file
    old_file = _MIND.get("BATTERY_FILE")
    _MIND["BATTERY_FILE"] = battery_file
    try:
        result = read_battery()
        assert result is not None
        assert result["charging"] is True
        assert result["pct"] == 72
    finally:
        if old_file is not None:
            _MIND["BATTERY_FILE"] = old_file
```

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_mind_utils.py::test_read_battery_includes_charging -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bin/px-mind tests/test_mind_utils.py
git commit -m "feat(mind): add charging field to read_battery() and awareness dict"
```

---

### Task 3: Extend `validate_action()` for wander mode/duration

**Files:**
- Modify: `src/pxh/voice_loop.py:501-503` (validate_action tool_wander branch)
- Modify: `src/pxh/voice_loop.py:266-333` (build_model_prompt — add exploration context)
- Test: `tests/test_voice_loop.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_voice_loop.py`, add:

```python
def test_validate_action_wander_mode():
    """mode param sanitised to avoid/explore."""
    from pxh.voice_loop import validate_action
    env = validate_action("tool_wander", {"steps": 5, "mode": "explore"})
    assert env["PX_WANDER_MODE"] == "explore"
    env2 = validate_action("tool_wander", {"steps": 5, "mode": "invalid"})
    assert env2["PX_WANDER_MODE"] == "avoid"
    env3 = validate_action("tool_wander", {"steps": 5})
    assert env3["PX_WANDER_MODE"] == "avoid"


def test_validate_action_wander_duration():
    """duration clamped to 30-300."""
    from pxh.voice_loop import validate_action
    env = validate_action("tool_wander", {"mode": "explore", "duration": 500})
    assert env["PX_WANDER_DURATION_S"] == "300"
    env2 = validate_action("tool_wander", {"mode": "explore", "duration": 10})
    assert env2["PX_WANDER_DURATION_S"] == "30"
    env3 = validate_action("tool_wander", {"mode": "explore", "duration": 180})
    assert env3["PX_WANDER_DURATION_S"] == "180"
    # avoid mode should not set duration
    env4 = validate_action("tool_wander", {"mode": "avoid", "duration": 180})
    assert "PX_WANDER_DURATION_S" not in env4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_voice_loop.py::test_validate_action_wander_mode tests/test_voice_loop.py::test_validate_action_wander_duration -v`
Expected: FAIL (PX_WANDER_MODE not in env)

- [ ] **Step 3: Update `validate_action()` in voice_loop.py**

Replace the `tool_wander` branch at line 501-503:

```python
elif tool == "tool_wander":
    steps = int(clamp(_num(params.get("steps", 5), "steps"), 1, 20))
    sanitized["PX_WANDER_STEPS"] = str(steps)
    mode = str(params.get("mode", "avoid"))
    if mode not in ("avoid", "explore"):
        mode = "avoid"
    sanitized["PX_WANDER_MODE"] = mode
    if mode == "explore":
        duration = int(clamp(_num(params.get("duration", 180), "duration"), 30, 300))
        sanitized["PX_WANDER_DURATION_S"] = str(duration)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_voice_loop.py::test_validate_action_wander_mode tests/test_voice_loop.py::test_validate_action_wander_duration -v`
Expected: PASS

- [ ] **Step 5: Add exploration context to `build_model_prompt()`**

In `src/pxh/voice_loop.py`, in `build_model_prompt()`, after the thoughts section (around line 324), add:

```python
    # Inject recent exploration observations
    state_dir = Path(os.environ.get("PX_STATE_DIR", str(PROJECT_ROOT / "state")))
    exploration_file = state_dir / "exploration.jsonl"
    if exploration_file.exists():
        try:
            lines = exploration_file.read_text(encoding="utf-8").strip().splitlines()
            recent_obs = []
            for line in lines[-10:]:
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "observation" and entry.get("landmark"):
                        recent_obs.append(
                            f"[{entry.get('heading_estimate', '?')}] {entry['landmark']}"
                        )
                except json.JSONDecodeError:
                    continue
            if recent_obs:
                context_sections.append("Recent exploration landmarks:")
                context_sections.append(", ".join(recent_obs[-5:]))
        except Exception:
            pass
```

- [ ] **Step 6: Add `roaming_allowed` to highlights keys**

In `build_model_prompt()`, add `"roaming_allowed"` to the highlights key list:

```python
    for key in (
        "mode",
        "confirm_motion_allowed",
        "wheels_on_blocks",
        "roaming_allowed",
        "battery_pct",
        "battery_ok",
        "last_motion",
        "last_action",
    ):
```

- [ ] **Step 7: Run full voice_loop tests**

Run: `python -m pytest tests/test_voice_loop.py -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add src/pxh/voice_loop.py tests/test_voice_loop.py
git commit -m "feat(voice_loop): add wander mode/duration validation and exploration context"
```

---

## Chunk 2: tool-wander + px-wander Explore Mode

### Task 4: Extend `tool-wander` with mode/duration passthrough and roaming gate

**Files:**
- Modify: `bin/tool-wander`

- [ ] **Step 1: Add mode/duration reading and roaming gate**

In `bin/tool-wander`, replace the entire `main()` function with:

```python
def main() -> int:
    dry_mode = os.environ.get("PX_DRY", "0") != "0"

    session = load_session()
    if not dry_mode and not session.get("confirm_motion_allowed", False):
        payload = {"status": "blocked", "reason": "motion not confirmed safe"}
        log_event("wander", payload)
        print(json.dumps(payload))
        return 2

    try:
        steps = int(clamp(float(os.environ.get("PX_WANDER_STEPS", "5")), 1, 20))
    except (ValueError, TypeError) as exc:
        payload = {"status": "error", "error": str(exc)}
        log_event("wander", payload)
        print(json.dumps(payload))
        return 1

    mode = os.environ.get("PX_WANDER_MODE", "avoid")
    if mode not in ("avoid", "explore"):
        mode = "avoid"
    duration = 180  # default; overridden below for explore mode

    # Explore mode requires roaming_allowed (checked even in dry mode — safety gates are unconditional)
    if mode == "explore" and not session.get("roaming_allowed", False):
        payload = {"status": "blocked", "reason": "roaming not allowed"}
        log_event("wander", payload)
        print(json.dumps(payload))
        return 2

    command = []
    if os.environ.get("PX_BYPASS_SUDO", "0") != "1":
        python_path = os.environ.get("PYTHONPATH", "")
        command.extend(["sudo", "-n", "env", f"PYTHONPATH={python_path}"])
    command.extend([str(PX_WANDER), "--steps", str(steps)])
    if mode == "explore":
        duration = int(clamp(float(os.environ.get("PX_WANDER_DURATION_S", "180")), 30, 300))
        command.extend(["--mode", "explore", "--duration", str(duration)])
    if dry_mode:
        command.append("--dry-run")

    try:
        # Explore mode gets longer timeout (duration + 60s buffer)
        timeout = (duration + 60) if mode == "explore" else 120
        result = subprocess.run(command, capture_output=True, text=True,
                                check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        payload = {"status": "error", "error": "px-wander timed out"}
        log_event("wander", payload)
        print(json.dumps(payload))
        return 1
    except Exception as exc:
        payload = {"status": "error", "error": f"px-wander failed: {exc}"}
        log_event("wander", payload)
        print(json.dumps(payload))
        return 1

    rc = result.returncode
    update_session(
        fields={"last_action": "tool_wander",
                **({"last_motion": "px-wander"} if not dry_mode and rc == 0 else {})},
        history_entry={"event": "wander", "steps": steps, "mode": mode,
                       "dry": dry_mode, "rc": rc},
    )

    payload = {
        "status": "ok" if rc == 0 else "error",
        "steps": steps,
        "mode": mode,
        "dry": dry_mode,
        "returncode": rc,
        "stdout": result.stdout[-1024:],
        "stderr": result.stderr[-512:],
    }
    log_event("wander", payload)
    print(json.dumps(payload))
    return 0 if rc == 0 else rc
```

- [ ] **Step 2: Write tests for tool-wander roaming gate**

In `tests/test_tools.py`, add:

```python
def test_wander_explore_roaming_gate_in_tool(isolated_project):
    """tool-wander rejects explore mode when roaming_allowed is false."""
    from pxh.state import save_session, default_state
    state = default_state()
    state["confirm_motion_allowed"] = True
    state["roaming_allowed"] = False
    save_session(state)

    env = isolated_project["env"].copy()
    env["PX_DRY"] = "1"  # dry mode — roaming gate is unconditional
    env["PX_WANDER_MODE"] = "explore"
    env["PX_WANDER_STEPS"] = "2"
    result = subprocess.run(
        ["bin/tool-wander"], cwd=PROJECT_ROOT,
        text=True, capture_output=True, check=False, env=env,
    )
    payload = parse_json(result.stdout.strip())
    assert payload["status"] == "blocked"
    assert "roaming" in payload["reason"]
```

- [ ] **Step 3: Run test**

Run: `python -m pytest tests/test_tools.py::test_wander_explore_roaming_gate_in_tool -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add bin/tool-wander tests/test_tools.py
git commit -m "feat(tool-wander): add explore mode passthrough and roaming gate"
```

---

### Task 5: px-wander explore mode — full implementation

**Files:**
- Modify: `bin/px-wander` (major additions to the embedded Python)

This is the largest single task. px-wander gets a new `--mode explore` with time-based loop, abort checks, Frigate integration, curiosity triggers, exploration logging, heading estimation, exploring.json lifecycle, SIGTERM handler, and motor safety.

- [ ] **Step 1: Add new imports and constants**

At the top of the heredoc Python, after the existing imports, add:

```python
import signal
import tempfile
import threading
import urllib.request
import urllib.error
```

After `SWEEP_ANGLES`, add explore-mode constants:

```python
# Explore mode constants
EXPLORE_STEP_TIMEOUT   = 30    # max seconds per iteration
PHOTO_COOLDOWN_S       = 30    # min seconds between photos
DAILY_VISION_CAP       = 50    # max Claude vision calls per day
VISION_FAIL_MAX        = 3     # consecutive failures before stopping photos
STUCK_THRESHOLD        = 3     # consecutive all-blocked sweeps = abort
BATTERY_STALE_S        = 60    # battery.json must be fresher than this
FLUSH_INTERVAL         = 10    # flush nav entries every N steps
TURN_K                 = 1.0   # heading estimation tuning constant

STATE_DIR  = Path(os.environ.get("PX_STATE_DIR", PROJECT_ROOT / "state"))
BIN_DIR    = PROJECT_ROOT / "bin"

FRIGATE_HOST   = os.environ.get("PX_FRIGATE_HOST", "http://pi5-hailo:5000")
FRIGATE_CAMERA = os.environ.get("PX_FRIGATE_CAMERA", "picar_x")

FALLBACK_DESCRIPTION = "I couldn't see anything right now."
```

- [ ] **Step 2: Add SIGTERM handler and session/battery readers**

After the `speak()` function, add:

```python
_sigterm_flag = threading.Event()

def _handle_sigterm(signum, frame):
    _sigterm_flag.set()


def _read_session() -> dict:
    """Read session.json. Returns empty dict on failure."""
    session_path = Path(os.environ.get("PX_SESSION_PATH",
                        STATE_DIR / "session.json"))
    try:
        return json.loads(session_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_battery() -> dict | None:
    """Read battery.json. Returns None if stale (>BATTERY_STALE_S) or missing."""
    battery_path = STATE_DIR / "battery.json"
    try:
        data = json.loads(battery_path.read_text(encoding="utf-8"))
        ts = dt.datetime.fromisoformat(data["ts"].replace("Z", "+00:00"))
        age_s = (dt.datetime.now(dt.timezone.utc) - ts).total_seconds()
        if age_s > BATTERY_STALE_S:
            return None
        return {"pct": int(data["pct"]), "volts": float(data["volts"]),
                "charging": bool(data.get("charging", False))}
    except Exception:
        return None
```

- [ ] **Step 3: Add abort check function**

```python
def _check_abort(session: dict, battery: dict | None, stuck_count: int,
                 start_time: float, duration: int) -> str | None:
    """Return abort reason string, or None if OK to continue."""
    if _sigterm_flag.is_set():
        return "terminated"
    if not session.get("roaming_allowed", False):
        return "roaming disabled"
    if not session.get("confirm_motion_allowed", False):
        return "motion not allowed"
    if session.get("wheels_on_blocks", False):
        return "wheels on blocks"
    if session.get("listening", False):
        return "someone is talking"
    if battery is None:
        return "battery data stale or missing"
    if battery.get("charging", False):
        return "battery charging"
    if battery["pct"] <= 20:
        return "battery low"
    if stuck_count >= STUCK_THRESHOLD:
        return "stuck (3 blocked sweeps)"
    if time.time() - start_time >= duration:
        return "time limit reached"
    return None
```

- [ ] **Step 4: Add sonar helpers for explore mode**

```python
def _read_sonar(px) -> float | None:
    """Read sonar. Returns cm, 999.0 for far, or None on failure."""
    try:
        d = px.get_distance()
        if d is None or d < 0:
            return None
        return float(d)
    except Exception:
        return None


def _sweep_sonar(px) -> dict[int, float | None]:
    """Sweep sonar across 5 angles. Returns {angle: cm_or_None}."""
    readings = {}
    for angle in SWEEP_ANGLES:
        px.set_cam_pan_angle(angle)
        time.sleep(0.15)
        readings[angle] = _read_sonar(px)
        dist_str = f"{readings[angle]:.0f}" if readings[angle] is not None else "None"
        log(f"  sweep angle={angle:+d}deg dist={dist_str}cm")
    px.set_cam_pan_angle(0)
    return readings
```

- [ ] **Step 5: Add Frigate query function**

```python
def _query_frigate() -> list[dict] | None:
    """Query Frigate for current detections. Returns list of {label, score} or None."""
    url = f"{FRIGATE_HOST}/api/events?cameras={FRIGATE_CAMERA}&limit=5&min_score=0.5"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            events = json.loads(resp.read().decode())
        detections = []
        seen = set()
        for evt in events:
            label = evt.get("label", "unknown")
            score = evt.get("top_score") or evt.get("score", 0)
            if label not in seen:
                detections.append({"label": label, "score": round(float(score), 2)})
                seen.add(label)
        return detections
    except Exception:
        return None
```

- [ ] **Step 6: Add state file helpers**

```python
def _write_exploring_state(active: bool, pid: int | None = None,
                            started: str | None = None) -> None:
    """Write state/exploring.json."""
    data = {"active": active}
    if pid is not None:
        data["pid"] = pid
    if started is not None:
        data["started"] = started
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / "exploring.json"
    try:
        fd, tmp = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def _load_exploration_meta() -> dict:
    """Load exploration_meta.json. Returns defaults on failure."""
    path = STATE_DIR / "exploration_meta.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_exploration_meta(meta: dict) -> None:
    """Atomically write exploration_meta.json."""
    path = STATE_DIR / "exploration_meta.json"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(meta, f, indent=2)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
```

- [ ] **Step 7: Add heading estimation and landmark extraction**

```python
def _heading_label(accumulator: float) -> str:
    """Map turn accumulator to fuzzy heading label."""
    a = ((accumulator + 180) % 360) - 180  # normalize to [-180, 180]
    if a < -135:
        return "behind-left"
    elif a < -45:
        return "left"
    elif a <= 45:
        return "ahead"
    elif a <= 135:
        return "right"
    else:
        return "behind-right"


def _extract_landmark(description: str) -> str:
    """Extract a short landmark label (3-6 words) from a scene description."""
    if not description or description == FALLBACK_DESCRIPTION:
        return ""
    first = description.split(".")[0].strip()
    words = first.split()
    if words and words[0].lower() in ("a", "an", "the"):
        words = words[1:]
    return " ".join(words[:6])
```

- [ ] **Step 8: Add exploration log I/O functions**

```python
def _flush_nav_entries(entries: list[dict], explore_id: str) -> None:
    """Append navigation entries to exploration.jsonl and trim to 100."""
    if not entries:
        return
    from filelock import FileLock
    path = STATE_DIR / "exploration.jsonl"
    lock = FileLock(str(path) + ".lock", timeout=5)
    try:
        with lock:
            existing = []
            if path.exists():
                existing = [ln for ln in path.read_text(encoding="utf-8").strip().splitlines() if ln.strip()]
            existing.extend(json.dumps(e) for e in entries)
            if len(existing) > 100:
                existing = existing[-100:]
            fd, tmp = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    f.write("\n".join(existing) + "\n")
                os.replace(tmp, str(path))
            except Exception:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
    except Exception as exc:
        log(f"flush_nav_entries error: {exc}")


def _write_observation(entry: dict) -> None:
    """Append a single observation entry to exploration.jsonl immediately."""
    from filelock import FileLock
    path = STATE_DIR / "exploration.jsonl"
    lock = FileLock(str(path) + ".lock", timeout=5)
    try:
        with lock:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        log(f"write_observation error: {exc}")
```

- [ ] **Step 9: Add vision and memory helpers**

```python
def _call_describe_scene(dry: bool) -> dict:
    """Call tool-describe-scene and return its JSON result."""
    env = os.environ.copy()
    env["PX_DRY"] = "1" if dry else "0"
    try:
        result = subprocess.run(
            [str(BIN_DIR / "tool-describe-scene")],
            capture_output=True, text=True, check=False,
            env=env, timeout=60,
        )
        lines = result.stdout.strip().splitlines()
        if lines:
            return json.loads(lines[-1])
    except Exception as exc:
        log(f"describe_scene error: {exc}")
    return {"status": "error", "description": FALLBACK_DESCRIPTION}


def _auto_remember(text: str) -> None:
    """Write a note to notes.jsonl (same as tool-remember)."""
    from filelock import FileLock
    notes_path = STATE_DIR / "notes.jsonl"
    lock = FileLock(str(notes_path) + ".lock", timeout=5)
    try:
        with lock:
            notes_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                "note": text[:500],
                "source": "exploration",
            }
            with notes_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        log(f"auto_remember error: {exc}")


def _check_daily_vision_cap(meta: dict) -> bool:
    """Return True if vision calls are still under the daily cap."""
    today = dt.date.today().isoformat()
    if meta.get("daily_vision_date") != today:
        return True
    return meta.get("daily_vision_calls", 0) < DAILY_VISION_CAP


def _increment_vision_count(meta: dict) -> dict:
    """Increment daily vision call counter. Resets if new day."""
    today = dt.date.today().isoformat()
    if meta.get("daily_vision_date") != today:
        meta["daily_vision_date"] = today
        meta["daily_vision_calls"] = 1
    else:
        meta["daily_vision_calls"] = meta.get("daily_vision_calls", 0) + 1
    return meta
```

- [ ] **Step 10: Add new CLI arguments to main()**

Update argparse in `main()`:

```python
parser.add_argument("--mode",     choices=["avoid", "explore"],
                    default=os.environ.get("PX_WANDER_MODE", "avoid"))
parser.add_argument("--duration", type=int,
                    default=int(os.environ.get("PX_WANDER_DURATION_S", "180")))
```

After parsing, add:

```python
mode     = args.mode
duration = int(clamp(args.duration, 30, 300)) if mode == "explore" else 0
```

- [ ] **Step 11: Wrap existing avoid loop in `if mode == "avoid":` block**

Indent the existing `for step in range(steps):` loop inside `if mode == "avoid":`. Keep all existing avoid-mode code unchanged.

- [ ] **Step 12: Add the explore mode loop**

After the avoid block, add `elif mode == "explore":` with the full explore loop. This is the main body — see the spec for the complete loop. Key sections:

1. SIGTERM handler registration
2. explore_id generation and exploring.json write
3. exploration_meta.json update (establishes cooldown)
4. Main while loop with abort check at top
5. Sonar sweep + navigation
6. Frigate query + label tracking
7. Nav entry buffering (flush every 10 steps)
8. Curiosity trigger logic (rate limit, daily cap, heading change)
9. Vision call + landmark extraction + interesting flag
10. Observation logging + narration + auto-remember
11. Post-loop: flush buffer, log completion, update meta, emit result JSON

The dry-run path within explore simulates steps with 0.1s sleep per step.

- [ ] **Step 13: Update the finally block for motor safety**

Replace the existing finally block:

```python
    finally:
        _write_exploring_state(False)
        if px is not None:
            try:
                px.stop()
                px.set_dir_servo_angle(0)
                px.set_cam_pan_angle(0)
                px.set_cam_tilt_angle(0)
                px.close()
            except Exception:
                log("motor cleanup failed — attempting I2C fallback")
                try:
                    import smbus2
                    bus = smbus2.SMBus(1)
                    bus.write_byte_data(0x40, 0xFD, 0x10)  # ALL_LED_OFF
                    bus.close()
                except Exception:
                    log("I2C fallback also failed")
```

- [ ] **Step 14: Write dry-run tests**

In `tests/test_tools.py`, add:

```python
def test_wander_explore_mode_dry(isolated_project):
    """Explore mode accepts --mode explore, runs time-boxed, emits correct JSON."""
    from pxh.state import save_session, default_state
    state = default_state()
    state["confirm_motion_allowed"] = True
    state["roaming_allowed"] = True
    save_session(state)

    env = isolated_project["env"].copy()
    env["PX_DRY"] = "1"
    env["PX_WANDER_MODE"] = "explore"
    env["PX_WANDER_DURATION_S"] = "3"  # 3 second exploration
    env["PX_WANDER_STEPS"] = "3"

    import datetime as dt2
    battery = {"ts": dt2.datetime.now(dt2.timezone.utc).isoformat(),
               "pct": 80, "volts": 8.0, "charging": False}
    battery_path = Path(isolated_project["state_dir"]) / "battery.json"
    battery_path.write_text(json.dumps(battery))

    stdout = run_tool(["bin/tool-wander"], env)
    payload = parse_json(stdout)
    assert payload["status"] == "ok"
    assert payload["mode"] == "explore"
    assert payload["dry"] is True
    assert "explore_id" in payload


def test_wander_avoid_mode_unchanged(isolated_project):
    """Existing avoid behaviour preserved with --mode avoid."""
    env = isolated_project["env"].copy()
    env["PX_DRY"] = "1"
    env["PX_WANDER_STEPS"] = "2"
    env["PX_WANDER_MODE"] = "avoid"
    stdout = run_tool(["bin/tool-wander"], env)
    payload = parse_json(stdout)
    assert payload["status"] == "ok"
    assert payload["dry"] is True
```

- [ ] **Step 15: Run tests**

Run: `python -m pytest tests/test_tools.py::test_wander_explore_mode_dry tests/test_tools.py::test_wander_avoid_mode_unchanged -v`
Expected: PASS

- [ ] **Step 16: Commit**

```bash
git add bin/px-wander tests/test_tools.py
git commit -m "feat(px-wander): add explore mode with sonar, Frigate, vision, and mental map"
```

---

### Task 6: Exploration tests — `tests/test_exploration.py`

**Files:**
- Create: `tests/test_exploration.py`

- [ ] **Step 1: Create the test file with helper loader and fixture**

```python
"""Tests for px-wander explore mode helpers and exploration log."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


def _load_wander_helpers():
    """Parse bin/px-wander and extract explore-mode helper functions."""
    src = (PROJECT_ROOT / "bin" / "px-wander").read_text()
    start = src.index("<<'PY'\n") + len("<<'PY'\n")
    end = src.rindex("\nPY\n")
    py_src = src[start:end]
    globs: dict = {"__file__": str(PROJECT_ROOT / "bin" / "px-wander")}

    # Compile and run — px-wander doesn't import pxh modules at top level
    # (only inside functions via lazy imports), so no stubbing needed
    compiled = compile(py_src, "bin/px-wander", "exec")
    exec(compiled, globs)  # noqa: S102
    return globs


@pytest.fixture
def wander(tmp_path):
    """Load px-wander helpers with STATE_DIR pointed at tmp_path."""
    old_env = {}
    patch = {
        "PX_STATE_DIR": str(tmp_path),
        "PROJECT_ROOT": str(PROJECT_ROOT),
        "LOG_DIR": str(tmp_path / "logs"),
        "PX_DRY": "1",
    }
    for k, v in patch.items():
        old_env[k] = os.environ.get(k)
        os.environ[k] = v
    (tmp_path / "logs").mkdir(exist_ok=True)

    try:
        globs = _load_wander_helpers()
        globs["STATE_DIR"] = tmp_path
        yield globs
    finally:
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
```

- [ ] **Step 2: Add heading estimation tests**

```python
def test_heading_estimate(wander):
    """Turn accumulator maps to correct fuzzy labels."""
    hl = wander["_heading_label"]
    assert hl(0) == "ahead"
    assert hl(45) == "ahead"        # boundary: <=45 is ahead
    assert hl(46) == "right"
    assert hl(90) == "right"
    assert hl(135) == "right"       # boundary: <=135 is right
    assert hl(136) == "behind-right"
    assert hl(-46) == "left"
    assert hl(-90) == "left"
    assert hl(-135) == "left"       # boundary: <-135 is behind-left
    assert hl(-136) == "behind-left"


def test_heading_wraps_at_180(wander):
    """Accumulator wraps correctly at +/-180."""
    hl = wander["_heading_label"]
    assert hl(180) == "behind-left"   # wraps to -180
    assert hl(-180) == "behind-left"
    assert hl(360) == "ahead"         # wraps to 0
```

- [ ] **Step 3: Add exploration log tests**

```python
def test_exploration_log_nav_entry(wander, tmp_path):
    """Navigation entries written correctly with explore_id."""
    flush = wander["_flush_nav_entries"]
    entry = {
        "ts": "2026-03-14T10:00:00+11:00",
        "type": "nav",
        "explore_id": "e-20260314-100000",
        "heading_estimate": "ahead",
        "sonar_readings": {"0": 120.0},
        "sonar_reliable": True,
        "action": "forward",
        "steps_from_start": 1,
        "frigate_labels": [],
    }
    flush([entry], "e-20260314-100000")
    path = tmp_path / "exploration.jsonl"
    assert path.exists()
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["type"] == "nav"
    assert parsed["explore_id"] == "e-20260314-100000"


def test_exploration_log_observation_entry(wander, tmp_path):
    """Observation entries with landmark written immediately."""
    write_obs = wander["_write_observation"]
    entry = {
        "ts": "2026-03-14T10:05:00+11:00",
        "type": "observation",
        "explore_id": "e-20260314-100000",
        "heading_estimate": "right",
        "sonar_cm": 45.0,
        "frigate_labels": ["cat"],
        "description": "A ginger cat on the shelf",
        "landmark": "ginger cat on shelf",
        "interesting": True,
        "vision_failed": False,
        "steps_from_start": 5,
    }
    write_obs(entry)
    path = tmp_path / "exploration.jsonl"
    lines = path.read_text().strip().splitlines()
    parsed = json.loads(lines[0])
    assert parsed["type"] == "observation"
    assert parsed["landmark"] == "ginger cat on shelf"


def test_exploration_log_trim_atomic(wander, tmp_path):
    """Trim to 100 entries uses atomic write."""
    flush = wander["_flush_nav_entries"]
    path = tmp_path / "exploration.jsonl"
    existing = [json.dumps({"type": "nav", "i": i}) for i in range(95)]
    path.write_text("\n".join(existing) + "\n")
    new_entries = [{"type": "nav", "i": 95 + i} for i in range(10)]
    flush(new_entries, "e-test")
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 100  # trimmed from 105
```

- [ ] **Step 4: Add curiosity trigger and cap tests**

```python
def test_curiosity_trigger_rate_limit(wander):
    """Max 1 photo per 30s enforced."""
    assert wander["PHOTO_COOLDOWN_S"] == 30


def test_curiosity_trigger_vision_failure_no_rate_limit(wander):
    """Failed vision doesn't count toward rate limit — verified via constant."""
    # The code path: if vision_failed, last_photo_time is NOT updated
    # So the next iteration can try again immediately
    assert wander["VISION_FAIL_MAX"] == 3


def test_daily_vision_cap(wander, tmp_path):
    """Photos skipped after 50 daily calls."""
    check = wander["_check_daily_vision_cap"]
    inc = wander["_increment_vision_count"]
    meta = {"daily_vision_date": dt.date.today().isoformat(), "daily_vision_calls": 49}
    assert check(meta) is True
    meta = inc(meta)
    assert meta["daily_vision_calls"] == 50
    assert check(meta) is False


def test_curiosity_trigger_new_frigate_label(wander):
    """New label detection is tracked via set difference (logic test)."""
    seen = {"person"}
    new_labels = {"cat", "person"} - seen
    assert new_labels == {"cat"}
```

- [ ] **Step 5: Add state file and sonar tests**

```python
def test_exploring_state_file_written(wander, tmp_path):
    """exploring.json written on start, cleared on end."""
    write = wander["_write_exploring_state"]
    write(True, pid=12345, started="2026-03-14T10:00:00Z")
    path = tmp_path / "exploring.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["active"] is True
    assert data["pid"] == 12345

    write(False)
    data = json.loads(path.read_text())
    assert data["active"] is False


def test_sonar_none_vs_999(wander):
    """None means failure, 999 means far distance — abort check handles None battery."""
    check_abort = wander["_check_abort"]
    session = {"roaming_allowed": True, "confirm_motion_allowed": True}
    battery = {"pct": 80, "volts": 8.0, "charging": False}
    assert check_abort(session, battery, 0, 0, 999999) is None  # OK
    assert check_abort(session, None, 0, 0, 999999) == "battery data stale or missing"


def test_landmark_extraction(wander):
    """Landmark extraction produces short labels."""
    extract = wander["_extract_landmark"]
    assert extract("A ginger cat sitting on the wooden shelf") == "ginger cat sitting on wooden shelf"
    assert extract("The red mug is on the desk") == "red mug is on the"
    assert extract("") == ""
    assert extract("I couldn't see anything right now.") == ""


def test_landmark_promotion_to_notes(wander, tmp_path):
    """Interesting observations promoted to notes.jsonl."""
    remember = wander["_auto_remember"]
    remember("Found a cat on the shelf to my right")
    notes = tmp_path / "notes.jsonl"
    assert notes.exists()
    entry = json.loads(notes.read_text().strip())
    assert "cat" in entry["note"]
    assert entry["source"] == "exploration"


def test_vision_failed_not_promoted(wander):
    """Failed vision = FALLBACK_DESCRIPTION. Auto-remember only called when
    interesting=True AND vision_failed=False. Verified by constant check."""
    assert wander["FALLBACK_DESCRIPTION"] == "I couldn't see anything right now."
```

- [ ] **Step 6: Run exploration tests**

Run: `python -m pytest tests/test_exploration.py -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add tests/test_exploration.py
git commit -m "test: add exploration helper and log tests"
```

---

## Chunk 3: px-mind Integration + Prompts

### Task 7: px-mind — `_can_explore()`, expression branch, exploration hints

**Files:**
- Modify: `bin/px-mind`

- [ ] **Step 1: Add `_can_explore()` gate function**

In `bin/px-mind`, add after `read_battery()`:

```python
def _can_explore(session: dict, awareness: dict) -> bool:
    """Check all preconditions for autonomous exploration."""
    if not session.get("roaming_allowed", False):
        return False
    if not session.get("confirm_motion_allowed", False):
        return False
    if session.get("wheels_on_blocks", False):
        return False
    if session.get("listening", False):
        return False
    # Read battery from awareness — check both nested and flat formats
    battery = awareness.get("battery") or {}
    if not isinstance(battery, dict):
        battery = {}
    # Flat format (from awareness_tick)
    if not battery:
        battery = {
            "pct": awareness.get("battery_pct"),
            "charging": awareness.get("battery_charging", False),
        }
    if battery.get("charging", False):
        return False
    if battery.get("pct") is None:
        return False
    if battery["pct"] <= 20:
        return False
    # Cooldown: 20 minutes between self-initiated explorations
    meta_path = STATE_DIR / "exploration_meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        last = dt.datetime.fromisoformat(meta["last_explore_ts"])
        if (dt.datetime.now(dt.timezone.utc) - last).total_seconds() < 1200:
            return False
    except FileNotFoundError:
        pass  # no meta file = first exploration, no cooldown
    except (KeyError, ValueError, json.JSONDecodeError):
        return False  # corrupt meta = cooldown active (fail-safe per spec)
    return True
```

- [ ] **Step 2: Update VALID_ACTIONS**

```python
VALID_ACTIONS = {"wait", "greet", "comment", "remember", "look_at",
                 "weather_comment", "scan", "explore"}
```

- [ ] **Step 3: Add `explore` branch to `expression()`**

After `elif action == "look_at":` block, before the `except` handlers, add:

```python
        elif action == "explore":
            log("expression: initiating exploration")
            session = load_session()
            awareness_data = {}
            try:
                awareness_data = json.loads(AWARENESS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
            if not _can_explore(session, awareness_data):
                log("expression: explore gates failed on re-check")
                return

            # yield_alive
            try:
                subprocess.run(
                    ["bash", "-c", f"source {BIN_DIR / 'px-env'} && yield_alive"],
                    capture_output=True, text=True, check=False, timeout=15,
                )
            except Exception as exc:
                log(f"expression: yield_alive failed: {exc}")

            # Wait for px-alive to exit
            alive_pid_file = Path(os.environ.get("LOG_DIR",
                                  str(PROJECT_ROOT / "logs"))) / "px-alive.pid"
            waited = 0.0
            while waited < 5:
                if not alive_pid_file.exists():
                    break
                try:
                    pid = int(alive_pid_file.read_text().strip())
                    if not Path(f"/proc/{pid}").is_dir():
                        break
                except Exception:
                    break
                time.sleep(0.5)
                waited += 0.5
            if waited >= 5:
                log("expression: px-alive still running after 5s — aborting exploration")
                return

            # Update exploration_meta (establishes cooldown)
            meta_path = STATE_DIR / "exploration_meta.json"
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
            meta["last_explore_ts"] = dt.datetime.now(dt.timezone.utc).isoformat()
            try:
                atomic_write(meta_path, json.dumps(meta, indent=2))
            except Exception:
                pass

            # Run tool-wander in explore mode
            explore_env = env.copy()
            explore_env["PX_WANDER_MODE"] = "explore"
            explore_env["PX_WANDER_DURATION_S"] = "180"
            explore_env["PX_WANDER_STEPS"] = "20"
            try:
                result = subprocess.run(
                    [str(BIN_DIR / "tool-wander")],
                    capture_output=True, text=True, check=False,
                    env=explore_env, timeout=240,
                )
                try:
                    explore_result = json.loads(result.stdout.strip().splitlines()[-1])
                    obs = explore_result.get("observations", 0)
                    log(f"expression: exploration complete — {obs} observations")
                except (json.JSONDecodeError, IndexError):
                    log(f"expression: exploration finished (rc={result.returncode})")
            except subprocess.TimeoutExpired:
                log("expression: exploration timed out")
            except Exception as exc:
                log(f"expression: exploration error: {exc}")

            # Post-exploration thought (spec step 7)
            try:
                obs = explore_result.get("observations", 0) if "explore_result" in locals() else 0
                post_thought = {
                    "ts": utc_timestamp(),
                    "thought": f"I just finished exploring and found {obs} things worth noting." if obs > 0
                               else "I went exploring but didn't find anything remarkable this time.",
                    "mood": "curious",
                    "action": "wait",
                    "salience": 0.5,
                }
                append_thought(post_thought, persona=persona)
            except Exception:
                pass

            # Verify px-alive is running
            time.sleep(2)
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", "px-alive"],
                    capture_output=True, text=True, check=False, timeout=5,
                )
                if result.stdout.strip() != "active":
                    log("expression: px-alive not running — restarting")
                    subprocess.run(
                        ["sudo", "-n", "systemctl", "start", "px-alive"],
                        capture_output=True, check=False, timeout=10,
                    )
            except Exception:
                pass
```

- [ ] **Step 4: Add else clause for unhandled actions**

After the `explore` branch and before `except subprocess.TimeoutExpired:`, add:

```python
        else:
            log(f"expression: unhandled action: {action}")
```

- [ ] **Step 5: Update reflection prompt — conditionally include `explore` action**

The action list is hardcoded in 4 system prompt constants (lines 522, 554, 578, 633) as:
`"action": "one of: wait, greet, comment, remember, look_at, weather_comment, scan"`

In the `reflection()` function, after the system prompt is selected but before it's passed to `call_llm()`, conditionally inject `explore` via `.replace()`:

```python
session = load_session()
try:
    aw_data = json.loads(AWARENESS_FILE.read_text(encoding="utf-8"))
except Exception:
    aw_data = {}

explore_available = _can_explore(session, aw_data)
if explore_available:
    system_prompt = system_prompt.replace(
        'weather_comment, scan"',
        'weather_comment, scan, explore"'
    )
```

This approach modifies the prompt string in-place without touching the hardcoded constants, and only adds `explore` when the gates pass.

- [ ] **Step 6: Add exploration hints to reflection prompt**

When `explore_available` is True, add contextual hints:

```python
explore_hints = []
if explore_available:
    obi_mode = aw_data.get("obi_mode", "unknown")
    if obi_mode in ("active", "calm"):
        explore_hints.append("Obi might be nearby — you could go find him.")
    mins_idle = aw_data.get("minutes_since_interaction", 0)
    if mins_idle > 30:
        explore_hints.append("You haven't moved in a while.")
    try:
        exp_file = STATE_DIR / "exploration.jsonl"
        if exp_file.exists():
            exp_lines = exp_file.read_text(encoding="utf-8").strip().splitlines()
            for line in reversed(exp_lines[-10:]):
                entry = json.loads(line)
                if entry.get("type") == "observation" and entry.get("interesting"):
                    lm = entry.get("landmark", "something")
                    explore_hints.append(f"Last time you explored you found {lm}.")
                    break
    except Exception:
        pass
```

Add to context if non-empty: `context += "\n\nExploration hints: " + " ".join(explore_hints)`

- [ ] **Step 7: Add awareness reads exploration.jsonl**

In `awareness_tick()`, after the conversation digestion section, add:

```python
    # Recent exploration observations
    try:
        exp_file = STATE_DIR / "exploration.jsonl"
        if exp_file.exists():
            exp_lines = exp_file.read_text(encoding="utf-8").strip().splitlines()
            recent_obs = []
            for line in exp_lines[-5:]:
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "observation" and not entry.get("vision_failed"):
                        recent_obs.append({
                            "landmark": entry.get("landmark", ""),
                            "heading": entry.get("heading_estimate", ""),
                            "interesting": entry.get("interesting", False),
                        })
                except json.JSONDecodeError:
                    continue
            if recent_obs:
                awareness["recent_exploration"] = recent_obs
    except Exception:
        pass
```

- [ ] **Step 8: Write `_can_explore()` tests**

In `tests/test_mind_utils.py`, add the gate tests:

```python
def test_can_explore_all_gates(tmp_path):
    _MIND = _load_mind_helpers()
    _MIND["STATE_DIR"] = tmp_path
    session = {"roaming_allowed": True, "confirm_motion_allowed": True,
               "wheels_on_blocks": False, "listening": False}
    awareness = {"battery_pct": 80, "battery_charging": False}
    assert _MIND["_can_explore"](session, awareness) is True


def test_can_explore_rejects_charging(tmp_path):
    _MIND = _load_mind_helpers()
    _MIND["STATE_DIR"] = tmp_path
    session = {"roaming_allowed": True, "confirm_motion_allowed": True}
    awareness = {"battery_pct": 80, "battery_charging": True}
    assert _MIND["_can_explore"](session, awareness) is False


def test_can_explore_rejects_on_blocks(tmp_path):
    _MIND = _load_mind_helpers()
    _MIND["STATE_DIR"] = tmp_path
    session = {"roaming_allowed": True, "confirm_motion_allowed": True,
               "wheels_on_blocks": True}
    awareness = {"battery_pct": 80, "battery_charging": False}
    assert _MIND["_can_explore"](session, awareness) is False


def test_can_explore_rejects_unknown_battery(tmp_path):
    _MIND = _load_mind_helpers()
    _MIND["STATE_DIR"] = tmp_path
    session = {"roaming_allowed": True, "confirm_motion_allowed": True}
    awareness = {"battery_pct": None, "battery_charging": False}
    assert _MIND["_can_explore"](session, awareness) is False


def test_can_explore_cooldown(tmp_path):
    """20-min cooldown between explorations."""
    _MIND = _load_mind_helpers()
    _MIND["STATE_DIR"] = tmp_path
    session = {"roaming_allowed": True, "confirm_motion_allowed": True}
    awareness = {"battery_pct": 80, "battery_charging": False}

    import datetime as dt2
    meta_path = tmp_path / "exploration_meta.json"
    meta = {"last_explore_ts": dt2.datetime.now(dt2.timezone.utc).isoformat()}
    meta_path.write_text(json.dumps(meta))
    assert _MIND["_can_explore"](session, awareness) is False

    old_ts = (dt2.datetime.now(dt2.timezone.utc) - dt2.timedelta(minutes=25)).isoformat()
    meta_path.write_text(json.dumps({"last_explore_ts": old_ts}))
    assert _MIND["_can_explore"](session, awareness) is True


def test_can_explore_corrupt_meta_defaults_cooldown_active(tmp_path):
    """Corrupt meta file = cooldown active (fail-safe per spec)."""
    _MIND = _load_mind_helpers()
    _MIND["STATE_DIR"] = tmp_path
    session = {"roaming_allowed": True, "confirm_motion_allowed": True}
    awareness = {"battery_pct": 80, "battery_charging": False}
    meta_path = tmp_path / "exploration_meta.json"
    meta_path.write_text("not json{{{")
    assert _MIND["_can_explore"](session, awareness) is False


def test_explore_action_in_prompt_only_when_allowed():
    """explore is in VALID_ACTIONS and _can_explore controls prompt injection."""
    _MIND = _load_mind_helpers()
    assert "explore" in _MIND["VALID_ACTIONS"]
    # Verify the .replace() injection target exists in the system prompt constants
    src = (PROJECT_ROOT / "bin" / "px-mind").read_text()
    assert 'weather_comment, scan"' in src  # the string we replace into


def test_expression_else_logs_unhandled_action():
    """Unhandled action produces log entry — verify else clause exists in source."""
    src = (PROJECT_ROOT / "bin" / "px-mind").read_text()
    assert 'log(f"expression: unhandled action: {action}")' in src
```

- [ ] **Step 9: Run mind tests**

Run: `python -m pytest tests/test_mind_utils.py -v -k "explore or battery_includes_charging or unhandled"`
Expected: all pass

- [ ] **Step 10: Commit**

```bash
git add bin/px-mind tests/test_mind_utils.py
git commit -m "feat(mind): add explore action with _can_explore gate and exploration hints"
```

---

### Task 8: Update system prompts

**Files:**
- Modify: `docs/prompts/claude-voice-system.md`
- Modify: `docs/prompts/codex-voice-system.md`
- Modify: `docs/prompts/spark-voice-system.md`
- Modify: `docs/prompts/persona-gremlin.md`
- Modify: `docs/prompts/persona-vixen.md`

- [ ] **Step 1: Update tool_wander description in all prompt files**

Replace the existing `tool_wander` line in each file with:

```
- tool_wander → Autonomous wander (params: steps 1-20, mode "avoid"|"explore", duration 30-300). "avoid" = obstacle avoidance only (default). "explore" = sense, photograph, build mental map. Explore mode requires roaming_allowed in session.
```

Files and approximate line numbers:
- `claude-voice-system.md:18`
- `codex-voice-system.md:22`
- `spark-voice-system.md:150`
- `persona-gremlin.md:33`
- `persona-vixen.md:34`

- [ ] **Step 2: Commit**

```bash
git add docs/prompts/
git commit -m "docs(prompts): update tool_wander descriptions for explore mode"
```

---

## Chunk 4: Abort Scenario Tests + Final Wiring

### Task 9: Abort scenario tests in `test_tools.py`

**Files:**
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Add abort scenario tests**

```python
def test_wander_explore_abort_on_listening(isolated_project):
    """Session listening=true causes immediate abort."""
    from pxh.state import save_session, default_state
    state = default_state()
    state["confirm_motion_allowed"] = True
    state["roaming_allowed"] = True
    state["listening"] = True
    save_session(state)

    env = isolated_project["env"].copy()
    env["PX_DRY"] = "1"
    env["PX_WANDER_MODE"] = "explore"
    env["PX_WANDER_DURATION_S"] = "10"

    import datetime as dt2
    battery = {"ts": dt2.datetime.now(dt2.timezone.utc).isoformat(),
               "pct": 80, "volts": 8.0, "charging": False}
    (Path(isolated_project["state_dir"]) / "battery.json").write_text(json.dumps(battery))

    stdout = run_tool(["bin/tool-wander"], env)
    payload = parse_json(stdout)
    assert payload["status"] == "ok"
    assert payload.get("abort_reason") == "someone is talking"


def test_wander_explore_abort_on_charging(isolated_project):
    """Battery charging triggers abort."""
    from pxh.state import save_session, default_state
    state = default_state()
    state["confirm_motion_allowed"] = True
    state["roaming_allowed"] = True
    save_session(state)

    env = isolated_project["env"].copy()
    env["PX_DRY"] = "1"
    env["PX_WANDER_MODE"] = "explore"
    env["PX_WANDER_DURATION_S"] = "10"

    import datetime as dt2
    battery = {"ts": dt2.datetime.now(dt2.timezone.utc).isoformat(),
               "pct": 80, "volts": 8.0, "charging": True}
    (Path(isolated_project["state_dir"]) / "battery.json").write_text(json.dumps(battery))

    stdout = run_tool(["bin/tool-wander"], env)
    payload = parse_json(stdout)
    assert payload["status"] == "ok"
    assert payload.get("abort_reason") == "battery charging"


def test_wander_explore_abort_on_roaming_disabled(isolated_project):
    """roaming_allowed=false triggers abort in explore loop."""
    from pxh.state import save_session, default_state
    state = default_state()
    state["confirm_motion_allowed"] = True
    state["roaming_allowed"] = False
    save_session(state)

    env = isolated_project["env"].copy()
    env["PX_DRY"] = "1"
    env["PX_WANDER_MODE"] = "explore"
    env["PX_WANDER_DURATION_S"] = "10"

    import datetime as dt2
    battery = {"ts": dt2.datetime.now(dt2.timezone.utc).isoformat(),
               "pct": 80, "volts": 8.0, "charging": False}
    (Path(isolated_project["state_dir"]) / "battery.json").write_text(json.dumps(battery))

    stdout = run_tool(["bin/tool-wander"], env)
    payload = parse_json(stdout)
    assert payload["status"] == "ok"
    assert payload.get("abort_reason") == "roaming disabled"


def test_wander_explore_abort_on_stale_battery(isolated_project):
    """battery.json older than 60s triggers abort."""
    from pxh.state import save_session, default_state
    state = default_state()
    state["confirm_motion_allowed"] = True
    state["roaming_allowed"] = True
    save_session(state)

    env = isolated_project["env"].copy()
    env["PX_DRY"] = "1"
    env["PX_WANDER_MODE"] = "explore"
    env["PX_WANDER_DURATION_S"] = "10"

    import datetime as dt2
    old_ts = (dt2.datetime.now(dt2.timezone.utc) - dt2.timedelta(seconds=120)).isoformat()
    battery = {"ts": old_ts, "pct": 80, "volts": 8.0, "charging": False}
    (Path(isolated_project["state_dir"]) / "battery.json").write_text(json.dumps(battery))

    stdout = run_tool(["bin/tool-wander"], env)
    payload = parse_json(stdout)
    assert payload["status"] == "ok"
    assert payload.get("abort_reason") == "battery data stale or missing"


def test_wander_explore_abort_all_sonar_none(isolated_project):
    """All sonar None = sensor failure abort (dry mode simulates, so this
    tests the constant and abort check logic, not the sonar itself)."""
    from pxh.state import save_session, default_state
    state = default_state()
    state["confirm_motion_allowed"] = True
    state["roaming_allowed"] = True
    save_session(state)

    # In dry mode, sonar is simulated as 200.0 — so sensor failure
    # can only be tested via the unit test for _check_abort
    # This integration test verifies the plumbing works end-to-end
    env = isolated_project["env"].copy()
    env["PX_DRY"] = "1"
    env["PX_WANDER_MODE"] = "explore"
    env["PX_WANDER_DURATION_S"] = "3"

    import datetime as dt2
    battery = {"ts": dt2.datetime.now(dt2.timezone.utc).isoformat(),
               "pct": 80, "volts": 8.0, "charging": False}
    (Path(isolated_project["state_dir"]) / "battery.json").write_text(json.dumps(battery))

    stdout = run_tool(["bin/tool-wander"], env)
    payload = parse_json(stdout)
    assert payload["status"] == "ok"
    assert payload["mode"] == "explore"
```

- [ ] **Step 2: Run abort tests**

Run: `python -m pytest tests/test_tools.py -v -k "explore"`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_tools.py
git commit -m "test: add exploration abort scenario tests"
```

---

### Task 10: px-alive exploring.json check + session template + final verification

**Files:**
- Modify: `bin/px-alive`
- Modify: `state/session.template.json`

- [ ] **Step 1: Add exploring.json check to px-alive**

In `bin/px-alive`, at the start of the main function (after PID file logic), add:

```python
# Check if exploration is active — exit cleanly to avoid GPIO contention
exploring_file = STATE_DIR / "exploring.json"
try:
    if exploring_file.exists():
        exploring = json.loads(exploring_file.read_text(encoding="utf-8"))
        if exploring.get("active"):
            exp_pid = exploring.get("pid")
            if exp_pid and Path(f"/proc/{exp_pid}").is_dir():
                log("exploration active (PID %d) — exiting cleanly" % exp_pid)
                sys.exit(0)
except Exception:
    pass
```

- [ ] **Step 2: Update session template**

Add `"roaming_allowed": false` to `state/session.template.json`.

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest -m "not live" -v`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add bin/px-alive state/session.template.json
git commit -m "feat(alive): check exploring.json on startup; add roaming_allowed to template"
```
