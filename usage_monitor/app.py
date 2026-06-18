"""Always-on-top Tkinter widget showing Claude token usage and estimated cost."""
import math
import tkinter as tk
from datetime import datetime, timezone

from usage_monitor import aggregate, config, heat, pricing, sparkline, transcripts
from usage_monitor.format import fmt_cost, fmt_tokens

REFRESH_MS = 3000
WINDOW_W = 384
WINDOW_H = 206
SPARK_H = 26
SEMI_ALPHA = 0.85  # opacity when "semi-transparent" is on (whole window, incl. text)
HOT_BUCKET = 11    # heat bucket (of 16) at/above which the cost number pulses
_MODE_LABELS = [("accurate", "Accurate"), ("simple", "Simple")]
_MODEL_SHORT = {
    "claude-opus-4-8": "Opus",
    "claude-sonnet-4-6": "Sonnet",
    "claude-haiku-4-5": "Haiku",
}
_MODEL_COLORS = {
    "claude-opus-4-8": "#7ec699",
    "claude-sonnet-4-6": "#6fb3d9",
    "claude-haiku-4-5": "#c39bd3",
}
_COST_BASE = "#7ec699"   # normal cost-number color
_COST_HOT = "#caf7d8"    # peak of the "hot" pulse
_FLASH_GREEN = "#7ee787"
_FLASH_GREY = "#8a8a8a"
_DIM = "#777777"


def _hex_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _blend(a, b, t):
    t = max(0.0, min(1.0, t))
    ar, ag, ab = _hex_rgb(a)
    br, bg, bb = _hex_rgb(b)
    return f"#{round(ar+(br-ar)*t):02x}{round(ag+(bg-ag)*t):02x}{round(ab+(bb-ab)*t):02x}"


