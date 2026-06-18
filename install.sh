#!/usr/bin/env bash
# Install a desktop launcher for the Claude usage monitor (per-user, no root).
# Registers the app under ~/.local so it appears in Activities / the app grid;
# from there you can pin it to the dock and click to open.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="claude-usage-monitor"
PY="$(command -v python3 || true)"

if [ -z "$PY" ]; then
    echo "error: python3 not found on PATH" >&2
    exit 1
fi

ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$ICON_DIR" "$DESKTOP_DIR"

install -m 644 "$REPO_DIR/packaging/icon.svg" "$ICON_DIR/$APP_ID.svg"

cat > "$DESKTOP_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Claude Usage Monitor
Comment=Live Claude Code token usage and estimated API cost
Exec=$PY "$REPO_DIR/run.py"
Path=$REPO_DIR
Icon=$APP_ID
Terminal=false
Categories=System;Monitor;
StartupNotify=false
EOF

# Top-bar indicator (AppIndicator): a launcher plus an autostart entry so the
# indicator returns at every login.
cat > "$DESKTOP_DIR/$APP_ID-tray.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Claude Usage Monitor (Top Bar)
Comment=Top-bar indicator showing near-live Claude API cost
Exec=$PY "$REPO_DIR/run_tray.py"
Path=$REPO_DIR
Icon=$APP_ID
Terminal=false
Categories=System;Monitor;
StartupNotify=false
EOF

AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cp "$DESKTOP_DIR/$APP_ID-tray.desktop" "$AUTOSTART_DIR/$APP_ID-tray.desktop"
printf 'X-GNOME-Autostart-enabled=true\n' >> "$AUTOSTART_DIR/$APP_ID-tray.desktop"

update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Installed:"
echo "  - window launcher : $DESKTOP_DIR/$APP_ID.desktop"
echo "  - top-bar launcher: $DESKTOP_DIR/$APP_ID-tray.desktop"
echo "  - autostart       : $AUTOSTART_DIR/$APP_ID-tray.desktop"
echo
echo "The top-bar indicator starts automatically at next login. To start it now:"
echo "  python3 \"$REPO_DIR/run_tray.py\" &"
echo "It appears at the top-right; its menu opens the full monitor window."
