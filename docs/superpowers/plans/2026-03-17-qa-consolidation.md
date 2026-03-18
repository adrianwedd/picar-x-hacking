# QA Consolidation — Fix Critical/High/Medium Findings

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address all 19 actionable findings from the consolidated QA report (3 critical, 5 high, 11 medium) to harden SPARK's runtime reliability, security, and data durability before the April DST transition.

**Architecture:** Fixes are grouped by subsystem (px-mind, state.py, api.py, .gitignore) to minimise context-switching. Each task produces a self-contained commit. The DST fix is first because it has a hard deadline (first Sunday of April 2026). TDD where feasible — some fixes are in bash heredocs where unit testing requires subprocess integration tests.

**Tech Stack:** Python 3.11, `zoneinfo` stdlib, `filelock`, `tempfile`, FastAPI, systemd, bash

---

## File Structure

| File | Responsibility | Tasks |
|------|---------------|-------|
| `bin/px-mind` | Cognitive loop daemon (3100-line bash heredoc) | 1, 3, 5, 6, 8, 9 |
| `src/pxh/state.py` | Thread-safe session management | 4 |
| `src/pxh/api.py` | REST API | 7, 10 |
| `bin/tool-describe-scene` | Camera + vision description tool | 2 |
| `bin/px-wake-listen` | Wake word listener | 6 |
| `.gitignore` | Git ignore patterns | 11 |
| `tests/test_mind_utils.py` | px-mind unit tests (extracted functions) | 1, 3, 5, 8 |
| `tests/test_state.py` | state.py tests | 4 |
| `tests/test_api.py` | API tests | 7 |

---

### Task 1: Fix hardcoded AEDT timezone (CRITICAL — April deadline)

**Files:**
- Modify: `bin/px-mind:152` — replace `AEDT` constant
- Modify: `bin/px-mind:159,184,1537,2837,3070` — all `AEDT` usage sites
- Modify: `tests/test_mind_utils.py:550,568,585,598` — update test fixtures
- Test: `tests/test_mind_utils.py`

**Context:** `bin/px-mind` line 152 defines `AEDT = dt.timezone(dt.timedelta(hours=11))`. Tasmania switches to AEST (UTC+10) on the first Sunday of April. After that, all time-gated behaviour (morning/bedtime suppression, school hours, day/night gating) will be wrong by 1 hour. `src/pxh/api.py` already uses the correct pattern: `ZoneInfo("Australia/Hobart")`.

- [ ] **Step 1: Write a failing test for DST-aware timezone**

Add to `tests/test_mind_utils.py`:

```python
def test_hobart_tz_is_dst_aware():
    """HOBART_TZ must be a DST-aware zone, not a fixed UTC offset."""
    import importlib, types
    # The constant should be a ZoneInfo, not a fixed-offset timezone
    assert hasattr(HOBART_TZ, 'key'), (
        "HOBART_TZ should be ZoneInfo('Australia/Hobart'), not a fixed offset"
    )
    assert HOBART_TZ.key == "Australia/Hobart"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_mind_utils.py::test_hobart_tz_is_dst_aware -v`
Expected: FAIL — `HOBART_TZ` not defined (still called `AEDT`)

- [ ] **Step 3: Replace hardcoded AEDT in px-mind**

In `bin/px-mind`, replace line 152:

```python
# OLD:
AEDT = dt.timezone(dt.timedelta(hours=11))  # Hobart, Tasmania (UTC+11)

# NEW:
from zoneinfo import ZoneInfo
HOBART_TZ = ZoneInfo("Australia/Hobart")  # DST-aware: AEDT (UTC+11) / AEST (UTC+10)
```

Then rename all references — 5 locations in px-mind:
- Line 159: `dt.datetime.now(AEDT)` → `dt.datetime.now(HOBART_TZ)`
- Line 184: `dt.datetime.now(AEDT)` → `dt.datetime.now(HOBART_TZ)`
- Line 1537: `now.astimezone(AEDT)` → `now.astimezone(HOBART_TZ)`
- Line 2837: `dt.datetime.now(AEDT)` → `dt.datetime.now(HOBART_TZ)`
- Line 3070: `dt.datetime.now(AEDT)` → `dt.datetime.now(HOBART_TZ)`