def _flash_sequence(n=10):
    return [_blend(_FLASH_GREEN, _FLASH_GREY, i / (n - 1)) for i in range(n)]


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

        self._translucent = bool(self.cfg.get("translucent", False))
        self.root.attributes("-alpha", SEMI_ALPHA if self._translucent else 1.0)

        # Animation / effect state.
        self._cost_shown = 0.0           # currently-displayed cost (for roll-up)
        self._cost_target = 0.0
        self._cost_animating = False
        self._last_msg_id = None         # for "cost of that answer" flash
        self._hot = False                # recent burn in the top bucket -> pulse
        self._pulse_phase = 0.0
        self._flash_seq = _flash_sequence()
        self._flash_idx = len(self._flash_seq)  # idle

        self._build_widgets()
        self._build_context_menu()
        self._bind_drag()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _label(self, parent, text, **kw):
        opts = dict(bg="#1e1e1e", fg="#dddddd", font=("TkDefaultFont", 10))
        opts.update(kw)
        return tk.Label(parent, text=text, **opts)

    def _build_widgets(self):
        # Top bar: "currently on" model dot (left), per-turn flash + close (right).
        topbar = tk.Frame(self.root, bg="#1e1e1e")
        topbar.pack(fill="x", padx=8, pady=(6, 0))
        self.model_label = self._label(topbar, "● —", fg=_DIM,
                                       font=("TkDefaultFont", 9, "bold"))
        self.model_label.pack(side="left")
        close_btn = self._label(topbar, "✕", fg="#888888", font=("TkDefaultFont", 10, "bold"))
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda _e: self._on_close())
        self.flash_label = self._label(topbar, "", fg=_FLASH_GREY, font=("TkDefaultFont", 9))
        self.flash_label.pack(side="right", padx=(0, 8))

        # Controls live at the bottom so their opened menus don't cover the figures.
        controls = tk.Frame(self.root, bg="#1e1e1e")
        controls.pack(side="bottom", fill="x", padx=8, pady=(2, 8))

        self.tf_var = tk.StringVar()
        tf_labels = [label for _, label in aggregate.TIMEFRAMES]
        self.tf_var.set(self._label_for_key(aggregate.TIMEFRAMES, self.cfg["timeframe"]))
        tf_menu = tk.OptionMenu(controls, self.tf_var, *tf_labels,
                                command=lambda _=None: self._on_timeframe_change())
        # Fixed width (in chars) so the chosen label's length never changes layout.
        tf_menu.config(bg="#2d2d2d", fg="#dddddd", highlightthickness=0, font=("TkDefaultFont", 9),
                       width=15, anchor="w")
        tf_menu.pack(side="left")

        # Delta-window selector — options/default scale with the timeframe.
        self.delta_var = tk.StringVar()
        self.delta_var.set(self._initial_delta_key())
        self.delta_menu = tk.OptionMenu(controls, self.delta_var, self.delta_var.get())
        self.delta_menu.config(bg="#2d2d2d", fg="#dddddd", highlightthickness=0,
                               font=("TkDefaultFont", 9), width=4, anchor="w")
        self.delta_menu.pack(side="left", padx=(6, 0))
        self._populate_delta_menu()

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

        cost_row = tk.Frame(body, bg="#1e1e1e")
        cost_row.pack(anchor="w", fill="x")
        self.cost_label = self._label(cost_row, "Cost     —", font=("TkDefaultFont", 14, "bold"), fg=_COST_BASE)
        self.cost_label.pack(side="left")
        self.delta_label = self._label(cost_row, "", font=("TkDefaultFont", 10), fg=_DIM)
        self.delta_label.pack(side="left", padx=(8, 0))

        self.breakdown_label = self._label(body, "", fg="#999999", font=("TkDefaultFont", 9))
        self.breakdown_label.pack(anchor="w")

        # Sparkline of recent cost; click to cycle its range.
        self.spark = tk.Canvas(self.root, height=SPARK_H, bg="#1e1e1e", highlightthickness=0)
        self.spark.pack(fill="x", padx=8, pady=(2, 2))
        self.spark.bind("<Button-1>", self._cycle_spark_range)

        self._drag_targets = [self.root, topbar, self.model_label, self.flash_label,
                              body, cost_row, self.tokens_label, self.cost_label,
                              self.delta_label, self.breakdown_label]

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

    def _initial_delta_key(self):
        tf = self.cfg["timeframe"]
        valid = [k for k, _ in aggregate.delta_window_options(tf)]
        saved = self.cfg.get("delta_window")
        return saved if saved in valid else aggregate.delta_default(tf)

    def _populate_delta_menu(self):
        tf = self._current_timeframe_key()
        opts = [k for k, _ in aggregate.delta_window_options(tf)]
        menu = self.delta_menu["menu"]
        menu.delete(0, "end")
        for key in opts:
            menu.add_command(label=key, command=lambda v=key: self._select_delta(v))
        if self.delta_var.get() not in opts:
            self.delta_var.set(aggregate.delta_default(tf))

    def _select_delta(self, key):
        self.delta_var.set(key)
        self._on_setting_change()

    # --- effects -------------------------------------------------------------

    def _set_cost(self, target):
        """Animate the cost number rolling toward `target`."""
        self._cost_target = target
        if not self._cost_animating:
            self._cost_animating = True
            self._cost_tick()

    def _cost_tick(self):
        diff = self._cost_target - self._cost_shown
        if abs(diff) < 0.005:
            self._cost_shown = self._cost_target
            self._cost_animating = False
        else:
            self._cost_shown += diff * 0.3  # exponential ease toward target
        self.cost_label.config(text=f"Cost     {fmt_cost(self._cost_shown)}")
        if self._cost_animating:
            self.root.after(30, self._cost_tick)

    def _flash_turn(self, cost):
        """Subtle per-turn flash: bright green fading to grey, then it lingers."""
        self.flash_label.config(text=f"+{fmt_cost(cost)}", fg=self._flash_seq[0])
        self._flash_idx = 1
        self.root.after(110, self._flash_step)

    def _flash_step(self):
        if self._flash_idx >= len(self._flash_seq):
            return  # stays at the final grey
        self.flash_label.config(fg=self._flash_seq[self._flash_idx])
        self._flash_idx += 1
        self.root.after(110, self._flash_step)

    def _pulse_step(self):
        if self._hot:
            self._pulse_phase += 0.20
            t = (math.sin(self._pulse_phase) + 1) / 2
            self.cost_label.config(fg=_blend(_COST_BASE, _COST_HOT, t))
        else:
            self.cost_label.config(fg=_COST_BASE)
        self.root.after(90, self._pulse_step)

    def _update_model_dot(self, model):
        if not model:
            self.model_label.config(text="● —", fg=_DIM)
            return
        norm = pricing.normalize_model(model)
        short = _MODEL_SHORT.get(norm, norm)
        self.model_label.config(text=f"● {short}", fg=_MODEL_COLORS.get(norm, "#aaaaaa"))

    def _draw_sparkline(self, values):
        c = self.spark
        c.delete("all")
        w = c.winfo_width() or (WINDOW_W - 16)
        n = len(values)
        if n:
            mx = max(values) or 1.0
            bw = w / n
            for i, v in enumerate(values):
                if v <= 0:
                    continue
                bh = (v / mx) * (SPARK_H - 6)
                x0, x1 = i * bw + 1, (i + 1) * bw - 1
                y1, y0 = SPARK_H - 2, SPARK_H - 2 - bh
                color = _COST_HOT if i == n - 1 else _COST_BASE  # newest bar brighter
                c.create_rectangle(x0, y0, x1, y1, fill=color, width=0)
        c.create_text(2, 0, anchor="nw", text=self.cfg.get("spark_range", "24h"),
                      fill="#666666", font=("TkDefaultFont", 7))

    def _cycle_spark_range(self, _event=None):
        self.cfg["spark_range"] = sparkline.next_range(self.cfg.get("spark_range", "24h"))
        config.save_config(self.config_file, self.cfg)
        self.refresh()

    def _build_context_menu(self):
        self._translucent_var = tk.BooleanVar(value=self._translucent)
        self._ctx = tk.Menu(self.root, tearoff=0)
        self._ctx.add_checkbutton(label="Semi-transparent",
                                  variable=self._translucent_var,
                                  command=self._toggle_opacity)
        self._ctx.add_separator()
        self._ctx.add_command(label="Quit", command=self._on_close)

    def _show_context_menu(self, event):
        self._ctx.tk_popup(event.x_root, event.y_root)

    def _toggle_opacity(self):
        self._translucent = self._translucent_var.get()
        self.root.attributes("-alpha", SEMI_ALPHA if self._translucent else 1.0)
        self._save()

    def _bind_drag(self):
        for w in self._drag_targets:
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<Button-3>", self._show_context_menu)

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

    def _on_timeframe_change(self):
        # Reset the delta window to the new timeframe's scaled default, then
        # rebuild the selectable options for it.
        self.delta_var.set(aggregate.delta_default(self._current_timeframe_key()))
        self._populate_delta_menu()
        self._save()
        self.refresh()

    def _save(self):
        self.cfg["timeframe"] = self._current_timeframe_key()
        self.cfg["mode"] = self._current_mode_key()
        self.cfg["delta_window"] = self.delta_var.get()
        self.cfg["translucent"] = self._translucent
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

        now = datetime.now(timezone.utc)
        result = aggregate.rollup(selected, mode)
        self.tokens_label.config(text=f"Tokens   {fmt_tokens(result['total_tokens'])}")
        self._set_cost(result["total_cost"])  # animated roll-up
        self.breakdown_label.config(text=self._breakdown_text(result["by_model"]))

        win = self.delta_var.get()
        delta = aggregate.recent_delta(selected, now, aggregate.delta_seconds(win), mode)
        self.delta_label.config(
            text=f"+{fmt_cost(delta)} ({win})",
            fg=_COST_BASE if delta > 0 else _DIM,
        )

        # "Currently on" dot + per-turn flash, both keyed off the newest record.
        newest = aggregate.latest_record(records)
        self._update_model_dot(newest.model if newest else None)
        if newest is not None and newest.message_id != self._last_msg_id:
            if self._last_msg_id is not None:  # don't flash on first load
                turn_cost = pricing.cost_for(
                    newest.model, newest.input, newest.output,
                    newest.cache_creation, newest.cache_read, mode,
                )
                self._flash_turn(turn_cost)
            self._last_msg_id = newest.message_id

        # Pulse the cost number when recent burn is in the top heat bucket.
        burn = aggregate.recent_delta(records, now, heat.COLOR_WINDOW_SECONDS, mode)
        self._hot = heat.bucket(burn) >= HOT_BUCKET

        self._draw_sparkline(sparkline.bucketize(
            records, now, self.cfg.get("spark_range", "24h"), mode))

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
        self.root.after(90, self._pulse_step)  # continuous; only glows when hot
        self.root.mainloop()


def main():
    UsageMonitorApp().run()
