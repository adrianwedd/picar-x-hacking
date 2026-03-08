import json
import pytest
from pxh.voice_loop import build_model_prompt, validate_action, VoiceLoopError


def test_build_model_prompt_includes_highlights():
    system_prompt = "SYSTEM"
    state = {
        "mode": "live",
        "confirm_motion_allowed": True,
        "wheels_on_blocks": True,
        "battery_pct": 72,
        "battery_ok": True,
        "last_motion": "px-circle",
        "last_action": "tool_circle",
        "last_weather": {
            "summary": "At Grove, it's 12 degrees."},
        "history": [
            {"ts": "t1", "event": "status"},
            {"ts": "t2", "event": "circle"},
            {"ts": "t3", "event": "weather"},
            {"ts": "t4", "event": "voice"},
        ],
    }
    prompt = build_model_prompt(system_prompt, state, "Weather now")
    assert "Current highlights:" in prompt
    assert '"mode": "live"' in prompt
    assert 'last_weather_summary' in prompt
    assert 'Recent events:' in prompt
    assert '"event": "weather"' in prompt
    assert 'User transcript: Weather now' in prompt


def test_validate_action_rejects_non_numeric_params():
    """Malformed numeric params should raise VoiceLoopError, not ValueError."""
    with pytest.raises(VoiceLoopError, match="invalid numeric"):
        validate_action({"tool": "tool_circle", "params": {"speed": "fast"}})
    with pytest.raises(VoiceLoopError, match="invalid numeric"):
        validate_action({"tool": "tool_drive", "params": {"speed": None, "direction": "forward"}})
    with pytest.raises(VoiceLoopError, match="invalid numeric"):
        validate_action({"tool": "tool_look", "params": {"pan": "left"}})


def test_validate_action_accepts_string_numbers():
    """LLMs sometimes send numbers as strings — should still work."""
    tool, env = validate_action({"tool": "tool_circle", "params": {"speed": "30", "duration": "6"}})
    assert tool == "tool_circle"
    assert env["PX_SPEED"] == "30"


def test_validate_action_rejects_unknown_tool():
    with pytest.raises(VoiceLoopError, match="unsupported tool"):
        validate_action({"tool": "tool_hack_nasa", "params": {}})
