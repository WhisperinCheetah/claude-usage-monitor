# claude-usage-monitor — Design

**Date:** 2026-06-18
**Status:** Approved, pending implementation plan

## Summary

A super-lightweight, always-on-top desktop widget that reads local Claude Code
transcripts and displays token usage plus an estimated pay-as-you-go API cost
(what the same usage would cost on the Anthropic API without a subscription).

Built with **Python + Tkinter (standard library only)** — no third-party
dependencies, no build step. Targets the user's Linux desktop.

## Goals

- Show token usage and estimated cost at a glance, always on top of other windows.
- Let the user switch between time windows via a dropdown.
- Let the user toggle between two cost-estimation methods.
- Stay lightweight: stdlib only, low RAM, incremental refresh.

## Non-goals

- No remote/telemetry dependency. The OTLP exporter configured in
  `~/.claude/settings.json` (to `dashboard-staging.api.optioryx.com`) is **not**
  used. All data comes from local files.
- No historical charts/graphs, no export, no multi-machine aggregation.
- No packaging/installer in v1 (run via `python3 run.py`).

## Data source

Claude Code writes per-message usage to JSONL transcripts under
`~/.claude/projects/**/*.jsonl`. Each assistant message line contains:

- `message.model` — e.g. `claude-opus-4-8`, `claude-sonnet-4-6`,
  `claude-haiku-4-5-20251001`
- `message.id` — message identifier (used for dedup)
- `message.usage` — `input_tokens`, `output_tokens`,
  `cache_creation_input_tokens`, `cache_read_input_tokens`
- `timestamp` — ISO 8601 timestamp on the record

This is the same data source the dashboards/`ccusage` use. It is live and
per-message, so a tail/poll approach yields near-real-time numbers.

`~/.claude/stats-cache.json` also exists (pre-aggregated daily/per-model
totals) but is stale (periodically recomputed) and reports `costUSD: 0`, so it
is **not** used as the source of truth.

### Usage record

Parsing produces a flat list of records, the single source of truth:

```
UsageRecord:
  timestamp: datetime (UTC)
  model: str               # raw model id from the transcript
  input: int
  output: int
  cache_creation: int
  cache_read: int
  message_id: str          # for dedup
  source_file: str
```

Dedup: drop records with a `message_id` already seen (Claude Code can write a
message line more than once). Records missing a `usage` block or a parseable
timestamp are skipped.

## Cost engine

Hardcoded, editable pricing table keyed by normalized model id (per 1M tokens):

| Model id           | input | output | cache write (5m) | cache read |
|--------------------|-------|--------|------------------|------------|
| `claude-opus-4-8`  | 5.00  | 25.00  | 6.25             | 0.50       |
| `claude-sonnet-4-6`| 3.00  | 15.00  | 3.75             | 0.30       |
| `claude-haiku-4-5` | 1.00  | 5.00   | 1.25             | 0.10       |

Derived rates: cache write = 1.25 × input, cache read = 0.1 × input (Anthropic's
published API rates). Cache writes are assumed to be the 5-minute TTL rate
(1.25×); this is the dominant case for Claude Code.

Model-id normalization: strip date suffixes (e.g. `claude-haiku-4-5-20251001`
→ `claude-haiku-4-5`) before lookup. Unknown models fall back to the Opus rate
and are flagged internally (so the cost is never silently zero).

Two cost methods:

- **Accurate** (default):
  `input·in + output·out + cache_creation·(1.25·in) + cache_read·(0.1·in)`
- **Simple**:
  `(input + cache_creation + cache_read)·in + output·out`
  (all input-side tokens at the flat input rate; slightly overestimates)

## Timeframe filtering

A dropdown selects the window, applied to records by `timestamp` (local time):

- **Current session** — records from the most-recently-modified transcript file only
- **Today** — since local midnight
- **This week** — since most recent Monday 00:00 local
- **Last 7 days** — rolling 168 hours
- **This month** — since the 1st of the current month, 00:00 local
- **All-time** — every record

## UI

Compact always-on-top window (~260×140px), Tkinter:

```
┌─ Claude Usage ──────────────┐
│ [This month ▾]   [Accurate ▾]│
│ Tokens   12.4M               │
│ Cost     $58.91              │
│ Opus $54 · Sonnet $4 · Haiku │
│ ● updated 14:32              │
└──────────────────────────────┘
```

- Always-on-top via `root.attributes('-topmost', True)`.
- Draggable by click-drag anywhere on the body; position persisted.
- Timeframe dropdown (all six windows above) and cost-mode dropdown
  (Accurate / Simple).
- Total tokens (human-formatted, e.g. `12.4M`) and total estimated cost.
- Per-model cost breakdown line.
- "updated HH:MM" indicator showing the last successful refresh.

## Refresh loop

Tkinter `after()` schedules a refresh every ~3s:

1. Scan `~/.claude/projects/**/*.jsonl` and check each file's
   `(mtime, size)`.
2. Re-parse only files whose `(mtime, size)` changed since last scan; reuse
   cached parsed records for unchanged files.
3. Recompute the current view (filter by timeframe, roll up per model, cost).
4. Update labels and the "updated" indicator.

Incremental re-parse keeps cost low as transcripts grow.

## Persistence

Settings saved to `~/.config/claude-usage-monitor/config.json`:

- window `x`, `y`
- selected timeframe
- selected cost mode

Missing/corrupt config falls back to defaults (This month, Accurate, centered).

## Structure

Logic is kept free of Tkinter so it can be tested with TDD against fixture
JSONL; only the UI layer does IO/state.

- `pricing.py` — pricing table, model normalization, `accurate`/`simple` cost
  functions. Pure.
- `transcripts.py` — file discovery, JSONL parsing, dedup, `(mtime,size)`
  parse cache. Pure functions over paths.
- `aggregate.py` — timeframe boundary computation, filtering, per-model
  rollups, totals. Pure (clock injected for testability).
- `config.py` — load/save settings JSON with defaults.
- `app.py` — Tkinter window, dropdowns, drag handling, refresh loop.
- `run.py` — entry point.

## Testing

- `pricing`: cost math for each model and both modes; date-suffix
  normalization; unknown-model fallback.
- `transcripts`: parse a fixture JSONL (valid lines, missing-usage lines,
  duplicate message ids); dedup correctness.
- `aggregate`: timeframe boundaries (week starts Monday, month start, rolling
  7-day) with an injected fixed clock; per-model rollups; current-session
  selection by newest file.
- `config`: round-trip save/load; default fallback on missing/corrupt file.
- UI layer is exercised manually (always-on-top, drag, dropdown switching).

## Open assumptions

- Cache writes priced at the 5-minute rate (1.25× input). If 1-hour caching
  turns out to be common in the user's transcripts, the TTL assumption could be
  made configurable later.
- All timestamps interpreted/aggregated in local time for the day/week/month
  boundaries.
