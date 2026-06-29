"""Bucket usage records into fixed time bins for the widget's sparkline.

Buckets are *calendar-aligned* to the timezone of ``now``: day ranges reset at
local midnight (00:00) and sub-day ranges at clock multiples of the bucket size,
so the newest bar is the current (partial) day/hour rather than a window that
trails ``now`` by an arbitrary offset. Pass a timezone-aware ``now`` (the widget
passes local time) — alignment follows ``now.tzinfo``.
"""
import math
from datetime import timedelta

from usage_monitor import pricing

# key -> (number of buckets, seconds per bucket, unit).
# unit "day" resets at local midnight; "sub" aligns to clock multiples of secs.
RANGES = [
    ("1h", 12, 300, "sub"),     # last hour, 5-minute bars
    ("12h", 12, 3600, "sub"),   # last 12 hours, hourly bars
    ("24h", 24, 3600, "sub"),   # last day, hourly bars
    ("7d", 7, 86400, "day"),    # last week, daily bars (per calendar day)
    ("30d", 30, 86400, "day"),  # last 30 days, daily bars (per calendar day)
]
_BY_KEY = {k: (n, s, u) for k, n, s, u in RANGES}


def range_keys():
    return [k for k, *_ in RANGES]


def next_range(key: str) -> str:
    keys = range_keys()
    i = keys.index(key) if key in keys else 0
    return keys[(i + 1) % len(keys)]


def _bucket_index(ts, now, n, secs, unit):
    """Calendar-aligned bucket index for ``ts``, or None if outside the range.

    The newest bucket (index ``n - 1``) is the one containing ``now``.
    """
    ts = ts.astimezone(now.tzinfo)
    if unit == "day":
        # Whole calendar days back from today, in now's timezone.
        idx = (n - 1) + (ts.date() - now.date()).days
    else:
        # Start of the current bucket: a clock multiple of `secs` since local
        # midnight (e.g. the top of the current hour). The oldest bucket starts
        # (n-1) buckets earlier; math.floor keeps older records out (idx < 0).
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed = int((now - midnight).total_seconds())
        cur_start = midnight + timedelta(seconds=(elapsed // secs) * secs)
        start = cur_start - timedelta(seconds=(n - 1) * secs)
        idx = math.floor((ts - start).total_seconds() / secs)
    return idx if 0 <= idx < n else None


def bucketize(records, now, range_key: str, mode: str):
    """Per-bucket cost over the range, oldest bucket first (length == n)."""
    n, secs, unit = _BY_KEY.get(range_key, _BY_KEY["24h"])
    out = [0.0] * n
    for r in records:
        idx = _bucket_index(r.timestamp, now, n, secs, unit)
        if idx is None:
            continue
        out[idx] += pricing.cost_for(
            r.model, r.input, r.output, r.cache_creation, r.cache_read, mode
        )
    return out
