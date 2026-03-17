# px-mind Extraction Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all Python code from `bin/px-mind` heredoc into `src/pxh/mind.py`, making it a proper importable module with IDE support and direct-import testing.

**Architecture:** Full extraction — 3300 lines of Python relocated verbatim from bash heredoc into `src/pxh/mind.py`. Thin bash launcher replaces the heredoc. Two test files migrated from heredoc-parsing hack to direct imports. `atomic_write` consolidated into `state.py`.

**Tech Stack:** Python 3.11, pytest, filelock, bash

**Spec:** `docs/superpowers/specs/2026-03-18-px-mind-extraction-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/pxh/state.py` | Modify | Rename `_atomic_write` → `atomic_write` (public export) |
| `src/pxh/mind.py` | Create | All px-mind Python code (3300 lines) — cognitive daemon module |
| `bin/px-mind` | Replace | Thin ~15-line bash launcher |
| `tests/test_mind_utils.py` | Modify | Direct imports replacing heredoc-parsing hack |
| `tests/test_mind_fallback.py` | Modify | Direct imports replacing heredoc-parsing hack |
| `tests/test_px_mind.py` | Unchanged | Subprocess tests — validates launcher→module path |
| `src/pxh/__init__.py` | Unchanged | Do NOT auto-import mind (heavy module with side effects) |

---

### Task 1: Consolidate `atomic_write` in state.py

**Files:**
- Modify: `src/pxh/state.py:21` (function def) and lines 101, 103, 116, 124, 152 (call sites)

- [ ] **Step 1: Verify both implementations are identical**

Compare the two `atomic_write` functions. Both should have `mkstemp` + `fsync` + `os.replace` + ownership preservation + cleanup on error. The px-mind version (bin/px-mind:699–731) wraps `dir=` in `str()` and uses `str(path)` in `os.replace` — otherwise identical.

- [ ] **Step 2: Rename `_atomic_write` to `atomic_write` in state.py**

In `src/pxh/state.py`, find-and-replace `_atomic_write` → `atomic_write`. This touches 6 locations:
- Line 21: function definition
- Lines 101, 103, 116, 124, 152: internal call sites

- [ ] **Step 3: Run state.py tests**

```bash
source .venv/bin/activate && python -m pytest tests/test_state.py -v
```

Expected: All pass — rename is purely cosmetic.

- [ ] **Step 4: Commit**

```bash
git add src/pxh/state.py
git commit -m "refactor: make atomic_write public in state.py (#78, #120)

Drop leading underscore so pxh.mind (and future callers) can import it.
Internal call sites updated. No behaviour change."
```

---

### Task 2: Create `src/pxh/mind.py` from heredoc

**Files:**
- Create: `src/pxh/mind.py`
- Source: `bin/px-mind` lines 20–3383 (Python code inside heredoc)

- [ ] **Step 1: Extract the Python block from the heredoc**

```bash
sed -n '20,3383p' bin/px-mind > src/pxh/mind.py
```

- [ ] **Step 2: Fix `PROJECT_ROOT` path calculation**

Find the line (originally line 60 in bin/px-mind):

```python
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
```

Change to (extra `.parent` for `src/pxh/` depth):

```python
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent.parent))
```

- [ ] **Step 3: Replace local `atomic_write` with import from state.py**

Delete the `atomic_write()` function definition (originally lines 699–731 in bin/px-mind — find the `def atomic_write(path: Path, data: str)` block and delete it entirely, including the docstring and all body lines through the final `raise`).

Add `atomic_write` to the existing `pxh.state` import. Find:

```python
from pxh.state import load_session, update_session
```

Change to:

```python
from pxh.state import atomic_write, load_session, update_session
```

All 6 call sites (`atomic_write(AWARENESS_FILE, ...`, etc.) keep the same name — no further changes.

- [ ] **Step 4: Add `_reset_state()` function for test isolation**

Add this function after the last mutable global declaration block (after `_tmux_turn_count = 0`). It resets all 27 mutable module globals:

