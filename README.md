# claude-usage-monitor

A super-lightweight, always-on-top desktop widget that reads your local Claude
Code transcripts and shows **token usage + estimated pay-as-you-go API cost** —
i.e. what your usage *would* cost on the Anthropic API without a subscription.

Pure Python standard library: no third-party dependencies, no build step, no
network. All data comes from `~/.claude/projects/**/*.jsonl` on your own machine.

```
┌─ Claude Usage ───────────────────────┐
│ ● Opus                      +$0.38    │
│ Tokens   12.4M                        │
│ Cost     $58.91   +$2.10 (5m)         │
│ Opus $54 · Sonnet $4 · Haiku $0.27    │
│ ▁▂▅▃▇▆█▄▂▁  24h                       │
│ ● updated 14:32                       │
│ [This month ▾]  [24h ▾]  [Accurate ▾] │
└───────────────────────────────────────┘
```

## Installation

**Requirements:** Python 3.8+ with `tkinter` (bundled with most Python installs;
on Linux `sudo apt install python3-tk` if missing). No other dependencies for the
widget. The Linux top-bar tray additionally needs PyGObject + AppIndicator
(see [Linux tray](#top-bar-indicator-linux-only)).

### Quick start (any OS)

```bash
python3 run.py        # macOS / Linux
pythonw run.py        # Windows (no console window)
```

### Linux (GNOME)

Register a clickable launcher and the top-bar indicator (per-user, no root):

```bash
./install.sh
```

Then open the Activities overview, search **Claude Usage Monitor**, and launch
it (right-click its dock icon → **Pin to Dash** to keep it handy). Remove with
`./uninstall.sh`.

### macOS

```bash
./install_macos.sh
```

Installs `Claude Usage Monitor.app` in `~/Applications` plus a login item.
Remove with `./uninstall_macos.sh`. Tip: use a [python.org](https://python.org)
build for a working Tk 8.6.

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\install_windows.ps1
```

Creates Start Menu and Startup shortcuts that launch via `pythonw.exe`. Remove
with `.\uninstall_windows.ps1`.

### Platform support at a glance

| | Widget (`run.py`) | Launcher / login item | Top-bar tray |
|---|---|---|---|
| **Linux (GNOME)** | yes (frameless) | `install.sh` | yes (`run_tray.py`) |
| **macOS** | yes (titled window) | `install_macos.sh` | — |
| **Windows** | yes (frameless) | `install_windows.ps1` | — |

On macOS the window uses a normal title bar (borderless windows are unreliable
on Aqua); the right-click button is selected automatically per platform.

## Usage

- **Drag** to move; **right-click** (Control-click on macOS) to toggle
  transparency or quit.
- **Click the sparkline** to cycle its range; the bottom dropdowns set
  timeframe, delta window, and cost method.
- Settings persist between runs (see [Configuration](#configuration)).

## Features

- **Real-cost estimate.** Per-model token usage priced at public API rates,
  including prompt-cache rates (writes 1.25×, reads 0.1× of input).
- **Timeframes.** Current session, Today, This week (from Monday), Last 7 days,
  This month, All-time.
- **Two cost methods.** *Accurate* (cache discounts applied) or *Simple* (all
  input-side tokens at the flat input rate).
- **Recent-spend delta.** A stock-ticker `+$x.xx (window)` next to the cost;
  the window scales with the timeframe (`5m/10m/30m/60m` always available,
  larger ranges added for longer timeframes).
- **Sparkline.** A bar chart of recent cost — click to cycle `1h / 24h / 7d / 30d`.
- **Live touches.** Cost number rolls to its new value, pulses green when you're
  burning hard, and each completed turn flashes its own cost. A `●` dot shows
  which model your latest message used.
- **Always on top**, draggable, with a **semi-transparent** toggle.
- **Linux top-bar indicator** with a cost label color-coded by recent activity.

## Top-bar indicator (Linux only)

`install.sh` also registers a GNOME AppIndicator and an autostart entry. The
indicator shows the cost for the configured timeframe and is **color-coded** by
recent activity (gray when idle → vivid green at ~$6 spent in the last 10 min).

- **Scroll** the icon to cycle the timeframe.
- **Show recent delta** (menu item, or **middle-click**) flips the label between
  the timeframe total and the recent delta.
- Its menu opens the full window, switches timeframe, or quits.

Start it now without re-logging in:

```bash
python3 run_tray.py &
```

Needs PyGObject + AppIndicator, which ship with Ubuntu GNOME. If missing:

```bash
sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1
```

## Configuration

Settings are stored as JSON in the OS-native config directory:

| OS | Location |
|---|---|
| Linux | `~/.config/claude-usage-monitor/` |
| macOS | `~/Library/Application Support/claude-usage-monitor/` |
| Windows | `%APPDATA%\claude-usage-monitor\` |

## Pricing

Per-1M-token rates live in `usage_monitor/pricing.json` (model rates, fallback
model, cache multipliers) — edit it when prices change, no code edit needed. To
customize without touching the repo, drop your own `pricing.json` (same shape)
in the config directory above; it overrides the bundled defaults. Unknown models
fall back to the configured fallback model, so cost is never silently zero.

Tray color thresholds (`COLOR_WINDOW_SECONDS`, `COLOR_MAX_SPEND`) and the
pulse/heat tuning live in `usage_monitor/heat.py`.

## How "live" is the cost?

Claude Code writes token usage to its transcripts only when an assistant message
**completes**, so the figures update per message — every few seconds during an
agentic task with many tool calls, but not token-by-token within a single
streaming response. True mid-generation cost isn't observable from outside
Claude Code.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Project layout

```
usage_monitor/
  pricing.py      cost engine + pricing.json loader      (pure)
  transcripts.py  discover/parse JSONL, dedup, mtime cache (pure)
  aggregate.py    timeframes, rollups, deltas             (pure)
  sparkline.py    time-bucketed cost series               (pure)
  heat.py         recent-burn -> gray/green color + icon   (pure)
  format.py       token/cost formatting                   (pure)
  config.py       settings load/save
  paths.py        OS-native config directory
  app.py          Tkinter widget + animations
  tray.py         GNOME AppIndicator (Linux)
run.py            launch the widget
run_tray.py       launch the tray indicator (Linux)
install*.{sh,ps1} per-OS launchers
```
