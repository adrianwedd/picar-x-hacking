import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_px_session_plan():
    result = subprocess.run(
        ["bin/px-session", "--plan"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
        env={"PROJECT_ROOT": str(PROJECT_ROOT)},
    )
    plan = result.stdout
    assert "tmux new-session" in plan
    assert "tmux attach" in plan
    assert "px-wake" in plan
