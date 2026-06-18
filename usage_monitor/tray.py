"""GNOME top-bar indicator (AppIndicator) showing near-live Claude API cost.

Runs as its own GTK process so it doesn't clash with the Tkinter window's event
loop. The indicator's label is the cost for the configured timeframe (updates
every few seconds, at message-completion granularity — see README); its menu
lets you pick the timeframe, open the full monitor window, or quit.
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except (ValueError, ImportError):  # older systems
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3 as AppIndicator
from gi.repository import GLib, Gtk  # noqa: E402

from usage_monitor import aggregate, config, heat, transcripts  # noqa: E402
from usage_monitor.format import fmt_cost  # noqa: E402

REFRESH_SECONDS = 3
APP_ID = "claude-usage-monitor"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGING = _REPO_ROOT / "packaging"
_RUN_PY = _REPO_ROOT / "run.py"
_LABEL_GUIDE = "$00000.00"


class TrayApp:
    def __init__(self, projects_dir=None, config_file=None):
        self.projects_dir = projects_dir or transcripts.default_projects_dir()
        self.config_file = config_file or config.config_path()
        self.cfg = config.load_config(self.config_file)
        self.cache = transcripts.TranscriptCache()

        # Pre-render the gray->green gradient icons and tint the indicator by
        # recent-spend bucket (see usage_monitor/heat.py).
        self._icon_dir = self._generate_icons()
        self._cur_bucket = 0

        self.indicator = AppIndicator.Indicator.new(
            APP_ID, "heat-00", AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_icon_theme_path(str(self._icon_dir))
        self.indicator.set_icon_full("heat-00", "Claude Usage Monitor")
        self.indicator.set_title("Claude Usage Monitor")
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_label("…", _LABEL_GUIDE)

        self._build_menu()
        self.refresh()
        GLib.timeout_add_seconds(REFRESH_SECONDS, self._tick)

    def _generate_icons(self):
        icon_dir = Path.home() / ".cache" / APP_ID / "icons"
        icon_dir.mkdir(parents=True, exist_ok=True)
        for i in range(heat.N_BUCKETS):
            (icon_dir / f"heat-{i:02d}.svg").write_text(
                heat.gradient_svg(heat.bucket_color_hex(i)), encoding="utf-8"
            )
        return icon_dir

    def _build_menu(self):
        menu = Gtk.Menu()

        self.header_item = Gtk.MenuItem(label="…")
        self.header_item.set_sensitive(False)
        menu.append(self.header_item)
        menu.append(Gtk.SeparatorMenuItem())

        # Timeframe radio submenu — controls what the top-bar number reflects.
        tf_parent = Gtk.MenuItem(label="Timeframe")
        tf_menu = Gtk.Menu()
        first = None
        for key, label in aggregate.TIMEFRAMES:
            item = Gtk.RadioMenuItem.new_with_label_from_widget(first, label)
            if first is None:
                first = item
            if key == self.cfg["timeframe"]:
                item.set_active(True)  # set before connect so it doesn't fire early
            item.connect("toggled", self._on_timeframe, key)
            tf_menu.append(item)
        tf_parent.set_submenu(tf_menu)
        menu.append(tf_parent)

        open_item = Gtk.MenuItem(label="Open monitor window")
        open_item.connect("activate", self._open_window)
        menu.append(open_item)

        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _i: Gtk.main_quit())
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def _on_timeframe(self, item, key):
        if not item.get_active():
            return
        self.cfg["timeframe"] = key
        config.save_config(self.config_file, self.cfg)
        self.refresh()

    def _open_window(self, _item):
        subprocess.Popen([sys.executable, str(_RUN_PY)], cwd=str(_REPO_ROOT),
                         start_new_session=True)

    def refresh(self):
        paths = transcripts.find_transcripts(self.projects_dir)
        records = transcripts.dedup(self.cache.load(paths))
        tf = self.cfg["timeframe"]
        mode = self.cfg["mode"]
        now = datetime.now(timezone.utc)

        if tf == "session":
            newest = aggregate.session_file(paths)
            selected = aggregate.filter_by_file(records, newest) if newest else []
        else:
            start, end = aggregate.timeframe_bounds(tf, now)
            selected = aggregate.filter_by_time(records, start, end)

        total = aggregate.rollup(selected, mode)["total_cost"]

        win = self.cfg.get("delta_window") or aggregate.delta_default(tf)
        if win not in [k for k, _ in aggregate.delta_window_options(tf)]:
            win = aggregate.delta_default(tf)
        delta = aggregate.recent_delta(selected, now, aggregate.delta_seconds(win), mode)

        self.indicator.set_label(fmt_cost(total), _LABEL_GUIDE)
        tf_label = dict(aggregate.TIMEFRAMES).get(tf, tf)
        self.header_item.set_label(
            f"{tf_label}: {fmt_cost(total)}    +{fmt_cost(delta)} ({win})"
        )

        # Tint the icon by spend over the fixed color window (independent of the
        # selected timeframe), so the color always means "recent activity".
        burn = aggregate.recent_delta(records, now, heat.COLOR_WINDOW_SECONDS, mode)
        b = heat.bucket(burn)
        if b != self._cur_bucket:
            self.indicator.set_icon_full(f"heat-{b:02d}", "Claude Usage Monitor")
            self._cur_bucket = b

    def _tick(self):
        self.refresh()
        return True  # keep the GLib timer running


def main():
    TrayApp()
    Gtk.main()
