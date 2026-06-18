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

update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Installed launcher: $DESKTOP_DIR/$APP_ID.desktop"
echo "Open the Activities overview and search 'Claude Usage Monitor' to launch it,"
echo "then right-click its dock icon and choose 'Pin to Dash' to keep it on the bar."
