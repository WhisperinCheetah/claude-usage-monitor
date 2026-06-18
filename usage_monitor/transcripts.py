"""Discover and parse Claude Code JSONL transcripts into usage records."""
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class UsageRecord:
    timestamp: datetime
    model: str
    input: int
    output: int
    cache_creation: int
    cache_read: int
    message_id: str
    source_file: str


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        # Handle trailing 'Z' (UTC) which fromisoformat rejects on older Pythons.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _record_from_obj(obj: dict, source_file: str) -> Optional[UsageRecord]:
    msg = obj.get("message")
    if not isinstance(msg, dict) or msg.get("role") != "assistant":
        return None
    usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None
    ts = _parse_ts(obj.get("timestamp", ""))
    if ts is None:
        return None
    return UsageRecord(
        timestamp=ts,
        model=msg.get("model", ""),
        input=int(usage.get("input_tokens", 0) or 0),
        output=int(usage.get("output_tokens", 0) or 0),
        cache_creation=int(usage.get("cache_creation_input_tokens", 0) or 0),
        cache_read=int(usage.get("cache_read_input_tokens", 0) or 0),
        message_id=str(msg.get("id", "")),
        source_file=source_file,
    )


def parse_file(path: Path) -> list:
    path = Path(path)
    records = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict):
                    continue
                rec = _record_from_obj(obj, str(path))
                if rec is not None:
                    records.append(rec)
    except OSError:
        return []
    return records


def dedup(records: Iterable) -> list:
    seen = set()
    out = []
    for r in records:
        if r.message_id:
            if r.message_id in seen:
                continue
            seen.add(r.message_id)
        out.append(r)
    return out


def default_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def find_transcripts(projects_dir: Path) -> list:
    projects_dir = Path(projects_dir)
    if not projects_dir.is_dir():
        return []
    return sorted(projects_dir.rglob("*.jsonl"))


class TranscriptCache:
    """Re-parses only files whose (mtime, size) changed since the last load."""

    def __init__(self):
        self._cache = {}  # str(path) -> (mtime, size, records)

    def load(self, paths) -> list:
        records = []
        current_keys = set()
        for path in paths:
            path = Path(path)
            key = str(path)
            current_keys.add(key)
            try:
                st = path.stat()
                sig = (st.st_mtime, st.st_size)
            except OSError:
                continue
            cached = self._cache.get(key)
            if cached is None or cached[0:2] != sig:
                recs = parse_file(path)
                self._cache[key] = (sig[0], sig[1], recs)
            records.extend(self._cache[key][2])
        # drop cache entries for files no longer present
        for stale in set(self._cache) - current_keys:
            del self._cache[stale]
        return records
