import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_ROOT = PROJECT_ROOT / "logs_test"
LOG_ROOT.mkdir(exist_ok=True)

def run(cmd, extra_env=None):
    env = os.environ.copy()
    env.setdefault("PROJECT_ROOT", str(PROJECT_ROOT))
    env.setdefault("PX_BYPASS_SUDO", "1")
    env.setdefault("LOG_DIR", str(LOG_ROOT))
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    return json.loads(result.stdout.strip())

def test_px_diagnostics_dry_run(tmp_path):
    env = {
        "PX_DRY": "1",
        "PX_SESSION_PATH": str(tmp_path / "session.json"),
    }
    summary = run(["bin/px-diagnostics", "--no-motion", "--short"], env)
    assert summary["status"] == "ok"
    assert summary["dry"] is True
    assert any(check["name"] == "status" for check in summary["checks"])

def test_px_dance_dry_run(tmp_path):
    env = {
        "PX_DRY": "1",
        "PX_SESSION_PATH": str(tmp_path / "session.json"),
    }
    summary = run(["bin/px-dance", "--voice", "Demo"], env)
    assert summary["status"] == "ok"
    assert summary["dry"] is True
    names = [entry["name"] for entry in summary["sequence"]]
    assert names[0] == "voice" and "circle" in names and "figure8" in names
