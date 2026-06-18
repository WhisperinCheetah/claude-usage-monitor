#!/usr/bin/env bash
# Remove the .app and login item installed by install_macos.sh.
set -euo pipefail

LABEL="com.claude.usage-monitor"
APP_DIR="$HOME/Applications/Claude Usage Monitor.app"
LA="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl unload "$LA" 2>/dev/null || true
rm -f "$LA"
rm -rf "$APP_DIR"
echo "Removed app and login item. If it's still running, quit it (✕ / Activity Monitor)."
