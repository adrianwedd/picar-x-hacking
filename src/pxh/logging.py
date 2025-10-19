from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .time import utc_timestamp

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"


def log_event(name: str, payload: Mapping[str, Any]) -> None:
    """Append a structured log entry under logs/tool-<name>.log."""
    log_path = LOG_DIR / f"tool-{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": utc_timestamp(),
        **payload,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        json.dump(record, handle)
        handle.write("\n")
