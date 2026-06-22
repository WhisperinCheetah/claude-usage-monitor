"""Live "is Claude responding right now?" signal, written by Claude Code hooks.

Transcripts only record *completed* messages, so they can't say when a turn is
in flight. Claude Code hooks can: a ``UserPromptSubmit`` hook marks a session
``responding`` and a ``Stop`` hook marks it ``idle`` (see
``usage_monitor/hooks/status_hook.py``). Each session writes its own file, so
concurrent sessions never race on a single shared file.

The monitor reads these files every refresh. A ``responding`` mark only counts
while it is *fresh* (``FRESHNESS_SECONDS``): if a session crashes without firing
its ``Stop`` hook the stale mark decays to "not responding" rather than getting
stuck on forever. The window is generous because a long agentic turn (many tool
steps) only writes the mark once, at prompt submit — it must outlast the turn.
"""
import json
import time
from pathlib import Path

FRESHNESS_SECONDS = 600  # a "responding" mark older than this is treated as stale


def status_dir() -> Path:
    """Directory holding per-session status files, beside ~/.claude/projects."""
    return Path.home() / ".claude" / "usage-monitor" / "status"


def _resolve_dir(override) -> Path:
    return Path(override) if override is not None else status_dir()


def _session_file(session_id: str, base: Path) -> Path:
    # Keep the filename filesystem-safe even if a session id is unusual.
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (session_id or "unknown"))
    return base / f"{safe}.json"


def write_status(state, session_id, cwd="", model="", *, now=None, status_dir=None) -> None:
    """Record `state` ("responding"/"idle") for `session_id`. Best-effort.

    `model` is the session's model id (e.g. "claude-opus-4-8"), captured by the
    hook so the monitor can color a responding agent immediately and for the
    whole turn, without waiting for the model to surface in the transcript cache.
    """
    base = _resolve_dir(status_dir)
    ts = time.time() if now is None else now
    base.mkdir(parents=True, exist_ok=True)
    payload = {"state": state, "ts": ts, "cwd": cwd, "session_id": session_id,
               "model": model}
    _session_file(session_id, base).write_text(json.dumps(payload), encoding="utf-8")


def model_from_transcript(transcript_path, *, tail_bytes=262144) -> str:
    """Newest assistant model id in a transcript JSONL, or "" if unknown.

    Reads only the tail so it stays fast when called from a hook on a large
    transcript. Returns "" on any problem — the model is then simply unknown and
    a caller must never fail over it.
    """
    try:
        path = Path(transcript_path)
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
                f.readline()  # drop the partial line we landed in the middle of
            data = f.read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return ""
    model = ""
    for line in data.splitlines():
        if '"model"' not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        msg = obj.get("message", obj) if isinstance(obj, dict) else {}
        m = msg.get("model") if isinstance(msg, dict) else None
        if m:
            model = m  # keep scanning; the last (newest) one wins
    return model


def clear_status(session_id, *, status_dir=None) -> None:
    """Remove a session's status file (called on session end). Best-effort."""
    try:
        _session_file(session_id, _resolve_dir(status_dir)).unlink()
    except OSError:
        pass


def responding_sessions(*, now=None, freshness_seconds=FRESHNESS_SECONDS, status_dir=None) -> list:
    """Freshly-responding sessions as ``{session_id, cwd, ts}``, oldest ts first.

    Sorting by ``ts`` gives a stable left-to-right order across refreshes so the
    dots don't jump around as files are re-read.
    """
    base = _resolve_dir(status_dir)
    if not base.is_dir():
        return []
    cutoff = (time.time() if now is None else now) - freshness_seconds
    out = []
    for path in base.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        ts = float(data.get("ts", 0) or 0)
        if data.get("state") == "responding" and ts >= cutoff:
            out.append({
                "session_id": str(data.get("session_id") or path.stem),
                "cwd": str(data.get("cwd") or ""),
                "ts": ts,
                "model": str(data.get("model") or ""),
            })
    out.sort(key=lambda s: s["ts"])
    return out


def is_responding(*, now=None, freshness_seconds=FRESHNESS_SECONDS, status_dir=None) -> bool:
    """True if any session is freshly marked "responding"."""
    return bool(responding_sessions(
        now=now, freshness_seconds=freshness_seconds, status_dir=status_dir))
