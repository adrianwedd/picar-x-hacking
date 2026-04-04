"""Story builder tool tests."""
import json, os


def test_session_has_story_field(isolated_project, monkeypatch):
    """Session template includes obi_story_lines."""
    # Apply isolated env vars so load_session uses the temp session path
    for k, v in isolated_project["env"].items():
        monkeypatch.setenv(k, v)
    from pxh.state import load_session
    s = load_session()
    assert "obi_story_lines" in s
    assert s["obi_story_lines"] == []
