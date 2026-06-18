# claude-usage-monitor

A super-lightweight, always-on-top desktop widget that reads your local Claude
Code transcripts (`~/.claude/projects/**/*.jsonl`) and shows token usage plus
the estimated pay-as-you-go Anthropic API cost — i.e. what the same usage would
cost without a subscription.

Pure Python standard library. No dependencies, no build step, no network.

## Run

```bash
python3 run.py
```

## Use

- **Timeframe dropdown:** Current session, Today, This week (from Monday),
  Last 7 days, This month, All-time.
- **Cost dropdown:** Accurate (cache writes at 1.25×, reads at 0.1× input) or
  Simple (all input-side tokens at the flat input rate).
- **Delta:** a stock-ticker-style `+$x.xx (window)` next to the cost shows how
  much was spent in the most recent window. The window dropdown's choices and
  default scale with the timeframe — `5m / 10m / 30m / 60m` are always
  available; larger timeframes also offer `6h / 24h / 7d / 30d`. Switching the
  timeframe resets the window to that timeframe's default.
- Drag the body to move it; position, timeframe, and mode are remembered in
  `~/.config/claude-usage-monitor/config.json`.

## Pricing

Hardcoded per-1M-token rates in `usage_monitor/pricing.py`
(Opus 4.8 / Sonnet 4.6 / Haiku 4.5). Update that table when prices change.
Unknown models fall back to the Opus rate so cost is never silently zero.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