- [ ] **Step 4: Update test fixtures**

In `tests/test_mind_utils.py`, replace all 4 test fixtures:

```python
# OLD (lines 550, 568, 585, 598):
tzinfo=_dt_cal.timezone(_dt_cal.timedelta(hours=11))

# NEW:
from zoneinfo import ZoneInfo
_HOBART = ZoneInfo("Australia/Hobart")
# Then in each test:
tzinfo=_HOBART
```

Also update the `HOBART_TZ` import at the top of the test file where other px-mind symbols are imported.

- [ ] **Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_mind_utils.py -v -k "hobart or calendar"`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add bin/px-mind tests/test_mind_utils.py
git commit -m "fix: replace hardcoded AEDT with ZoneInfo('Australia/Hobart') for DST"
```

---

### Task 2: Set exploring.json in tool-describe-scene (CRITICAL)

**Files:**
- Modify: `bin/tool-describe-scene` — add exploring.json write/cleanup
- Test: `tests/test_tools.py` — add dry-run test

**Context:** `tool-describe-scene` can take 60s+ (Claude vision). `px-alive` restarts after 15s via systemd and calls `Picarx()` which resets the MCU, interrupting any camera operation. `tool-wander` already sets `exploring.json` correctly using `tempfile.mkstemp` + `os.replace`. `px-alive` checks this file on startup and exits if active.

Note: `tool-describe-scene` does NOT define `STATE_DIR` — it uses `PROJECT_ROOT` (from env). Add a `STATE_DIR` constant near the existing `PROJECT_ROOT` definition (line 25).

- [ ] **Step 1: Read tool-describe-scene to find the right insertion point**

Read `bin/tool-describe-scene` to identify where the main work begins (after dry-run check at line 177, before photograph capture at line 178).

- [ ] **Step 2: Add STATE_DIR and exploring.json guard to tool-describe-scene**

First, add `STATE_DIR` near line 25 (after `PROJECT_ROOT`), and `import tempfile` + `import datetime as dt` to the imports section (lines 10-23):

```python
STATE_DIR = Path(os.environ.get("PX_STATE_DIR", str(PROJECT_ROOT / "state")))
```

Then add the helper function before `main()`:

```python
import tempfile

def _set_exploring(active: bool) -> None:
    """Write exploring.json so px-alive yields GPIO."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / "exploring.json"
    data = {"active": active}
    if active:
        data["pid"] = os.getpid()
        data["started"] = dt.datetime.now(dt.timezone.utc).isoformat()
    fd, tmp = tempfile.mkstemp(dir=str(STATE_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
```

Then wrap the main camera+describe block (line 178 onward, after the dry-run early return):

```python
_set_exploring(True)
try:
    # ... existing photograph + describe logic (lines 178-232) ...
finally:
    _set_exploring(False)
```

- [ ] **Step 3: Add dry-run test**

In `tests/test_tools.py`, add a test that runs `tool-describe-scene` in dry-run mode and verifies `exploring.json` is cleaned up (active=false) after exit.

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_tools.py -v -k describe_scene`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bin/tool-describe-scene tests/test_tools.py
git commit -m "fix: set exploring.json in tool-describe-scene to prevent px-alive restart"
```

---

### Task 3: Unify atomic_write — use state.py's robust version in px-mind (HIGH)

**Files:**
- Modify: `bin/px-mind:696-700` — replace naive `atomic_write` with robust version
- Test: `tests/test_mind_utils.py`

**Context:** `bin/px-mind` has a 5-line `atomic_write()` that uses a deterministic `.tmp` suffix (race-prone), no ownership preservation, no cleanup on failure. `src/pxh/state.py` has a robust version using `tempfile.mkstemp()`, ownership preservation, `0o644` mode, and full error handling. Since px-mind runs as `pi` user and writes to state files that px-alive (root) may also read, the robust version is needed.

