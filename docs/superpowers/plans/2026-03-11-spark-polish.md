# SPARK Polish Backlog Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix GPIO busy for emotes, reduce px-mind's over-filing of memories, add a session history clear API endpoint, teach SPARK its own wake phrase, add a Frigate stream systemd service, and wire ambient sound into Obi-mode detection in px-mind.

**Architecture:** Six independent tasks. Each is self-contained and produces a working change on its own. P0 first (GPIO + PID race), then P1 quality-of-life, then P2 new capability. All bin/ scripts follow the bash-wrapper-with-embedded-Python-heredoc pattern; the FastAPI app is in `src/pxh/api.py`; the cognitive daemon is `bin/px-mind`.

**Tech Stack:** Python 3.11 (system), bash, FastAPI 0.110, pytest, systemd, espeak, aplay, picarx (system site-packages)

---

## Chunk 1: P0 — GPIO PID file race condition + emotes broken

### Task 1: Guard px-alive PID write against concurrent starts

**Problem:** When systemd rapid-restarts px-alive, two instances can start simultaneously. The second overwrites the PID file with its own PID, then exits and its `finally` block deletes the file, leaving the survivor running with no PID file. `yield_alive` can't find it, silently skips the signal, and the next `tool-perform` fails with `'GPIO busy'`.

**Files:**
- Modify: `bin/px-alive` (lines 429–431 — PID write; lines 467–476 — finally cleanup)

- [ ] **Step 1: Reproduce the missing PID file symptom in a test**

```bash
# Confirm no PID file exists right now and kill the service
sudo systemctl stop px-alive
ls logs/px-alive.pid  # should say "No such file" or show old file
```

- [ ] **Step 2: Read the px-alive PID write section**

Open `bin/px-alive` around line 429. The write is unconditional: `PID_FILE.write_text(str(os.getpid()))`. Any concurrent instance overwrites it.

- [ ] **Step 3: Add atomic compare-and-write with PID validity check**

Replace lines 429–431 in `bin/px-alive`:

```python
# OLD (unconditional):
# PID_FILE.parent.mkdir(parents=True, exist_ok=True)
# PID_FILE.write_text(str(os.getpid()))

# NEW: only write if no other live px-alive already owns the PID file
import os as _os
PID_FILE.parent.mkdir(parents=True, exist_ok=True)
_existing = None
try:
    _existing = int(PID_FILE.read_text().strip())
except Exception:
    pass
if _existing and _existing != _os.getpid() and _os.path.isdir(f"/proc/{_existing}"):
    log(f"another px-alive (pid={_existing}) already running — exiting")
    return 0  # graceful exit; systemd will not restart (rc=0)
PID_FILE.write_text(str(_os.getpid()))
```

- [ ] **Step 4: Protect the finally cleanup against deleting another instance's PID file**

In `bin/px-alive` `finally` block (around line 472) and signal handler cleanup (line 438, 455, 475):

```python
# Replace every bare: PID_FILE.unlink(missing_ok=True)
# With a guarded version:
def _safe_unlink_pid():
    try:
        if int(PID_FILE.read_text().strip()) == os.getpid():
            PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
```

Call `_safe_unlink_pid()` instead of `PID_FILE.unlink(missing_ok=True)` in all three locations.

- [ ] **Step 5: Add a test**

In `tests/test_tools.py`, add after the existing `test_tool_perform_dry_run`:

```python
def test_px_alive_pid_race_not_duplicate(isolated_project, tmp_path):
    """Second px-alive start should exit cleanly if PID file shows live process."""
    import os
    pid_file = Path(isolated_project["log_dir"]) / "px-alive.pid"
    # Write our own PID as if we're px-alive instance 1
    pid_file.write_text(str(os.getpid()))
    # Invoking px-alive with PX_ALIVE_PID set should detect the conflict and exit 0
    env = {**isolated_project["env"], "PX_ALIVE_PID": str(pid_file), "PX_DRY": "1"}
    result = subprocess.run(
        [str(Path(isolated_project["project_root"]) / "bin" / "px-alive"), "--dry-run"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    # Should have exited cleanly without overwriting PID file
    assert pid_file.read_text().strip() == str(os.getpid()), "PID file was overwritten"
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_tools.py::test_px_alive_pid_race_not_duplicate -v
```
Expected: PASS

