import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_report(args):
    env = os.environ.copy()
    env.setdefault("PROJECT_ROOT", str(PROJECT_ROOT))
    result = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    return result.stdout.strip()


def test_voice_report_json(tmp_path):
    log_path = tmp_path / "tool-voice-transcript.log"
    entries = [
        {
            "tool": "tool_weather",
            "tool_payload": {"summary": "At Grove, it's 12°C.", "battery_pct": 55},
            "voice_result": {"returncode": 0},
        },
        {
            "tool": "tool_status",
            "tool_payload": {"battery_pct": 25},
        },
    ]
    with log_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")

    stdout = run_report(["bin/px-voice-report", "--log", str(log_path), "--json"])
    summary = json.loads(stdout)
    assert summary["total_records"] == 2
    assert summary["tool_counts"]["tool_weather"] == 1
    assert summary["voice_success"] == 1
    assert summary["battery_warnings"] == 1
    assert summary["last_summary"] == "At Grove, it's 12°C."
