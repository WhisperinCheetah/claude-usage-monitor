"""Always-on-top Tkinter widget showing Claude token usage and estimated cost."""
import tkinter as tk
from datetime import datetime, timezone

from usage_monitor import aggregate, config, transcripts
from usage_monitor.format import fmt_cost, fmt_tokens

REFRESH_MS = 3000
WINDOW_W = 360
WINDOW_H = 168
_MODE_LABELS = [("accurate", "Accurate"), ("simple", "Simple")]
_MODEL_SHORT = {
    "claude-opus-4-8": "Opus",
    "claude-sonnet-4-6": "Sonnet",
    "claude-haiku-4-5": "Haiku",
}


class UsageMonitorApp:
    def __init__(self, projects_dir=None, config_file=None):
        self.projects_dir = projects_dir or transcripts.default_projects_dir()
        self.config_file = config_file or config.config_path()
        self.cfg = config.load_config(self.config_file)
        self.cache = transcripts.TranscriptCache()

        self.root = tk.Tk()
        self.root.title("Claude Usage")
        self.root.overrideredirect(True)  # no native title bar / min / close
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")
        self.root.resizable(False, False)
        self.root.pack_propagate(False)  # fixed size — content never resizes the window
        geo = f"{WINDOW_W}x{WINDOW_H}"
        if self.cfg.get("x") is not None and self.cfg.get("y") is not None:
            geo += f"+{self.cfg['x']}+{self.cfg['y']}"
        self.root.geometry(geo)

        self._build_widgets()
        self._bind_drag()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _label(self, parent, text, **kw):
        opts = dict(bg="#1e1e1e", fg="#dddddd", font=("TkDefaultFont", 10))
        opts.update(kw)
        return tk.Label(parent, text=text, **opts)

    def _build_widgets(self):
        # Top bar: title + close button (substitutes for the removed native bar).
        topbar = tk.Frame(self.root, bg="#1e1e1e")
        topbar.pack(fill="x", padx=8, pady=(6, 0))
        title = self._label(topbar, "Claude Usage", fg="#aaaaaa", font=("TkDefaultFont", 9, "bold"))
        title.pack(side="left")
        close_btn = self._label(topbar, "✕", fg="#888888", font=("TkDefaultFont", 10, "bold"))
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda _e: self._on_close())

        # Controls live at the bottom so their opened menus don't cover the figures.
        controls = tk.Frame(self.root, bg="#1e1e1e")
        controls.pack(side="bottom", fill="x", padx=8, pady=(2, 8))

        self.tf_var = tk.StringVar()
        tf_labels = [label for _, label in aggregate.TIMEFRAMES]
        self.tf_var.set(self._label_for_key(aggregate.TIMEFRAMES, self.cfg["timeframe"]))
        tf_menu = tk.OptionMenu(controls, self.tf_var, *tf_labels, command=lambda _=None: self._on_setting_change())
        # Fixed width (in chars) so the chosen label's length never changes layout.
        tf_menu.config(bg="#2d2d2d", fg="#dddddd", highlightthickness=0, font=("TkDefaultFont", 9),
                       width=14, anchor="w")
        tf_menu.pack(side="left")

        self.mode_var = tk.StringVar()
        mode_labels = [label for _, label in _MODE_LABELS]
        self.mode_var.set(self._label_for_key(_MODE_LABELS, self.cfg["mode"]))
        mode_menu = tk.OptionMenu(controls, self.mode_var, *mode_labels, command=lambda _=None: self._on_setting_change())
        mode_menu.config(bg="#2d2d2d", fg="#dddddd", highlightthickness=0, font=("TkDefaultFont", 9),
                         width=8, anchor="w")
        mode_menu.pack(side="right")

        self.status_label = self._label(self.root, "● starting…", fg="#777777", font=("TkDefaultFont", 8))
        self.status_label.pack(side="bottom", anchor="w", padx=8)

        body = tk.Frame(self.root, bg="#1e1e1e")
        body.pack(fill="x", padx=8, pady=(4, 2))
        self.tokens_label = self._label(body, "Tokens   —", font=("TkDefaultFont", 11))
        self.tokens_label.pack(anchor="w")
        self.cost_label = self._label(body, "Cost     —", font=("TkDefaultFont", 14, "bold"), fg="#7ec699")
        self.cost_label.pack(anchor="w")
        self.breakdown_label = self._label(body, "", fg="#999999", font=("TkDefaultFont", 9))
        self.breakdown_label.pack(anchor="w")

        self._drag_targets = [self.root, topbar, title, body,
                              self.tokens_label, self.cost_label, self.breakdown_label]

    @staticmethod
    def _label_for_key(pairs, key):
        for k, label in pairs:
            if k == key:
                return label
        return pairs[0][1]

    @staticmethod
    def _key_for_label(pairs, label):
        for k, lab in pairs:
            if lab == label:
                return k
        return pairs[0][0]

    def _bind_drag(self):
        for w in self._drag_targets:
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _current_timeframe_key(self):
        return self._key_for_label(aggregate.TIMEFRAMES, self.tf_var.get())

    def _current_mode_key(self):
        return self._key_for_label(_MODE_LABELS, self.mode_var.get())

    def _on_setting_change(self):
        self._save()
        self.refresh()

    def _save(self):
        self.cfg["timeframe"] = self._current_timeframe_key()
        self.cfg["mode"] = self._current_mode_key()
        self.cfg["x"] = self.root.winfo_x()
        self.cfg["y"] = self.root.winfo_y()
        config.save_config(self.config_file, self.cfg)

    def _on_close(self):
        self._save()
        self.root.destroy()

    def refresh(self):
        paths = transcripts.find_transcripts(self.projects_dir)
        records = transcripts.dedup(self.cache.load(paths))
        tf = self._current_timeframe_key()
        mode = self._current_mode_key()

        if tf == "session":
            newest = aggregate.session_file(paths)
            selected = aggregate.filter_by_file(records, newest) if newest else []
        else:
            start, end = aggregate.timeframe_bounds(tf, datetime.now(timezone.utc))
            selected = aggregate.filter_by_time(records, start, end)

        result = aggregate.rollup(selected, mode)
        self.tokens_label.config(text=f"Tokens   {fmt_tokens(result['total_tokens'])}")
        self.cost_label.config(text=f"Cost     {fmt_cost(result['total_cost'])}")
        self.breakdown_label.config(text=self._breakdown_text(result["by_model"]))
        self.status_label.config(text=f"● updated {datetime.now().strftime('%H:%M:%S')}")

    @staticmethod
    def _breakdown_text(by_model):
        if not by_model:
            return "no usage in range"
        parts = []
        for model, vals in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"]):
            short = _MODEL_SHORT.get(model, model)
            parts.append(f"{short} {fmt_cost(vals['cost'])}")
        return " · ".join(parts)

    def _tick(self):
        self.refresh()
        self.root.after(REFRESH_MS, self._tick)

    def run(self):
        self.root.after(0, self._tick)
        self.root.mainloop()


def main():
    UsageMonitorApp().run()
