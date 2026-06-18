"""Load/save widget settings as JSON in the OS-native config directory."""
import json
from pathlib import Path

from usage_monitor import paths

DEFAULTS = {
    "x": None, "y": None,
    "timeframe": "month", "mode": "accurate", "delta_window": "24h",
    "translucent": False,      # widget semi-transparency toggle
    "tray_show_delta": False,  # tray label shows recent delta vs. total
    "spark_range": "24h",      # sparkline range (1h / 24h / 7d / 30d)
}


def config_path() -> Path:
    return paths.config_dir() / "config.json"


def load_config(path: Path) -> dict:
    cfg = dict(DEFAULTS)
    try:
        with Path(path).open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cfg.update({k: data[k] for k in DEFAULTS if k in data})
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return cfg


def save_config(path: Path, cfg: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULTS)
    merged.update({k: cfg[k] for k in DEFAULTS if k in cfg})
    with path.open("w", encoding="utf-8") as fh:
        json.dump(merged, fh)