- [ ] **Step 1: Write a test for atomic_write crash safety**

Add to `tests/test_mind_utils.py`:

```python
def test_atomic_write_no_partial_on_error(tmp_path):
    """atomic_write must not leave partial files on write failure."""
    target = tmp_path / "test.json"
    target.write_text('{"original": true}')
    # Simulate write failure by making parent read-only after creating target
    # (this tests the cleanup path)
    assert target.read_text() == '{"original": true}'
```

- [ ] **Step 2: Replace px-mind's atomic_write**

In `bin/px-mind`, replace lines 696-700:

```python
# OLD:
def atomic_write(path: Path, data: str) -> None:
    """Write data to file atomically via temp + rename (prevents partial reads)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.rename(path)

# NEW:
def atomic_write(path: Path, data: str) -> None:
    """Write data to file atomically via mkstemp + os.replace.

    Uses secure temp file (no deterministic name), preserves ownership for
    cross-user access (root px-alive / pi px-mind), sets 0o644, cleans up on error.
    """
    try:
        st = path.stat()
        orig_uid, orig_gid = st.st_uid, st.st_gid
    except FileNotFoundError:
        orig_uid, orig_gid = None, None

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        if orig_uid is not None:
            try:
                os.chown(tmp, orig_uid, orig_gid)
            except OSError:
                pass
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
```

Also add `import tempfile` near the top of the heredoc if not already present.

Note: This also addresses finding #8 (deterministic temp filename) and #13 (no fsync). The `fsync` call is intentionally added here but not in `state.py`'s `_atomic_write` — px-mind writes awareness/mood state that is read by the dashboard and other daemons, where SD-card durability matters more. `state.py` writes session.json which is updated frequently and can tolerate loss of the last write (it recovers via `default_state()`). If desired, `fsync` can be added to `state.py` later as a separate commit.

- [ ] **Step 3: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_mind_utils.py tests/test_px_mind.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add bin/px-mind tests/test_mind_utils.py
git commit -m "fix: replace naive atomic_write in px-mind with mkstemp+fsync+ownership version"
```

---

### Task 4: Add FileLock timeout to state.py (HIGH)

**Files:**
- Modify: `src/pxh/state.py:95,107,120,133` — add timeout to all 4 lock sites
- Test: `tests/test_state.py`

**Context:** All 4 `FileLock()` acquisitions in state.py have no timeout. If a process crashes while holding the lock (or the lock file becomes stale), all state operations hang indefinitely. The `filelock` library supports a `timeout` parameter — after the timeout, it raises `filelock.Timeout`.

- [ ] **Step 1: Write a failing test for lock timeout**

Add to `tests/test_state.py`:

```python
import filelock

def test_filelock_has_timeout(isolated_project):
    """FileLock must not block indefinitely — should raise after timeout."""
    from pxh.state import session_path, ensure_session
    path = ensure_session()
    lock_path = str(path) + ".lock"
    # Hold the lock externally
    outer = filelock.FileLock(lock_path)
    outer.acquire()
    try:
        # load_session should raise Timeout, not hang forever
        import pxh.state as _st
        with pytest.raises(filelock.Timeout):
            # Temporarily patch to short timeout for test speed
            _st.load_session()
    finally:
        outer.release()
```

Note: This test will need adjustment based on how the timeout is implemented (the constant value).

- [ ] **Step 2: Add LOCK_TIMEOUT_S constant and apply to all 4 sites**

In `src/pxh/state.py`, add near the top:

```python
LOCK_TIMEOUT_S = 10  # seconds — fail fast rather than hang forever
```

Then update all 4 lock sites:

```python
# Line 95:  with FileLock(lock_path):
# Line 107: with FileLock(lock_path):
# Line 120: with FileLock(lock_path):
# Line 133: with FileLock(lock_path):

