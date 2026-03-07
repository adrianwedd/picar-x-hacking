from __future__ import annotations

import datetime as _dt


def utc_timestamp() -> str:
    """Return an ISO 8601 timestamp (UTC) with second precision."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
