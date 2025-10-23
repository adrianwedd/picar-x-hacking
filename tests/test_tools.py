import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


LOG_ROOT = PROJECT_ROOT / "logs_test"
LOG_ROOT.mkdir(exist_ok=True)
def run_tool(args, extra_env=None):
    env = os.environ.copy()
    env.setdefault("PROJECT_ROOT", str(PROJECT_ROOT))
    env.setdefault("LOG_DIR", str(LOG_ROOT))
    env.setdefault("PX_BYPASS_SUDO", "1")
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    return result.stdout.strip()


def parse_json(output: str):
    return json.loads(output.splitlines()[-1])


def test_tool_status_dry_run():
    stdout = run_tool(["bin/tool-status"], {"PX_DRY": "1"})
    payload = parse_json(stdout)
    assert payload["status"] == "ok"
    assert payload["dry"] is True


def test_tool_circle_dry_run():
    stdout = run_tool(
        ["bin/tool-circle"],
        {"PX_DRY": "1", "PX_SPEED": "26", "PX_DURATION": "3"},
    )
    payload = parse_json(stdout)
    assert payload["dry"] is True
    assert payload["speed"] == 26
    assert payload["duration"] == 3.0


def test_tool_figure8_dry_run():
    stdout = run_tool(
        ["bin/tool-figure8"],
        {"PX_DRY": "1", "PX_SPEED": "27", "PX_DURATION": "3", "PX_REST": "0.5"},
    )
    payload = parse_json(stdout)
    assert payload["dry"] is True
    assert payload["speed"] == 27
    assert payload["rest"] == 0.5


def test_tool_stop_dry_run():
    stdout = run_tool(["bin/tool-stop"], {"PX_DRY": "1"})
    payload = parse_json(stdout)
    assert payload["status"] == "ok"
    assert payload["dry"] is True


def test_tool_voice_dry_run():
    stdout = run_tool(
        ["bin/tool-voice"],
        {"PX_DRY": "1", "PX_TEXT": "Hello PiCar-X"},
    )
    payload = parse_json(stdout)
    assert payload["status"] == "ok"
    assert payload["dry"] is True
    assert payload.get("note", "").startswith("voice output suppressed")


def test_tool_weather_dry_run():
    stdout = run_tool(["bin/tool-weather"], {"PX_DRY": "1"})
    payload = parse_json(stdout)
    assert payload["status"] == "dry-run"
    assert "Dry-run" in payload["summary"]
