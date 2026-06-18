#!/usr/bin/env bash
# Install a .app launcher and a login item for the Claude usage monitor (macOS).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3)"
LABEL="com.claude.usage-monitor"
APP_DIR="$HOME/Applications/Claude Usage Monitor.app"
LA="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ -z "$PY" ]; then
    echo "error: python3 not found on PATH" >&2
    exit 1
fi

# Minimal .app bundle that launches the widget.
mkdir -p "$APP_DIR/Contents/MacOS"
cat > "$APP_DIR/Contents/MacOS/launcher" <<EOF
#!/bin/bash
exec "$PY" "$REPO/run.py"
EOF
chmod +x "$APP_DIR/Contents/MacOS/launcher"

cat > "$APP_DIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Claude Usage Monitor</string>
  <key>CFBundleIdentifier</key><string>$LABEL</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
</dict></plist>
EOF

# Login item (starts at login).
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$LA" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string>
    <string>$REPO/run.py</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict></plist>
EOF

echo "Installed app:        $APP_DIR"
echo "Installed login item: $LA"
echo "Start it now (no re-login):  launchctl load \"$LA\""
echo "Or open 'Claude Usage Monitor' from ~/Applications."
echo "Remove with: ./uninstall_macos.sh"
