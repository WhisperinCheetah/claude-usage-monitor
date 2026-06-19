# Responding indicator + cost-scaled flash — design

Date: 2026-06-19

Two additions to the Tkinter usage monitor:

1. **"Responding now" indicator** — show, at the top, whether Claude is actively
   working on a prompt (vs idle), using Claude Code hooks for an accurate signal.
2. **Cost-scaled flash** — make the per-turn "+$x.xx" flash punch harder the more
   expensive the response was (no rolling average; scaled to absolute cost).

Constraint: the project is pure-stdlib Python (no third-party deps). Both features
preserve that.

## Feature A — "Responding now" indicator (hook-based)

Transcripts only contain *completed* messages, so they can't tell us when Claude
is mid-response. Claude Code hooks can: `UserPromptSubmit` fires when a turn
starts, `Stop` when it ends.

### Components

- **`usage_monitor/status.py`** (new, pure logic):
  - `status_dir()` → `~/.claude/usage-monitor/status/` (sibling of `projects/`,
    so the monitor finds it with no config).
  - `write_status(state, session_id, cwd, *, now, status_dir)` → writes one JSON
    file per session: `<session_id>.json = {state, ts, cwd, session_id}`. Per-
    session files mean concurrent sessions never race on a write.
  - `clear_status(session_id, *, status_dir)` → removes the file on session end.
  - `is_responding(*, now, freshness_seconds=180, status_dir)` → `True` if any
    session file has `state == "responding"` and `ts` is within the freshness
    window. The freshness guard means a crashed session that never fired `Stop`
    decays to "idle" instead of being stuck "responding" forever.

- **`usage_monitor/hooks/status_hook.py`** (new, runs as the hook process):
  - Invoked as `status_hook.py <state>` where `<state>` ∈
    `responding | idle | end`. Reads the hook JSON from stdin (`session_id`,
    `cwd`), then calls `write_status`/`clear_status`. Wrapped so it *always*
    exits 0 and never blocks or breaks a Claude turn. Adds the repo root to
    `sys.path` so it can import `usage_monitor.status` (single source of truth
    for the dir + file format).

- **`usage_monitor/install_hooks.py`** (new): `python -m usage_monitor.install_hooks`
  patches `~/.claude/settings.json` idempotently, registering the hook for
  `UserPromptSubmit` (→ responding), `Stop` (→ idle), and `SessionEnd` (→ end).
  `--uninstall` removes them. Re-running is a no-op (commands are matched by the
  hook script path). Existing unrelated hooks are preserved.

### Monitor side (`app.py`)

- Each refresh sets `self._responding = status.is_responding(now=...)`.
- The top-left dot:
  - responding → `● {Model} ⚡` with the dot **shimmering** (brightness
    oscillation, driven by the existing `_pulse_step` loop).
  - idle → `● {Model}` steady (current behavior).
- The model name still comes from the newest transcript record; the hook only
  supplies live on/off state.

## Feature B — cost-scaled flash (`app.py` + `config.py`)

`intensity = clamp(turn_cost / flash_full_cost, 0, 1)`, where `flash_full_cost`
is a new config key (default **$0.25/turn = full burn**). On each new turn the
flash amplifies three ways with intensity:

- **Color:** peak flash color lerps green (`_FLASH_GREEN`) → hot-white
  (`_FLASH_HOT`). Cheap turn = soft green; spike = white-hot.
- **Size + duration:** the `+$x.xx` text scales up (≈9→14pt) at the peak and the
  fade has more steps (lingers longer) when intensity is high.
- **Pulse burst:** above a threshold (intensity ≥ ~0.6) the cost total throbs a
  few hard "heartbeats" (`_COST_BURST` white) before settling. The burst
  temporarily takes over the cost-label color from the steady `_pulse_step`.

Pure helper `flash_intensity(cost, full_cost)` is extracted to module level so it
is unit-testable without Tk. The existing 10-minute "hot" pulse is unchanged;
this per-turn punch layers on top.

## Testing

- `status.py`: write/read round-trip, freshness decay (stale "responding" →
  not responding), multi-session (one responding among several idle), missing
  dir → not responding.
- `install_hooks.py`: fresh patch creates the three events; re-running is
  idempotent; `--uninstall` removes only our entries and leaves others intact.
- `flash_intensity`: 0 cost → 0, at/above full → 1, clamping.

Animations themselves (Tk timers/colors) are verified by running the app, not
unit-tested.

## Out of scope

- No rolling-average / z-score heat math (explicitly dropped per user).
- No new network calls; everything stays local + stdlib.