- [ ] **Step 7: Restart px-alive and confirm PID file exists**

```bash
sudo systemctl restart px-alive
sleep 4
cat logs/px-alive.pid  # should show current PID
```

- [ ] **Step 8: Smoke-test emote via tool-perform**

```bash
PX_DRY=1 PX_BYPASS_SUDO=1 PX_PERFORM_STEPS='[{"emote":"curious","pause":0.3}]' bin/tool-perform
# Expected: {"status": "ok", "returncode": 0, ...}
```

- [ ] **Step 9: Commit**

```bash
git add bin/px-alive tests/test_tools.py
git commit -m "fix(alive): guard PID file write against concurrent-start race condition"
```

---

## Chunk 2: P1 — px-mind time-of-day action weighting

### Task 2: Weight reflection actions by time of day

**Problem:** px-mind uses Claude (for SPARK) and chooses `"remember"` or `"wait"` far too often, meaning SPARK stays silent during the day. The LLM should be nudged toward `comment`/`greet` during Obi's waking hours (7am–8pm AEDT = UTC+11) and toward `wait`/`remember` overnight.

**Strategy:** Inject a time-of-day instruction into the SPARK reflection prompt (not the other personas — GREMLIN and VIXEN are adult use and are fine being nocturnal).

**Files:**
- Modify: `bin/px-mind` (around line 288 — `REFLECTION_SYSTEM_SPARK`; around line 900 — `reflection()` call that builds the prompt)

- [ ] **Step 1: Locate where the reflection prompt is assembled**

```bash
grep -n "build_reflection_prompt\|REFLECTION_SYSTEM_SPARK\|system.*prompt\|user_prompt\|def reflection" bin/px-mind | head -20
```

- [ ] **Step 2: Add a helper function to determine daytime context**

Add near the top of the Python heredoc constants section in `bin/px-mind` (after imports, before `VALID_MOODS`):

```python
import datetime as _dt
AEDT = _dt.timezone(_dt.timedelta(hours=11))  # UTC+11

def _daytime_action_hint() -> str:
    """Return an action-weighting hint based on Hobart local time."""
    hour = _dt.datetime.now(AEDT).hour
    if 7 <= hour < 20:
        # Obi's waking hours — prefer speaking
        return (
            "\n\nIMPORTANT: It is daytime in Hobart. Obi may be present. "
            "Strongly prefer action='comment' or action='greet'. "
            "Use 'remember' or 'wait' ONLY if you literally just spoke."
        )
    else:
        # Overnight — Obi is asleep, be quiet
        return (
            "\n\nIMPORTANT: It is night in Hobart. Obi is likely asleep. "
            "Prefer action='remember' or action='wait'. "
            "Only use 'comment' if salience > 0.8."
        )
```

- [ ] **Step 3: Inject the hint into SPARK's reflection prompt**

Find the `reflection()` function in `bin/px-mind`. Locate where `REFLECTION_SYSTEM_SPARK` is used as the system prompt (it will be something like `system = REFLECTION_SYSTEM_SPARK`). Change it to:

```python
# For SPARK only, append time-of-day hint
if persona == "spark":
    system = REFLECTION_SYSTEM_SPARK + _daytime_action_hint()
else:
    system = reflection_system  # unchanged for other personas
```

- [ ] **Step 4: Write a test**

Add to `tests/test_state.py` (or a new `tests/test_mind_utils.py`):

