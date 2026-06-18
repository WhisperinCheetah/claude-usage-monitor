#!/usr/bin/env bash
# Remove the desktop launcher installed by install.sh.
set -euo pipefail

APP_ID="claude-usage-monitor"
ICON="$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"
DESKTOP="$HOME/.local/share/applications/$APP_ID.desktop"

rm -f "$ICON" "$DESKTOP"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Removed $DESKTOP and its icon."
