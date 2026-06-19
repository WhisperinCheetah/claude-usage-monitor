"""Timeframe filtering and per-model rollups over usage records."""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from usage_monitor import pricing

TIMEFRAMES = [
    ("session", "Current session"),
    ("today", "Today"),
    ("week", "This week"),
    ("last7days", "Last 7 days"),
    ("month", "This month"),
    ("all", "All-time"),
]


def timeframe_bounds(key: str, now: datetime):
    if key in ("session", "all"):
        return (None, None)
    if key == "today":
        return (now.replace(hour=0, minute=0, second=0, microsecond=0), None)
    if key == "week":
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return (midnight - timedelta(days=now.weekday()), None)
    if key == "month":
        return (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), None)
    if key == "last7days":
        return (now - timedelta(days=7), None)
    return (None, None)


# Recent-spend "delta" windows. 5/10/30/60m are always selectable; larger
# timeframes additionally offer longer windows. Each entry is (key, seconds).
DELTA_WINDOWS = [
    ("1m", 60), ("5m", 300), ("10m", 600), ("30m", 1800), ("60m", 3600),
    ("6h", 21600), ("24h", 86400), ("7d", 604800), ("30d", 2592000),
]
_DELTA_SECONDS = dict(DELTA_WINDOWS)
_ALWAYS = ["1m", "5m", "10m", "30m", "60m"]
_DELTA_BY_TIMEFRAME = {
    "session": _ALWAYS,
    "today": _ALWAYS,
    "week": _ALWAYS + ["6h", "24h"],
    "last7days": _ALWAYS + ["6h", "24h"],
    "month": _ALWAYS + ["6h", "24h", "7d"],
    "all": _ALWAYS + ["6h", "24h", "7d", "30d"],
}
_DELTA_DEFAULT = {
    "session": "5m", "today": "10m", "week": "60m",
    "last7days": "60m", "month": "24h", "all": "24h",
}


def delta_window_options(timeframe_key: str):
    keys = _DELTA_BY_TIMEFRAME.get(timeframe_key, _ALWAYS)
    return [(k, _DELTA_SECONDS[k]) for k in keys]


def delta_default(timeframe_key: str) -> str:
    return _DELTA_DEFAULT.get(timeframe_key, "5m")


def delta_seconds(key: str) -> int:
    return _DELTA_SECONDS.get(key, 300)


def recent_delta(records, now: datetime, window_seconds: int, mode: str) -> float:
    """Cost of usage in the last `window_seconds` (the stock-ticker delta)."""
    start = now - timedelta(seconds=window_seconds)
    recent = filter_by_time(records, start, None)
    return rollup(recent, mode)["total_cost"]


def filter_by_time(records, start: Optional[datetime], end: Optional[datetime]):
    out = []
    for r in records:
        if start is not None and r.timestamp < start:
            continue
        if end is not None and r.timestamp >= end:
            continue
        out.append(r)
    return out


def latest_record(records):
    """The most recent record by timestamp, or None."""
    latest = None
    for r in records:
        if latest is None or r.timestamp > latest.timestamp:
            latest = r
    return latest


def model_by_session(records) -> dict:
    """Map session id -> that session's newest model.

    A transcript file is named ``<session_id>.jsonl``, so the file stem is the
    session id. Used to color each responding-agent dot by its model.
    """
    out = {}          # session_id -> (timestamp, model)
    for r in records:
        sid = Path(r.source_file).stem
        prev = out.get(sid)
        if prev is None or r.timestamp > prev[0]:
            out[sid] = (r.timestamp, r.model)
    return {sid: model for sid, (_, model) in out.items()}


def session_file(paths) -> Optional[Path]:
    newest = None
    newest_mtime = None
    for p in paths:
        p = Path(p)
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if newest_mtime is None or m > newest_mtime:
            newest_mtime = m
            newest = p
    return newest


def filter_by_file(records, path):
    target = str(path)
    return [r for r in records if r.source_file == target]


def rollup(records, mode: str) -> dict:
    total_tokens = 0
    total_cost = 0.0
    by_model = {}
    for r in records:
        tokens = r.input + r.output + r.cache_creation + r.cache_read
        cost = pricing.cost_for(r.model, r.input, r.output, r.cache_creation, r.cache_read, mode)
        total_tokens += tokens
        total_cost += cost
        key = pricing.normalize_model(r.model)
        slot = by_model.setdefault(key, {"tokens": 0, "cost": 0.0})
        slot["tokens"] += tokens
        slot["cost"] += cost
    return {"total_tokens": total_tokens, "total_cost": total_cost, "by_model": by_model}
