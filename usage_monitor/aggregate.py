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


def filter_by_time(records, start: Optional[datetime], end: Optional[datetime]):
    out = []
    for r in records:
        if start is not None and r.timestamp < start:
            continue
        if end is not None and r.timestamp >= end:
            continue
        out.append(r)
    return out


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
