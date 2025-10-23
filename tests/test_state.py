import json
from pathlib import Path

import pxh.state as state

def test_update_session_appends_history(tmp_path, monkeypatch):
    session_file = tmp_path / "session.json"
    monkeypatch.setenv("PX_SESSION_PATH", str(session_file))
    data = state.update_session(
        fields={"mode": "live"}, history_entry={"event": "alpha"}
    )
    assert data["mode"] == "live"
    assert data["history"]
    assert data["history"][0]["event"] == "alpha"

    # Exceed history limit to ensure truncation works
    for idx in range(1, 105):
        state.update_session(history_entry={"event": f"e{idx}"})
    data = state.load_session()
    assert len(data["history"]) == 100
    assert data["history"][0]["event"].startswith("e")


def test_default_state_contains_tracking_fields(tmp_path, monkeypatch):
    session_file = tmp_path / "session.json"
    monkeypatch.setenv("PX_SESSION_PATH", str(session_file))
    defaults = state.default_state()
    expected_keys = {
        "last_weather",
        "last_prompt_excerpt",
        "last_model_action",
        "last_tool_payload",
    }
    assert expected_keys.issubset(defaults.keys())
    # Ensure ensure_session creates file matching template
    state.ensure_session()
    loaded = json.loads(session_file.read_text())
    assert all(key in loaded for key in expected_keys)