```python
def test_daytime_hint_daytime():
    """During daytime hours the hint should encourage comment/greet."""
    import datetime as dt
    # Patch datetime to return 10am AEDT
    # (This tests the logic, not the actual time)
    AEDT = dt.timezone(dt.timedelta(hours=11))
    hint_fn = ... # import or inline _daytime_action_hint with hour=10
    hint = hint_fn(hour_override=10)
    assert "comment" in hint
    assert "greet" in hint

def test_daytime_hint_night():
    hint_fn = ...
    hint = hint_fn(hour_override=2)
    assert "asleep" in hint
    assert "remember" in hint
```

To make `_daytime_action_hint` testable, accept an optional `hour_override` param:

```python
def _daytime_action_hint(hour_override: int | None = None) -> str:
    hour = hour_override if hour_override is not None else _dt.datetime.now(AEDT).hour
    ...
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_mind_utils.py -v
```

- [ ] **Step 6: Restart px-mind and verify in log**

```bash
sudo systemctl restart px-mind
sleep 60
grep "expressing\|action=" logs/px-mind.log | tail -5
# During daytime should show more comment/greet
```

- [ ] **Step 7: Commit**

```bash
git add bin/px-mind tests/
git commit -m "feat(mind): weight SPARK reflection actions by time of day (Obi hours)"
```

---

## Chunk 3: P1 — Session history clear API endpoint

### Task 3: POST /api/v1/session/history/clear

**Problem:** Session history accumulates up to 100 entries including corrupted phrases from bad STT results. px-mind's reflection ingests recent history, so garbled text keeps appearing in thoughts. Need a way to wipe it from the web UI (Adrian panel) without SSHing in.

**Files:**
- Modify: `src/pxh/api.py` (add new endpoint; add button to Adrian panel HTML)
- Modify: `tests/test_api.py` (if it exists) or `tests/test_tools.py`

- [ ] **Step 1: Check existing API test file**

```bash
ls tests/test_api.py 2>/dev/null || echo "no test_api.py — add to test_tools.py"
```

- [ ] **Step 2: Write failing test for the new endpoint**

In `tests/test_tools.py` (or `test_api.py`):

```python
def test_session_history_clear(isolated_project):
    """POST /api/v1/session/history/clear should wipe session history."""
    from fastapi.testclient import TestClient
    from pxh.api import app
    client = TestClient(app)
    # Seed history
    from pxh.state import update_session
    update_session(history_entry={"event": "test", "text": "hello"})
    # Clear it
    resp = client.post(
        "/api/v1/session/history/clear",
        headers={"Authorization": "Bearer testtoken"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cleared"] > 0
    # Verify history is empty
    from pxh.state import load_session
    assert load_session().get("history", []) == []
```

- [ ] **Step 3: Run test to confirm it fails**

```bash
python -m pytest tests/test_tools.py::test_session_history_clear -v
# Expected: FAIL — 404 not found
```

- [ ] **Step 4: Add the endpoint to src/pxh/api.py**

After the `patch_session` function (around line 230), add:

```python
@app.post("/api/v1/session/history/clear", dependencies=[Depends(verify_token)])
async def clear_session_history() -> Dict[str, Any]:
    """Wipe session conversation history (keeps all other session fields)."""
    session = load_session()
    count = len(session.get("history", []))
    update_session(fields={"history": []})
    return {"status": "ok", "cleared": count}
```

Note: `update_session` accepts a `fields` dict that merges into the session. Passing `history: []` resets it. Verify this works with how `update_session` is implemented in `src/pxh/state.py`.

- [ ] **Step 5: Run test again**

```bash
python -m pytest tests/test_tools.py::test_session_history_clear -v
# Expected: PASS
```

- [ ] **Step 6: Add a "Clear History" button to the Adrian panel in the web UI**

In `src/pxh/api.py`, find the Adrian panel HTML section. Add a danger-zone button:

```html
<button onclick="clearHistory()" style="background:#dc2626;color:#fff;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px;">🗑 Clear Session History</button>
```

And the JS function (in the `<script>` block):

