"""Tests for px-mind utility functions: _daytime_action_hint and compute_obi_mode."""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


def _load_mind_helpers():
    """Parse bin/px-mind and extract the helper functions we want to test."""
    src = (PROJECT_ROOT / "bin" / "px-mind").read_text()

    # Find the heredoc Python block (everything between <<'PY' and the closing PY)
    start = src.index("<<'PY'\n") + len("<<'PY'\n")
    end = src.rindex("\nPY\n")
    py_src = src[start:end]

    import datetime as _dt

    stub_keys = ("pxh", "pxh.state", "pxh.logging", "pxh.time")
    saved_modules = {k: sys.modules.get(k) for k in stub_keys}

    # Stub out hardware/network imports only for the duration of exec
    stubs_pxh = types.ModuleType("pxh")
    stubs_state = types.ModuleType("pxh.state")
    stubs_state.load_session = lambda: {}
    stubs_state.update_session = lambda **kw: None
    stubs_state.save_session = lambda s: None
    stubs_logging = types.ModuleType("pxh.logging")
    stubs_logging.log_event = lambda *a, **kw: None
    stubs_time = types.ModuleType("pxh.time")
    stubs_time.utc_timestamp = lambda: _dt.datetime.now(_dt.timezone.utc).isoformat()

    sys.modules["pxh"] = stubs_pxh
    sys.modules["pxh.state"] = stubs_state
    sys.modules["pxh.logging"] = stubs_logging
    sys.modules["pxh.time"] = stubs_time

    env_patch = {
        "PROJECT_ROOT": str(PROJECT_ROOT),
        "LOG_DIR": str(PROJECT_ROOT / "logs"),
        "PX_STATE_DIR": str(PROJECT_ROOT / "state"),
        "MIND_BACKEND": "auto",
        "PX_OLLAMA_HOST": "http://localhost:11434",
    }
    old_env = {k: os.environ.get(k) for k in env_patch}
    for k, v in env_patch.items():
        os.environ[k] = v

    globs: dict = {"__file__": str(PROJECT_ROOT / "bin" / "px-mind")}
    try:
        exec(compile(py_src, "bin/px-mind", "exec"), globs)  # noqa: S102
    finally:
        # Restore sys.modules to avoid polluting other test imports
        for k, old_mod in saved_modules.items():
            if old_mod is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = old_mod
        for k, old_v in old_env.items():
            if old_v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old_v

    return globs


_MIND = _load_mind_helpers()
_daytime_action_hint = _MIND["_daytime_action_hint"]
compute_obi_mode = _MIND["compute_obi_mode"]


# ---------------------------------------------------------------------------
# _daytime_action_hint
# ---------------------------------------------------------------------------


def test_daytime_hint_daytime():
    """During Obi's waking hours (7–19) the hint pushes toward comment/greet."""
    hint = _daytime_action_hint(hour_override=10)
    assert "comment" in hint or "greet" in hint


def test_daytime_hint_night():
    """Overnight the hint pushes toward remember/wait."""
    hint = _daytime_action_hint(hour_override=2)
    assert "remember" in hint or "wait" in hint


def test_daytime_hint_boundary_start():
    """Hour 7 (day start) → daytime hint."""
    hint = _daytime_action_hint(hour_override=7)
    assert "comment" in hint or "greet" in hint


def test_daytime_hint_boundary_end():
    """Hour 20 (day end) → night hint."""
    hint = _daytime_action_hint(hour_override=20)
    assert "remember" in hint or "wait" in hint


# ---------------------------------------------------------------------------
# compute_obi_mode
# ---------------------------------------------------------------------------


def test_obi_mode_absent_at_night():
    """Silent + no one near + night → absent."""
    awareness = {"ambient_sound": {"level": "silent"}, "sonar_cm": 80}
    mode = compute_obi_mode(awareness, hour_override=3)
    assert mode == "absent"


def test_obi_mode_overloaded():
    """Very close + loud → possibly-overloaded."""
    awareness = {"ambient_sound": {"level": "loud"}, "sonar_cm": 15}
    mode = compute_obi_mode(awareness, hour_override=14)
    assert mode == "possibly-overloaded"


def test_obi_mode_active_daytime_close():
    """Close + loud + daytime → active."""
    awareness = {"ambient_sound": {"level": "loud"}, "sonar_cm": 25}
    mode = compute_obi_mode(awareness, hour_override=10)
    assert mode == "active"


def test_obi_mode_calm_daytime_close_quiet():
    """Close + quiet + daytime → calm."""
    awareness = {"ambient_sound": {"level": "quiet"}, "sonar_cm": 25}
    mode = compute_obi_mode(awareness, hour_override=10)
    assert mode == "calm"


def test_obi_mode_unknown_no_ambient():
    """No ambient data → unknown."""
    awareness = {"sonar_cm": 50}
    mode = compute_obi_mode(awareness, hour_override=10)
    assert mode == "unknown"
