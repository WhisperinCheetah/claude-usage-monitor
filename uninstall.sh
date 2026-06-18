#!/usr/bin/env bash
# Remove the desktop launcher installed by install.sh.
set -euo pipefail

APP_ID="claude-usage-monitor"
ICON="$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"
DESKTOP="$HOME/.local/share/applications/$APP_ID.desktop"
TRAY_DESKTOP="$HOME/.local/share/applications/$APP_ID-tray.desktop"
AUTOSTART="$HOME/.config/autostart/$APP_ID-tray.desktop"
CACHE="$HOME/.cache/$APP_ID"

rm -f "$ICON" "$DESKTOP" "$TRAY_DESKTOP" "$AUTOSTART"
rm -rf "$CACHE"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Removed launchers, autostart entry, and icon."
echo "If the indicator is still running, quit it from its top-bar menu."