```javascript
async function clearHistory() {
  if (!confirm('Wipe all session history? SPARK will stop ruminating on old phrases.')) return;
  const r = await api('/api/v1/session/history/clear', {method:'POST'});
  chat(`History cleared (${r.cleared} entries removed).`);
}
```

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
python -m pytest -m "not live" -q
# Expected: all pass
```

- [ ] **Step 8: Commit**

```bash
git add src/pxh/api.py tests/
git commit -m "feat(api): POST /session/history/clear endpoint + Adrian panel button"
```

---

## Chunk 4: P1 — SPARK self-introduction of wake phrase

### Task 4: Add "say hey spark" to SPARK's first-contact rule

**Problem:** Obi doesn't know to say "hey spark" — there's no mechanism for SPARK to tell him. The system prompt should instruct SPARK to mention the wake phrase naturally in early interactions.

**Files:**
- Modify: `docs/prompts/spark-voice-system.md` (Rules section, around line 195)

- [ ] **Step 1: Read the current Rules section**

```bash
tail -20 docs/prompts/spark-voice-system.md
```

- [ ] **Step 2: Add rule about self-introduction**

In `docs/prompts/spark-voice-system.md`, add to the numbered Rules list:

```markdown
15. On your very first interaction of a session with Obi (when the history is short or empty), naturally work in: "You can say 'hey spark' any time to talk to me." — say it once, casually, not as a lecture. After that, never repeat it unless Obi asks how to wake you up.
```

This is a simple document edit — no code change, no test needed.

- [ ] **Step 3: Also add to session context builder**

In `bin/px-wake-listen`, find where the voice loop is invoked with the session context. Confirm the system prompt file path is `docs/prompts/spark-voice-system.md` (via `--prompt` arg in `run-voice-loop-claude`).

```bash
grep -n "spark.*prompt\|spark-voice-system\|--prompt" bin/run-voice-loop-claude bin/px-spark 2>/dev/null
```

No code change needed if the system prompt is already being read from the file.

- [ ] **Step 4: Commit**

```bash
git add docs/prompts/spark-voice-system.md
git commit -m "feat(spark): instruct SPARK to tell Obi its wake phrase on first interaction"
```

---

## Chunk 5: P2 — Frigate stream systemd service with camera exclusivity

### Task 5: px-frigate-stream.service

**Problem:** `bin/px-frigate-stream` works manually but isn't a systemd service. Also, `tool-photograph` and `tool-describe-scene` conflict with the rpicam-vid process that powers the stream.

**Files:**
- Create: `systemd/px-frigate-stream.service`
- Modify: `bin/tool-photograph` — check if stream is active before opening camera
- Modify: `bin/tool-describe-scene` — same guard
- Modify: `bin/px-frigate-stream` — write a PID file; handle SIGTERM cleanly

**Design decision — camera exclusivity strategy:**
- `px-frigate-stream` writes a PID file `logs/px-frigate-stream.pid`
- `tool-photograph` and `tool-describe-scene` check for that PID file and emit `{"status": "error", "error": "camera busy (frigate stream active)"}` if present
- This is simpler than a SIGUSR1 stop/start cycle (frigate stream restart takes ~3s and confuses go2rtc)

- [ ] **Step 1: Add PID file writing to px-frigate-stream**

In `bin/px-frigate-stream`, after the Python/bash shebang section, add:

```bash
STREAM_PID_FILE="${LOG_DIR}/px-frigate-stream.pid"
echo $$ > "$STREAM_PID_FILE"
trap "rm -f '$STREAM_PID_FILE'" EXIT SIGTERM SIGINT
```

(This is a bash-level change before the main ffmpeg pipeline.)

- [ ] **Step 2: Write the systemd service**

Create `systemd/px-frigate-stream.service`:

```ini
[Unit]
Description=PiCar-X Frigate camera stream (RTSP push to go2rtc)
After=network.target
# Don't start if tool-photograph might be running (best-effort)

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/picar-x-hacking
Environment=HOME=/home/pi
ExecStart=/home/pi/picar-x-hacking/bin/px-frigate-stream
Restart=on-failure
RestartSec=15
# Give rpicam-vid time to release the camera on stop
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Note: `Restart=on-failure` not `always` — don't restart if manually stopped or camera is in use.