```python
def _reset_state():
    """Reset all mutable module globals to defaults. Called by test fixtures."""
    global _battery_history, _battery_glitch_count, _battery_glitch_first_mono
    global _cached_weather, _last_weather_fetch
    global _cached_ha, _last_ha_fetch
    global _cached_ha_calendar, _last_ha_calendar_fetch
    global _cached_ha_sleep, _last_ha_sleep_fetch
    global _cached_ha_routines, _last_ha_routines_fetch
    global _cached_ha_context, _last_ha_context_fetch
    global _cached_calendar, _last_calendar_fetch
    global _last_spoken_text, _last_morning_fact_date
    global _mood_history, _last_reactive_phrases
    global _consecutive_reflection_failures, _reflection_offline_spoken
    global _mood_v, _mood_a
    global _time_period_start_mono, _last_image_cleanup
    global _tmux_ready, _tmux_timeout_count, _tmux_turn_count

    _battery_history = []
    _battery_glitch_count = 0
    _battery_glitch_first_mono = 0.0
    _cached_weather = None
    _last_weather_fetch = 0.0
    _cached_ha = None
    _last_ha_fetch = 0.0
    _cached_ha_calendar = None
    _last_ha_calendar_fetch = 0.0
    _cached_ha_sleep = None
    _last_ha_sleep_fetch = 0.0
    _cached_ha_routines = None
    _last_ha_routines_fetch = 0.0
    _cached_ha_context = None
    _last_ha_context_fetch = 0.0
    _cached_calendar = None
    _last_calendar_fetch = 0.0
    _last_spoken_text = ""
    _last_morning_fact_date = ""
    _mood_history = []
    _last_reactive_phrases = {}
    _consecutive_reflection_failures = 0
    _reflection_offline_spoken = False
    _mood_v = 0.4
    _mood_a = 0.0
    _time_period_start_mono = 0.0
    _last_image_cleanup = 0.0
    _tmux_ready = False
    _tmux_timeout_count = 0
    _tmux_turn_count = 0
```

- [ ] **Step 5: Verify `from __future__ import annotations` is the first import**

Check that the first non-comment, non-docstring line is `from __future__ import annotations`.

- [ ] **Step 6: Verify `if __name__` guard exists at end of file**

Check that the last lines of mind.py are:

```python
if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 7: Verify mind.py parses without syntax errors**

```bash
source .venv/bin/activate && python -c "import ast; ast.parse(open('src/pxh/mind.py').read()); print('OK')"
```

Expected: `OK`

---

### Task 3: Replace `bin/px-mind` with thin launcher

**Files:**
- Replace: `bin/px-mind` (entire file — 3384 lines → ~15 lines)

- [ ] **Step 1: Write the thin launcher**

Replace `bin/px-mind` entirely with:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/px-env"

# Load .env secrets (PX_HA_TOKEN, PX_BSKY_*, etc.)
ENV_FILE="$PROJECT_ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

exec python -m pxh.mind "$@"
```

- [ ] **Step 2: Ensure launcher is executable**

```bash
chmod +x bin/px-mind
```

- [ ] **Step 3: Smoke test — dry run**

```bash
source .venv/bin/activate && PX_DRY=1 bin/px-mind --dry-run 2>&1 | head -20
```

Expected: Starts, prints "starting pid=...", runs 3 awareness cycles, exits 0.

---

### Task 4: Migrate `tests/test_mind_utils.py` to direct imports

**Files:**
- Modify: `tests/test_mind_utils.py`

- [ ] **Step 1: Replace the heredoc-parsing hack with direct imports**

Delete the `_load_mind_helpers()` function (lines 14–85 of the current file) and any `_MIND = _load_mind_helpers()` call.

Replace the top of the file with direct imports. Keep existing `import json as _json`, `import time as _time`, `from unittest.mock import ...` etc. Add:

```python
from pxh.mind import (
    _daytime_action_hint,
    _reset_state,
    apply_mood_momentum,
    classify_time_period,
    compute_obi_mode,
    extract_json,
    filter_battery,
    nearest_mood,
    notes_file_for_persona,
    text_similarity,
    thoughts_file_for_persona,
)
```

Scan the rest of the file for any additional `_MIND["..."]` references and add those functions/constants to the import list. Common ones: `_fetch_frigate_presence`, `_pick_reflection_seed`, `_pick_spark_angles`, `_cleanup_thought_images`, `load_recent_thoughts`, `append_thought`, `auto_remember`, `awareness_tick`, and constants like `VALID_ACTIONS`, `VALID_MOODS`, `TOPIC_SEEDS`, `SPARK_ANGLES`, `HOBART_TZ`, `FRIGATE_CAMERA_ROOMS`, `THOUGHTS_LIMIT`, `NOTES_LIMIT`, `SALIENCE_THRESHOLD`.

- [ ] **Step 2: Replace all `_MIND["name"]` references with direct names**

