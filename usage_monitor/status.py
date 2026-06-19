"""Live "is Claude responding right now?" signal, written by Claude Code hooks.

Transcripts only record *completed* messages, so they can't say when a turn is
in flight. Claude Code hooks can: a ``UserPromptSubmit`` hook marks a session
``responding`` and a ``Stop`` hook marks it ``idle`` (see
``usage_monitor/hooks/status_hook.py``). Each session writes its own file, so
concurrent sessions never race on a single shared file.

The monitor reads these files every refresh. A ``responding`` mark only counts
while it is *fresh* (``FRESHNESS_SECONDS``): if a session crashes without firing
its ``Stop`` hook the stale mark decays to "not responding" rather than getting
stuck on forever.
"""
import json
import time
from pathlib import Path

FRESHNESS_SECONDS = 180  # a "responding" mark older than this is treated as stale


def status_dir() -> Path:
    """Directory holding per-session status files, beside ~/.claude/projects."""
    return Path.home() / ".claude" / "usage-monitor" / "status"


def _resolve_dir(override) -> Path:
    return Path(override) if override is not None else status_dir()


def _session_file(session_id: str, base: Path) -> Path:
    # Keep the filename filesystem-safe even if a session id is unusual.
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (session_id or "unknown"))
    return base / f"{safe}.json"


def write_status(state, session_id, cwd="", *, now=None, status_dir=None) -> None:
    """Record `state` ("responding"/"idle") for `session_id`. Best-effort."""
    base = _resolve_dir(status_dir)
    ts = time.time() if now is None else now
    base.mkdir(parents=True, exist_ok=True)
    payload = {"state": state, "ts": ts, "cwd": cwd, "session_id": session_id}
    _session_file(session_id, base).write_text(json.dumps(payload), encoding="utf-8")


def clear_status(session_id, *, status_dir=None) -> None:
    """Remove a session's status file (called on session end). Best-effort."""
    try:
        _session_file(session_id, _resolve_dir(status_dir)).unlink()
    except OSError:
        pass


def is_responding(*, now=None, freshness_seconds=FRESHNESS_SECONDS, status_dir=None) -> bool:
    """True if any session is freshly marked "responding"."""
    base = _resolve_dir(status_dir)
    if not base.is_dir():
        return False
    cutoff = (time.time() if now is None else now) - freshness_seconds
    for path in base.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("state") == "responding" and float(data.get("ts", 0)) >= cutoff:
            return True
    return False