- [ ] **Step 3: Add camera-busy guard to tool-photograph**

In `bin/tool-photograph` (Python heredoc section), near the top:

```python
import os, sys
from pathlib import Path
LOG_DIR = Path(os.environ.get("LOG_DIR", Path(os.environ["PROJECT_ROOT"]) / "logs"))
_stream_pid_file = LOG_DIR / "px-frigate-stream.pid"
if _stream_pid_file.exists():
    try:
        _stream_pid = int(_stream_pid_file.read_text().strip())
        if Path(f"/proc/{_stream_pid}").is_dir():
            payload = {"status": "error", "error": "camera busy — frigate stream active"}
            print(json.dumps(payload))
            sys.exit(1)
    except Exception:
        pass  # stale pid file — proceed
```

- [ ] **Step 4: Same guard in tool-describe-scene**

Same three-line check in `bin/tool-describe-scene`.

- [ ] **Step 5: Write a dry-run test for the camera-busy guard**

```python
def test_tool_photograph_camera_busy(isolated_project):
    """tool-photograph should fail gracefully when frigate stream is active."""
    pid_file = Path(isolated_project["log_dir"]) / "px-frigate-stream.pid"
    pid_file.write_text(str(os.getpid()))  # our own PID = definitely alive
    env = {**isolated_project["env"], "PX_DRY": "1"}
    result = subprocess.run(
        [str(Path(isolated_project["project_root"]) / "bin" / "tool-photograph")],
        capture_output=True, text=True, env=env, timeout=10,
    )
    data = json.loads(result.stdout)
    assert data["status"] == "error"
    assert "camera busy" in data["error"]
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_tools.py::test_tool_photograph_camera_busy -v
```