Search for `_MIND[` throughout the file. Every `_MIND["compute_obi_mode"]` becomes `compute_obi_mode`. Every `_MIND["VALID_ACTIONS"]` becomes `VALID_ACTIONS`.

- [ ] **Step 3: Add `_reset_state` autouse fixture**

Add near the top of the file (after imports):

```python
@pytest.fixture(autouse=True)
def _clean_mind_state():
    """Reset px-mind module globals before each test."""
    _reset_state()
    yield
    _reset_state()
```

- [ ] **Step 4: Remove leftover imports from the hack**

Remove `import sys`, `import types` if they were only used by the deleted `_load_mind_helpers()`. Keep them if other code uses them.

- [ ] **Step 5: Run the tests**

```bash
source .venv/bin/activate && python -m pytest tests/test_mind_utils.py -v 2>&1 | tail -30
```

Expected: All tests pass. Fix any `ImportError` or `NameError` by adding missing names to the import list.

---

### Task 5: Migrate `tests/test_mind_fallback.py` to direct imports

**Files:**
- Modify: `tests/test_mind_fallback.py`

- [ ] **Step 1: Replace the heredoc-parsing hack with direct imports**

Delete the `_load_mind()` function (lines 11–71) and the `_MIND = _load_mind()` call (line 74).

Replace the top of the file with:

```python
"""Tests for px-mind three-tier LLM fallback: Claude -> M1 Ollama -> local Ollama."""
from __future__ import annotations

import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from pxh.mind import call_llm, _reset_state
```

- [ ] **Step 2: Replace `_MIND["call_llm"]` references**

In each test function, find lines like `call_llm = _MIND["call_llm"]` and delete them. The `call_llm` function is now imported at module level.

- [ ] **Step 3: Add `_reset_state` autouse fixture**

```python
@pytest.fixture(autouse=True)
def _clean_mind_state():
    _reset_state()
    yield
    _reset_state()
```

- [ ] **Step 4: Run the tests**

```bash
source .venv/bin/activate && python -m pytest tests/test_mind_fallback.py -v
```

Expected: All 4 tests pass.

---

### Task 6: Run full test suite and commit extraction

**Files:** All files from Tasks 2–5

- [ ] **Step 1: Run the three mind test files together**

```bash
source .venv/bin/activate && python -m pytest tests/test_mind_utils.py tests/test_mind_fallback.py tests/test_px_mind.py -v 2>&1 | tail -20
```

Expected: All pass. `test_px_mind.py` validates the launcher → `python -m pxh.mind` → module path.

- [ ] **Step 2: Run the full test suite**

```bash
source .venv/bin/activate && python -m pytest -x -q 2>&1 | tail -10
```

Expected: 459+ tests pass. Only expected failure is `test_tool_play_sound` (live hardware test).

- [ ] **Step 3: Commit the extraction**

```bash
git add src/pxh/mind.py bin/px-mind tests/test_mind_utils.py tests/test_mind_fallback.py
git commit -m "refactor: extract px-mind heredoc into src/pxh/mind.py (#78)

Move 3300 lines of Python from bin/px-mind bash heredoc into a proper
importable module. bin/px-mind is now a 15-line thin launcher.

Changes from verbatim copy:
- PROJECT_ROOT fallback uses .parent.parent.parent (src/pxh/ depth)
- atomic_write imported from pxh.state (consolidated in prior commit)
- _reset_state() added for test isolation of 27 mutable globals

Test migration:
- test_mind_utils.py: heredoc-parsing hack replaced with direct imports
- test_mind_fallback.py: heredoc-parsing hack replaced with direct imports
- test_px_mind.py: unchanged (subprocess tests validate launcher path)

Closes #78"
```

- [ ] **Step 4: Push**

```bash
git push
```

---

### Task 7: Post-extraction verification on Pi

- [ ] **Step 1: Verify systemd service starts**

```bash
sudo systemctl restart px-mind
sleep 3
journalctl -u px-mind --no-pager -n 20
```

Expected: Service starts, logs show "starting pid=..." with awareness ticks.

- [ ] **Step 2: Verify dry-run end-to-end**

```bash
bin/px-mind --dry-run
```

Expected: 3 awareness cycles, thoughts generated, exits 0.

- [ ] **Step 3: Check state files were created**

```bash
ls -la state/awareness.json state/thoughts.jsonl
```

Expected: Both exist with recent timestamps.
