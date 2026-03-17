# Extract px-mind from Bash Heredoc into src/pxh/mind.py — Design Spec

**Date:** 2026-03-18
**Issue:** #78
**Scope:** Relocate all Python code from `bin/px-mind` heredoc into `src/pxh/mind.py`; consolidate duplicate `atomic_write`; update 3 test files to use direct imports

---

## Problem

`bin/px-mind` is a 3384-line file where lines 1–18 are bash and lines 19–3384 are a Python heredoc. This means:

- **No IDE support** — no autocomplete, type checking, or go-to-definition for 57 functions
- **Fragile testing** — three test files use a hack: parse the heredoc, stub pxh imports into `sys.modules`, run the source into a globals dict, then access functions as dict keys
- **Duplicated code** — `atomic_write()` exists in both `bin/px-mind` and `src/pxh/state.py` with near-identical implementations (both now have `fsync` after commit 84adbce)
- **Refactoring risk** — any change to px-mind's 57 functions risks breaking the test hack if import structure shifts

---

## Design

### Overview

Move all Python code from the heredoc verbatim into `src/pxh/mind.py`. Replace `bin/px-mind` with a ~15-line thin launcher. Update tests to use direct imports. Consolidate `atomic_write` into `state.py`.

No logic changes. No restructuring of global state. No new abstractions. This is a relocation, not a rewrite.

### Commit 1: Consolidate `atomic_write` in state.py

**`src/pxh/state.py`:**
- Rename `_atomic_write()` to `atomic_write()` (drop leading underscore, make public export)
- No signature change — it already accepts `(path: Path, content: str) -> None`
- Both implementations now have `f.flush() + os.fsync()` (state.py gained this in commit 84adbce), so the consolidation is a clean dedup with no behavioural difference

**Why a separate commit:** Independently valuable (#120 partial), independently revertible, and mechanically distinct from the extraction.

### Commit 2: Extract mind.py + thin launcher + test migration

#### New file: `src/pxh/mind.py`

All ~3300 lines of Python from the heredoc, with three targeted changes:

**1. `PROJECT_ROOT` path calculation:**

In the heredoc, `Path(__file__)` resolves to `bin/px-mind`, so `.parent.parent` gives the project root. In `src/pxh/mind.py`, the path is `src/pxh/mind.py`, so the fallback needs `.parent.parent.parent`. Use the env var (always set by px-env) with a corrected fallback:

```python
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent.parent))
```

**2. Import `atomic_write` from state.py:**

Replace the local `atomic_write()` definition with:

```python
from pxh.state import atomic_write
```

All call sites remain unchanged — same function name, same signature.

**3. `_reset_state()` function for test isolation:**

New function that resets all ~25 mutable module globals to their default values. Called by a pytest fixture before each test to prevent cross-test contamination from shared module state.

The function uses `global` declarations for each mutable variable and resets them to their initial values (None/0.0 for caches, empty list/dict for collections, False for flags, 0.4/0.0 for mood valence/arousal).

**Everything else is verbatim.** All 57 functions, 70+ constants, imports, docstrings — copied as-is.

#### Replaced file: `bin/px-mind`

Thin bash launcher (~15 lines):

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

python -m pxh.mind "$@"
```

This follows the same pattern as `bin/px-api-server`. The venv python is used (px-env activates it), PYTHONPATH includes both `$PROJECT_ROOT/src` and `/home/pi/picar-x` (for `robot_hat` in `_play_alarm_beeps()`).

#### Updated file: `tests/test_mind_utils.py`

Remove the `_load_mind_helpers()` heredoc-parsing hack. Replace with direct imports:

```python
from pxh.mind import (
    compute_obi_mode, _daytime_action_hint, classify_time_period,
    text_similarity, nearest_mood, apply_mood_momentum, filter_battery,
    extract_json, notes_file_for_persona, thoughts_file_for_persona,
    _reset_state,
)
```

Add a fixture that calls `_reset_state()` before each test to prevent cross-test contamination from mutable globals.

#### Updated file: `tests/test_mind_fallback.py`

Same pattern — remove heredoc-parsing hack, import directly, use `_reset_state()` fixture.

#### Unchanged file: `tests/test_px_mind.py`

Already tests via subprocess (`bin/px-mind --dry-run`). No changes needed — it validates the full launcher-to-module path end-to-end.

#### Unchanged file: `src/pxh/__init__.py`

Do NOT add `mind` to `__init__.py` imports. `pxh.mind` is a heavy module (network connections, filesystem access, 30+ global state variables). Importing it has side effects. Only import it explicitly when needed.

---

## What Does NOT Change

- **All function signatures** — verbatim copy, no renames
- **Global state pattern** — module-level mutable variables, no dataclass/object restructuring
- **`log()` function** — stays in mind.py (px-mind-specific, writes to `logs/px-mind.log`)
- **`robot_hat` import** — stays in `_play_alarm_beeps()` inside try/except; resolves via PYTHONPATH
- **Daemon behaviour** — argparse, signal handlers, PID file, main loop — all identical
- **systemd service** — `bin/px-mind` is still the entry point, still runs as user `pi`

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Large diff (~3400 lines) | No logic changes — relocation only. Single `git revert` rolls back. |
| `__file__` path breaks | Use `PROJECT_ROOT` env var (always set by px-env) with `.parent.parent.parent` fallback |
| Test flakiness from shared module state | `_reset_state()` + per-test fixture |
| `robot_hat` import fails under venv | Already in try/except; PYTHONPATH includes `/home/pi/picar-x` via px-env |
| Other bin scripts' `atomic_write` diverges | Only px-mind has a duplicate. px-alive and px-wake-listen use their own `log()` but not `atomic_write`. |

---

## Smoke Test

After deployment on Pi:

```bash
bin/px-mind --dry-run          # 3-cycle dry run — validates full path
python -m pytest tests/test_mind_utils.py tests/test_mind_fallback.py tests/test_px_mind.py -v
sudo systemctl restart px-mind && journalctl -u px-mind -f  # live service check
```

---

## Out of Scope

- Splitting mind.py into submodules (awareness.py, reflection.py, etc.) — future work
- Deduplicating `log()` across bin scripts (#120) — future work
- Adding test coverage for cognitive loop (#123) — depends on this extraction landing first
- MCP server (#36) — separate feature, no dependency on this work
