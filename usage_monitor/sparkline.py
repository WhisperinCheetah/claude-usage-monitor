"""Bucket usage records into fixed time bins for the widget's sparkline."""
from datetime import timedelta

from usage_monitor import pricing

# key -> (number of buckets, seconds per bucket)
RANGES = [
    ("1h", 12, 300),     # last hour, 5-minute bars
    ("24h", 24, 3600),   # last day, hourly bars
    ("7d", 7, 86400),    # last week, daily bars
    ("30d", 30, 86400),  # last 30 days, daily bars
]
_BY_KEY = {k: (n, s) for k, n, s in RANGES}


def range_keys():
    return [k for k, _, _ in RANGES]


def next_range(key: str) -> str:
    keys = range_keys()
    i = keys.index(key) if key in keys else 0
    return keys[(i + 1) % len(keys)]


def bucketize(records, now, range_key: str, mode: str):
    """Per-bucket cost over the range, oldest bucket first (length == n)."""
    n, secs = _BY_KEY.get(range_key, _BY_KEY["24h"])
    start = now - timedelta(seconds=n * secs)
    out = [0.0] * n
    for r in records:
        if r.timestamp < start or r.timestamp > now:
            continue
        idx = int((r.timestamp - start).total_seconds() // secs)
        idx = max(0, min(idx, n - 1))
        out[idx] += pricing.cost_for(
            r.model, r.input, r.output, r.cache_creation, r.cache_read, mode
        )
    return out
