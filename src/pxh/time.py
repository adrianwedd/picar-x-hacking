from __future__ import annotations

import datetime as _dt


def utc_timestamp() -> str:
    """Return an ISO 8601 timestamp (UTC) with second precision."""
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
