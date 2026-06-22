#!/usr/bin/env python3
"""Claude Code hook that records whether this session is responding.

Wired up by ``python -m usage_monitor.install_hooks`` for three events:

    UserPromptSubmit  ->  status_hook.py responding
    Stop              ->  status_hook.py idle
    SessionEnd        ->  status_hook.py end

Claude Code passes the hook payload as JSON on stdin (``session_id``, ``cwd``,
...). We write a per-session status file the monitor polls. This runs inside the
critical path of a Claude turn, so it must be fast and must NEVER fail the turn:
every path swallows errors and exits 0.
"""
import json
import sys
from pathlib import Path

# Run as an absolute-path script (not `-m`), so make the package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def main() -> int:
    state = sys.argv[1] if len(sys.argv) > 1 else "responding"
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        payload = {}
    session_id = str(payload.get("session_id") or "unknown")
    cwd = str(payload.get("cwd") or "")

    try:
        from usage_monitor import status
        if state == "end":
            status.clear_status(session_id)
        else:
            # The model isn't in the hook payload, but transcript_path is — read
            # the session's model from it so the monitor can color this agent for
            # the whole turn. Best-effort: "" if it can't be read.
            model = ""
            tp = payload.get("transcript_path")
            if state == "responding" and tp:
                model = status.model_from_transcript(tp)
            status.write_status(state, session_id, cwd, model)
    except Exception:
        pass  # never break a Claude turn over telemetry
    return 0


if __name__ == "__main__":
    sys.exit(main())
