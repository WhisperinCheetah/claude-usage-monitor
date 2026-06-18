"""OS-native per-user configuration directory.

Linux:   $XDG_CONFIG_HOME/claude-usage-monitor or ~/.config/claude-usage-monitor
macOS:   ~/Library/Application Support/claude-usage-monitor
Windows: %APPDATA%\\claude-usage-monitor
"""
import os
import sys
from pathlib import Path

APP_NAME = "claude-usage-monitor"


def config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / APP_NAME
