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

## Desktop launcher (Ubuntu / GNOME)

Register a clickable launcher (per-user, no root):

```bash
./install.sh
```

This installs `.desktop` entries and an icon under `~/.local`. Open the
Activities overview, search **Claude Usage Monitor**, and launch it; right-click
its dock icon and choose **Pin to Dash** to keep it on the bar.

### Top-bar indicator

`install.sh` also registers a top-bar (AppIndicator) entry and an autostart
entry. The indicator sits at the top-right of the GNOME panel, shows the cost
for the configured timeframe as its label (updating every few seconds — at
message-completion granularity, see below), and its menu lets you switch
timeframe, open the full window, or quit.

- **Scroll** over the icon to cycle the timeframe.
- **Show recent delta** (menu item, or **middle-click** the icon) flips the
  label between the timeframe total and the recent-spend delta.

It starts automatically at next login; to start it now:

```bash
python3 run_tray.py &
```

The indicator icon is **color-coded by recent activity**: gray when idle,
ramping to vivid green as spend over the last 10 minutes rises, fully green at
about $6 in that window. Tune the window and scale via `COLOR_WINDOW_SECONDS` /
`COLOR_MAX_SPEND` in `usage_monitor/heat.py`. (The color always reflects this
fixed window, independent of the timeframe shown in the label.)

Requires PyGObject + AppIndicator, which ship with Ubuntu GNOME. If missing:

```bash
sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1
```

Remove everything (launchers, autostart, icon) with:

```bash
./uninstall.sh
```

### A note on "live" cost

Claude Code writes token usage to its transcripts only when an assistant
message *completes*, so the figures update per message (every few seconds
during an agentic task with many tool calls), not token-by-token within a
single streaming response. True mid-generation cost isn't observable from
outside Claude Code.

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
- A **`●` model dot** (top-left) shows which model your most recent message
  used; the **cost number rolls** up/down when it changes and **pulses** green
  while recent burn is high; each completed turn briefly **flashes** its own
  cost (top-right, green fading to grey).
- A **sparkline** of recent cost sits below the figures — **click it** to cycle
  the range (1h / 24h / 7d / 30d).
- Drag the body to move it. **Right-click** for a menu to toggle
  **Semi-transparent** (see-through but readable) or quit.
- Position, timeframe, mode, transparency, and sparkline range are remembered
  in `~/.config/claude-usage-monitor/config.json`.

## Pricing

Per-1M-token rates live in `usage_monitor/pricing.json` (model rates, fallback
model, cache multipliers) — edit that file when prices change, no code edit
needed. To customize without touching the repo, drop your own
`~/.config/claude-usage-monitor/pricing.json` (same shape); it overrides the
bundled defaults. Unknown models fall back to the configured fallback model so
cost is never silently zero.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