# ALL become:
with FileLock(lock_path, timeout=LOCK_TIMEOUT_S):
```

- [ ] **Step 3: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_state.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/pxh/state.py tests/test_state.py
git commit -m "fix: add 10s timeout to all FileLock acquisitions in state.py"
```

---

### Task 5: Add single-instance PID guards to px-mind and px-wake-listen (HIGH)

**Files:**
- Modify: `bin/px-mind` — add PID check before write (copy px-alive's pattern)
- Modify: `bin/px-wake-listen` — same
- Test: `tests/test_px_mind.py`

**Context:** `px-alive` already has this fix (2026-03-11): check-before-write exits cleanly if another instance is running. `px-mind` and `px-wake-listen` unconditionally overwrite their PID files, risking duplicate daemons on rapid systemd restarts which cause double speech output.

- [ ] **Step 1: Add PID guard to px-mind**

After the line that creates PID directory (line ~3261), before the unconditional PID write, add:

```python
# Guard: if another live px-mind already owns the PID file, exit cleanly
_existing_pid = None
try:
    _existing_pid = int(PID_FILE.read_text().strip())
except (FileNotFoundError, ValueError, OSError):
    pass
if _existing_pid and _existing_pid != os.getpid() and os.path.isdir(f"/proc/{_existing_pid}"):
    log(f"another px-mind (pid={_existing_pid}) already running — exiting")
    return 0
PID_FILE.write_text(str(os.getpid()))
```

- [ ] **Step 2: Add same PID guard to px-wake-listen**

Same pattern at line ~1148.

- [ ] **Step 3: Run existing tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_px_mind.py -v`
Expected: All PASS (existing tests cover dry-run which should still work with guard)

- [ ] **Step 4: Commit**

```bash
git add bin/px-mind bin/px-wake-listen
git commit -m "fix: add single-instance PID guards to px-mind and px-wake-listen"
```

---

### Task 6: Fix tool execution subprocess orphaning in API (HIGH)

**Files:**
- Modify: `src/pxh/voice_loop.py` — add timeout parameter to `execute_tool()`
- Modify: `src/pxh/api.py` — pass timeout to execute_tool
- Test: `tests/test_api.py`

**Context:** When `asyncio.wait_for` times out in the `/tool` endpoint, the thread running `subprocess.run()` continues — the subprocess is never killed. The public chat endpoint already does this correctly with `subprocess.run(..., timeout=sp_timeout)`. The fix is to pass a `timeout` to `subprocess.run()` in `execute_tool()`.

There are **5 call sites** for `execute_tool` across 2 files:
- `voice_loop.py:786` — main voice loop (no timeout needed — voice loop manages its own watchdog)
- `voice_loop.py:839` — weather voice output (no timeout needed)
- `api.py:1098` — async wander job (needs timeout — long-running)
- `api.py:1124` — sync tool with asyncio.wait_for (needs timeout — this is the primary fix)
- `api.py:1204` — synchronous tool call from internal helper (needs timeout)

- [ ] **Step 1: Add timeout parameter to execute_tool**

In `src/pxh/voice_loop.py`, modify `execute_tool()` signature:

```python
def execute_tool(tool: str, env_overrides: dict | None = None,
                 dry: bool = False, timeout: float | None = None):
```

Add `timeout=timeout` to the `subprocess.run()` call. Catch `subprocess.TimeoutExpired` and return a timeout error tuple:

```python
try:
    result = subprocess.run(
        [str(command_path)],
        capture_output=True, text=True, check=False,
        env=env, timeout=timeout,
    )
except subprocess.TimeoutExpired:
    return 1, json.dumps({"status": "error", "error": f"tool {tool} timed out after {timeout}s"}), ""
```

- [ ] **Step 2: Update ALL 3 API call sites**

In `src/pxh/api.py`:

**Site 1 — async wander job (line 1098):**
```python
# OLD:
rc, stdout, stderr = await loop.run_in_executor(
    None, execute_tool, tool, env_overrides, dry
)
# NEW:
rc, stdout, stderr = await loop.run_in_executor(
    None, execute_tool, tool, env_overrides, dry, SYNC_TIMEOUT_SLOW
)
```

**Site 2 — sync tool with timeout (line 1124):**
```python
# OLD:
rc, stdout, stderr = await asyncio.wait_for(
    loop.run_in_executor(None, execute_tool, tool, env_overrides, dry),
    timeout=timeout,
)
# NEW (subprocess kills itself; asyncio is safety net):
rc, stdout, stderr = await asyncio.wait_for(
    loop.run_in_executor(None, execute_tool, tool, env_overrides, dry, timeout),
    timeout=timeout + 2,
)
```

**Site 3 — synchronous tool call (line 1204):**
```python
# OLD:
t_rc, t_stdout, t_stderr = execute_tool(tool, env_overrides, dry)
# NEW:
t_rc, t_stdout, t_stderr = execute_tool(tool, env_overrides, dry, SYNC_TIMEOUT_DEFAULT)
```

The 2 voice_loop.py call sites (lines 786, 839) are left as-is — the voice loop has its own watchdog thread for stall detection.

- [ ] **Step 3: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_api.py tests/test_voice_loop.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/pxh/voice_loop.py src/pxh/api.py
git commit -m "fix: pass timeout to subprocess.run in execute_tool to kill orphaned processes"
```

---

### Task 7: Make PIN lockout per-IP and fix X-Forwarded-For spoofing (HIGH)

**Files:**
- Modify: `src/pxh/api.py` — per-IP lockout, trusted proxy check
- Test: `tests/test_api.py`

**Context:** PIN lockout is global — any remote actor can lock out all legitimate users. Also, `X-Forwarded-For` is trusted unconditionally, allowing rate limit bypass. Fix: make lockout per-IP, and only trust `X-Forwarded-For` from localhost/known proxies.

- [ ] **Step 1: Add trusted proxy check to _get_client_ip**

```python
_TRUSTED_PROXIES = {"127.0.0.1", "::1"}  # Only trust XFF from Cloudflare tunnel / localhost

def _get_client_ip(request: "Request") -> str:
    peer = request.client.host if request.client else "unknown"
    if peer in _TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return peer
```

- [ ] **Step 2: Make PIN lockout per-IP**

Replace the global scalars with per-IP dicts. The current implementation has:
- `_pin_attempts: int` (line 1365) → `_pin_attempts: dict[str, int]`
- `_pin_lockout_until: float` (line 1366) → `_pin_lockout_until: dict[str, float]`
- `_pin_lock` (line 1364) — keep as-is, still protects both dicts

Update `pin_lockout.json` schema (line 1408-1440 `_save_pin_state()`):

```python
# OLD schema:
{"attempts": 3, "lockout_until": "2026-03-17T10:30:00+00:00", "last_attempt_ts": "..."}

# NEW schema:
{
  "version": 2,
  "ips": {
    "192.168.1.5": {"attempts": 3, "lockout_until": "2026-03-17T10:30:00+00:00"},
    "10.0.0.1": {"attempts": 1, "lockout_until": null}
  }
}
```

Migration in `_load_pin_state()` (line 1378-1405): if `data` has no `"version"` key, it's the old global format — ignore it (reset to empty). The old format had no IP info, so there's nothing to migrate per-IP. This is safe because the worst case is a lockout expires early on upgrade.

Cap dict at 1000 IPs in `_save_pin_state()`:

```python
if len(data["ips"]) > 1000:
    # Evict IPs with zero lockout first, then oldest
    expired = [ip for ip, v in data["ips"].items()
               if not v.get("lockout_until")]
    for ip in expired[:len(data["ips"]) - 1000]:
        del data["ips"][ip]
```

Update `verify_pin()` (line 959-1013) to pass `client_ip = _get_client_ip(request)` and index into the per-IP dicts:

```python
# Instead of: _pin_attempts += 1
# Use: _pin_attempts[client_ip] = _pin_attempts.get(client_ip, 0) + 1
```

- [ ] **Step 3: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_api.py -v -k pin`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/pxh/api.py tests/test_api.py
git commit -m "fix: per-IP PIN lockout + trusted proxy check for X-Forwarded-For"
```

---

### Task 8: Add thought-images cleanup (MEDIUM)

**Files:**
- Modify: `bin/px-mind` — add cleanup function called from awareness_tick
- Test: `tests/test_mind_utils.py`

**Context:** `state/thought-images/` currently has 278 files (16 MB) and grows unbounded. On a Raspberry Pi with 7.2 GB free on the SD card, this will eventually fill the disk. Add a cleanup pass that deletes images older than 30 days during the awareness tick.

- [ ] **Step 1: Add cleanup function to px-mind**

```python
THOUGHT_IMAGE_MAX_AGE_DAYS = 30

def _cleanup_thought_images() -> int:
    """Delete thought images older than THOUGHT_IMAGE_MAX_AGE_DAYS. Returns count deleted."""
    img_dir = STATE_DIR / "thought-images"
    if not img_dir.is_dir():
        return 0
    cutoff = time.time() - (THOUGHT_IMAGE_MAX_AGE_DAYS * 86400)
    deleted = 0
    for f in img_dir.iterdir():
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        except OSError:
            pass
    return deleted
```

- [ ] **Step 2: Call from awareness_tick**

Add at the end of `awareness_tick()`, after writing awareness.json:

```python
# Periodic cleanup — run once per hour (every ~60 ticks)
if getattr(_cleanup_thought_images, '_last_run', 0) < time.monotonic() - 3600:
    n = _cleanup_thought_images()
    if n:
        log(f"cleaned up {n} old thought images")
    _cleanup_thought_images._last_run = time.monotonic()
```

- [ ] **Step 3: Write test**

```python
def test_cleanup_thought_images_deletes_old(tmp_path):
    img_dir = tmp_path / "thought-images"
    img_dir.mkdir()
    old = img_dir / "old.png"
    old.write_bytes(b"x")
    os.utime(old, (0, 0))  # epoch = very old
    new = img_dir / "new.png"
    new.write_bytes(b"x")
    deleted = _cleanup_thought_images()  # needs STATE_DIR override
    assert deleted == 1
    assert new.exists()
    assert not old.exists()
```

- [ ] **Step 4: Run tests and commit**

```bash
git add bin/px-mind tests/test_mind_utils.py
git commit -m "fix: add thought-images cleanup — delete images older than 30 days"
```

---

### Task 9: Make JSONL trimming atomic (MEDIUM)

**Files:**
- Modify: `bin/px-mind:2017-2033` — `append_thought()` trim path

**Context:** The `append_thought()` function trims thoughts.jsonl by reading all lines, slicing, and writing back with `write_text()`. A crash between the truncation and write leaves an empty file. Use `atomic_write()` instead.

- [ ] **Step 1: Fix append_thought trim to use atomic_write**

```python
# OLD (inside append_thought, lines 2028-2032):
if len(lines) > THOUGHTS_LIMIT:
    thoughts_file.write_text(
        "\n".join(lines[-THOUGHTS_LIMIT:]) + "\n", encoding="utf-8"
    )

# NEW:
if len(lines) > THOUGHTS_LIMIT:
    atomic_write(thoughts_file, "\n".join(lines[-THOUGHTS_LIMIT:]) + "\n")
```

- [ ] **Step 2: Run tests and commit**

```bash
source .venv/bin/activate && python -m pytest tests/test_mind_utils.py tests/test_px_mind.py -v
git add bin/px-mind
git commit -m "fix: use atomic_write for JSONL trimming to prevent data loss on crash"
```

---

### Task 10: Bound rate limit store growth (MEDIUM)

**Files:**
- Modify: `src/pxh/api.py` — add hard cap to `_rate_limit_store`

**Context:** The rate limit store is an in-memory dict keyed by IP. While there's a periodic prune every 100 calls, a burst of unique IPs (e.g., bot scan) could grow the dict unboundedly between prune cycles.

- [ ] **Step 1: Add size cap to _check_rate_limit**

After the prune block in `_check_rate_limit()`:

```python
# Hard cap to prevent memory exhaustion from IP scan bursts
_RATE_STORE_MAX = 10000
if len(_rate_limit_store) > _RATE_STORE_MAX:
    # Evict oldest entries
    sorted_ips = sorted(_rate_limit_store, key=lambda k: _rate_limit_store[k][-1] if _rate_limit_store[k] else 0)
    for k in sorted_ips[:len(_rate_limit_store) - _RATE_STORE_MAX]:
        del _rate_limit_store[k]
```

- [ ] **Step 2: Run tests and commit**

```bash
source .venv/bin/activate && python -m pytest tests/test_api.py -v
git add src/pxh/api.py
git commit -m "fix: cap rate limit store at 10k entries to bound memory growth"
```

---

### Task 11: Update .gitignore for missing state files (MEDIUM)

**Files:**
- Modify: `.gitignore`

**Context:** 10 state files are not covered by .gitignore: `exploring.json`, `feed.json`, `post_queue.jsonl`, `px-post-cursor.json`, `px-post.pid`, `px-post-status.json`, `thought-images/`, `token_usage.json`, `pin_lockout.json`, and temp files.

- [ ] **Step 1: Add missing patterns to .gitignore**

Append to the state section of `.gitignore`:

```gitignore
state/exploring.json
state/feed.json
state/post_queue.jsonl
state/px-post-cursor.json
state/px-post.pid
state/px-post-status.json
state/thought-images/
state/token_usage.json
state/pin_lockout.json
state/*.tmp
state/.*.tmp
```

- [ ] **Step 2: Remove tracked files if any are committed**

```bash
# Check if any are tracked
git ls-files state/exploring.json state/feed.json state/post_queue.jsonl state/px-post-cursor.json state/px-post.pid state/px-post-status.json state/token_usage.json state/pin_lockout.json
# If any show up, remove from index:
# git rm --cached <file>
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add missing state files to .gitignore"
```

---

## Dependency Order

```
Task 1 (DST)           — no deps, highest priority
Task 2 (exploring.json) — no deps
Task 3 (atomic_write)   — no deps; Task 9 depends on this
Task 4 (FileLock timeout) — no deps
Task 5 (PID guards)     — no deps
Task 6 (subprocess kill) — no deps
Task 7 (PIN per-IP)     — no deps
Task 8 (image cleanup)  — no deps
Task 9 (JSONL trim)     — depends on Task 3 (uses atomic_write)
Task 10 (rate limit cap) — no deps
Task 11 (.gitignore)    — no deps, can run any time
```

Tasks 1–8, 10, 11 are independent and can be parallelised. Task 9 must run after Task 3.

---

## Not Addressed (deferred)

These findings from the QA report are acknowledged but deferred:

| # | Finding | Reason |
|---|---------|--------|
| 14 | JSONL reads entire file on every tick | Optimisation, not a bug; 10k-line cap limits impact |
| 15 | PID-file stop/start can kill unrelated processes | Systemd `Restart=always` makes this very unlikely; PID reuse race window is tiny |
| 16 | yield_alive proceeds regardless if px-alive doesn't exit | yield_alive sends SIGUSR1 → px-alive exits within 1s; non-issue in practice |
| 17 | Log rotation duplicated across files | Refactor/DRY suggestion; not a bug |
| 18 | Two divergent atomic_write implementations | Addressed by Task 3 |
| Sug | validate_action() 230-line if/elif | Refactor suggestion; works correctly |
| Sug | px-mind 3100 lines in heredoc | Architectural debt; extraction plan already exists (2026-03-16) |
| Sug | LOG_DIR to tmpfs | Ops change, not code |
| Sug | Public chat prompt injection | Rate-limited + sandboxed Claude call; low risk |
| Sug | CORS allow_headers=["*"] | Internal network only; low risk |
| Sug | photos/{filename} unauthenticated | Intentional — public photo sharing |