- [ ] **Step 7: Install service (don't enable by default — on-demand)**

```bash
sudo cp systemd/px-frigate-stream.service /etc/systemd/system/
sudo systemctl daemon-reload
# Don't enable — start manually when streaming is wanted:
# sudo systemctl start px-frigate-stream
```

- [ ] **Step 8: Commit**

```bash
git add systemd/px-frigate-stream.service bin/px-frigate-stream bin/tool-photograph bin/tool-describe-scene tests/
git commit -m "feat(frigate): systemd service + camera exclusivity guard for photo tools"
```

---

## Chunk 6: P2 — Obi-mode detection in px-mind Layer 1

### Task 6: Wire ambient sound level into obi_mode state

**Problem:** px-mind's Layer 1 already reads `state/ambient_sound.json` (written by px-wake-listen) but doesn't do anything with it. The ambient level (`silent`/`quiet`/`moderate`/`loud`) is a useful proxy for Obi's presence and state — loud = likely active/dysregulated, silent = absent or calm.

**Design:**
- Layer 1 computes `obi_mode` from ambient level + sonar + time-of-day
- Writes it to `state/awareness.json` alongside existing fields
- Layer 2 reflection prompt receives `obi_mode` in context
- Layer 3 expression checks `obi_mode` before choosing vocal actions (don't speak if `sensory-overloaded`)

**obi_mode values:**
| Value | Conditions | SPARK response |
|---|---|---|
| `unknown` | No ambient data or too stale | Normal |
| `absent` | Silent + no sonar (<35cm) + night hours | Stay quiet |
| `calm` | Quiet/moderate ambient + sonar in range | Normal engagement |
| `active` | Loud ambient + sonar in range + day | Energised but steady |
| `possibly-overloaded` | Loud + very close sonar (<20cm) | Reduce output |

**Files:**
- Modify: `bin/px-mind` — `awareness_tick()` function (around line 669 where ambient is already read)
- Modify: `bin/px-mind` — `expression()` function to gate speech on `obi_mode`
- Modify: `bin/px-mind` — SPARK reflection prompt context to include `obi_mode`

- [ ] **Step 1: Locate awareness_tick and add obi_mode computation**

Find `awareness_tick()` in `bin/px-mind`. After the existing ambient sound block (around line 678), add:

```python
# Compute obi_mode from ambient + sonar + time
import datetime as _dt
_hour = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=11))).hour
_ambient_level = awareness.get("ambient_sound", {}).get("level", "unknown")
_sonar_cm = awareness.get("sonar_cm")
_is_day = 7 <= _hour < 20
_close = _sonar_cm is not None and _sonar_cm < 35
_very_close = _sonar_cm is not None and _sonar_cm < 20

if _ambient_level == "unknown":
    obi_mode = "unknown"
elif not _is_day and _ambient_level in ("silent", "quiet") and not _close:
    obi_mode = "absent"
elif _very_close and _ambient_level == "loud":
    obi_mode = "possibly-overloaded"
elif _close and _is_day:
    obi_mode = "active" if _ambient_level == "loud" else "calm"
else:
    obi_mode = "calm"

awareness["obi_mode"] = obi_mode
```

- [ ] **Step 2: Add obi_mode to SPARK reflection context**

Find where the reflection user prompt is built (in `reflection()` function). The context dict or string that includes sonar, battery, etc. Add:

```python
# In the context block passed to LLM
obi_mode = awareness.get("obi_mode", "unknown")
context_lines.append(f"Obi's current mode: {obi_mode}")
```

Also add a note in `REFLECTION_SYSTEM_SPARK` (the system prompt string) explaining what obi_mode means:
```
- When context shows obi_mode='possibly-overloaded': choose action='wait' or 'look_at'. No speech.
- When obi_mode='absent': prefer 'remember' or 'wait'.
- When obi_mode='active' or 'calm': prefer 'comment' or 'greet'.
```

- [ ] **Step 3: Gate Layer 3 expression on obi_mode**

In `expression()` function (around line 1042), at the top after getting `action`:

```python
# Don't speak if Obi seems overloaded
obi_mode = thought.get("obi_mode") or load_session().get("obi_mode", "unknown")
if obi_mode == "possibly-overloaded" and action in ("comment", "greet", "weather_comment"):
    log(f"expression suppressed (obi_mode={obi_mode}): {action}")
    return
```

- [ ] **Step 4: Write tests**

```python
def test_obi_mode_absent_at_night():
    """At 2am with silent ambient and no sonar, obi_mode should be 'absent'."""
    awareness = {
        "ambient_sound": {"level": "silent"},
        "sonar_cm": None,
    }
    result = compute_obi_mode(awareness, hour_override=2)
    assert result == "absent"

def test_obi_mode_overloaded():
    awareness = {
        "ambient_sound": {"level": "loud"},
        "sonar_cm": 15,  # very close
    }
    result = compute_obi_mode(awareness, hour_override=10)
    assert result == "possibly-overloaded"
```

Extract `compute_obi_mode` as a standalone function (currently inline) to make it testable.

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/ -k "obi_mode" -v
```

- [ ] **Step 6: Restart px-mind and verify obi_mode appears in awareness.json**

```bash
sudo systemctl restart px-mind
sleep 35
cat state/awareness.json | python3 -m json.tool | grep obi_mode
```

- [ ] **Step 7: Commit**

```bash
git add bin/px-mind tests/
git commit -m "feat(mind): obi_mode detection from ambient sound + sonar + time-of-day"
```

---

## Execution order

1. Task 1 (GPIO PID race) — already partially fixed by `sudo systemctl restart px-alive`; the code change prevents recurrence
2. Task 2 (time-of-day weighting) — quick prompt injection, high daily impact
3. Task 3 (history clear endpoint) — needed to clear the current corrupted history
4. Task 4 (SPARK self-intro) — one-line doc change
5. Task 5 (Frigate stream service) — new capability, independent
6. Task 6 (obi-mode detection) — builds on Task 2's time-of-day infrastructure

Run the full test suite after each task:
```bash
python -m pytest -m "not live" -q
```

Expected: 107+ tests passing throughout.
