import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(cmd, log_dir):
    env = os.environ.copy()
    env.setdefault('PROJECT_ROOT', str(PROJECT_ROOT))
    env['LOG_DIR'] = str(log_dir)
    env.setdefault('PX_BYPASS_SUDO', '1')
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


def write_health(entries, log_dir):
    log = log_dir / 'tool-health.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('\n'.join(json.dumps(entry) for entry in entries) + '\n', encoding='utf-8')


def test_px_health_report_text(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    entries = [
        {"ts": "2025-10-26T19:14:21Z", "status": "ok", "dry": True, "telemetry": {"battery_pct": 66, "speaker_ok": True}},
        {"ts": "2025-10-26T19:15:21Z", "status": "warn", "dry": False, "telemetry": {"battery_pct": 30, "motors_ok": False}},
    ]
    write_health(entries, log_dir)
    result = run(['bin/px-health-report', '--limit', '2'], log_dir)
    output = result.stdout.strip()
    assert 'status=warn' in output
    assert 'battery=30' in output


def test_px_health_report_json(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    entries = [
        {"ts": "2025-10-26T19:20:00Z", "status": "ok", "dry": True, "telemetry": {"battery_pct": 70}},
    ]
    write_health(entries, log_dir)
    result = run(['bin/px-health-report', '--json'], log_dir)
    payload = json.loads(result.stdout.strip())
    assert isinstance(payload['entries'], list)
    assert payload['entries'][0]['telemetry']['battery_pct'] == 70
