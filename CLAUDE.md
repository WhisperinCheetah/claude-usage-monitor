# CLAUDE.md

Guidance for working in this repo.

## What this is

An always-on-top desktop widget (Tkinter) that reads local Claude Code
transcripts and shows token usage + estimated pay-as-you-go API cost. There is
also a GNOME top-bar indicator (`tray.py`). No subscription/account data — it
just prices the tokens already recorded on disk.

## Hard constraints

- **Pure Python standard library. No third-party dependencies, no build step.**
  The only non-stdlib import is PyGObject in `tray.py`, and it is optional and
  Linux-only (guarded by try/except). Do not add dependencies to the widget.
- **No network.** All data comes from `~/.claude/projects/**/*.jsonl` locally.
  Don't add telemetry or remote calls.
- **Python 3.8+** must keep working (e.g. `datetime.fromisoformat` can't parse a
  trailing `Z` on old versions — see `transcripts._parse_ts`).

## Architecture / data flow

```
~/.claude/projects/**/*.jsonl
   -> transcripts.find_transcripts / TranscriptCache.load   (parse, mtime-cached)
   -> transcripts.dedup                                     (drop repeat message ids)
   -> aggregate.filter_by_time / filter_by_file             (select a timeframe)
   -> aggregate.rollup + pricing.cost_for                   (tokens + $)
   -> app.py renders + animates  /  tray.py renders a label
```

Only assistant messages that carry a `usage` block become `UsageRecord`s; user
messages are ignored. Cost math lives in `pricing.py` (rates in `pricing.json`;
a user copy in the config dir overrides the bundled one).

## Module map (keep logic out of the UI)

The "pure" modules have no Tk/GTK and are unit-tested directly:

- `pricing.py` — cost engine + `pricing.json` loader, `normalize_model`.
- `transcripts.py` — discover/parse JSONL, dedup, `(mtime,size)` cache.
- `aggregate.py` — timeframes, rollups, recent-delta windows.
- `sparkline.py` — time-bucketed cost series + range cycling.
- `heat.py` — recent-burn → gray/green color + tray icon SVG.
- `status.py` — hook-fed "responding now" signal (per-session files).
- `format.py` — token/cost formatting.
- `config.py` / `paths.py` — settings JSON + OS-native config dir.

UI / process entry points:

- `app.py` — the Tkinter widget and all animations.
- `tray.py` — GNOME AppIndicator (separate GTK process; runs `run.py` to open
  the window).
- `install_hooks.py` + `hooks/status_hook.py` — the responding-indicator hooks.

**Convention: put testable logic in a pure module (or a module-level pure
function) and keep `app.py`/`tray.py` thin.** Animations can't be unit-tested
(they need a Tk event loop), so extract their math — e.g. `app.flash_intensity`,
`heat.intensity` — as pure functions and test those.

## Animations in app.py

Tk has no real animation API; everything is `root.after(ms, callback)` loops
that re-schedule themselves:

- `_cost_tick` — eases the displayed cost toward the target (roll-up).
- `_pulse_step` — always running (90ms); glows the cost number when `_hot`, and
  shimmers the responding dot. **It yields the cost color to a heartbeat burst
  when `_burst_seq` is active** — don't have two loops fight over one widget's
  color; gate one on the other.
- `_flash_turn`/`_flash_step` — per-turn `+$x.xx` flash, scaled by
  `flash_intensity(turn_cost, cfg["flash_full_cost"])`: hotter color, bigger
  font, longer fade, and a `_start_burst` heartbeat above `_BURST_THRESHOLD`.

Colors are hex; blend with `_blend(a, b, t)`.

## Responding indicator (hooks)

`status.is_responding()` reads `~/.claude/usage-monitor/status/<session>.json`,
written by `hooks/status_hook.py` (UserPromptSubmit → responding, Stop → idle,
SessionEnd → remove). The hook runs inside a Claude turn, so it must be fast and
**always exit 0** — never let telemetry break a turn. A "responding" mark is only
trusted while fresh (`status.FRESHNESS_SECONDS`) so a crashed session decays to
idle. `install_hooks.py` patches `~/.claude/settings.json` idempotently and
preserves unrelated hooks.

## Run & test

```bash
python3 run.py                              # the widget (needs a display + tkinter)
python3 run_tray.py                         # Linux top-bar indicator
python3 -m usage_monitor.install_hooks      # responding-indicator hooks (--uninstall)
python3 -m unittest discover -s tests -v    # tests (no display needed)
```

Tests use `unittest` (no pytest). Every pure module has a `tests/test_*.py`; add
cases there and keep the suite green. There's no linter/formatter configured —
match the surrounding style (concise docstrings explaining *why*, not *what*).
