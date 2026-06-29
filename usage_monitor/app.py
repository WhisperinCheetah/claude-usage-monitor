"""Always-on-top Tkinter widget showing Claude token usage and estimated cost."""
import math
import re
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime, timezone
from pathlib import Path

from usage_monitor import aggregate, config, heat, pricing, sparkline, status, transcripts
from usage_monitor.format import fmt_cost, fmt_spark_cost, fmt_tokens

REFRESH_MS = 3000
WINDOW_W = 384
WINDOW_H = 206
SPARK_H = 26
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
_COST_BURST = "#eafff2"  # peak of a per-turn "heartbeat" burst on a pricey turn
_FLASH_GREEN = "#7ee787"  # cheap-turn flash peak
_FLASH_HOT = "#d6f5dd"    # expensive-turn flash peak (soft bright green)
_FLASH_GREY = "#8a8a8a"
_DIM = "#777777"

# Cost-scaled flash tuning.
_FLASH_MIN_STEPS = 8     # fade steps for a cheap turn
_FLASH_MAX_STEPS = 22    # fade steps for a full-burn turn (lingers longer)
_BURST_THRESHOLD = 0.7   # intensity at/above which the cost total throbs
_BURST_STEP_MS = 55      # frame time for the heartbeat burst

# Responding-dot cluster.
_DOT_H = 16               # height of the dot canvas in the top bar
_DOT_R = 4                # dot radius
_DOT_GAP = 12            # horizontal step between dot centers
_DOT_UNKNOWN = "#9aa0a6"  # dot color when a session's model can't be resolved
_DOT_DARK = "#3a3a3a"     # shimmer floor a dot dims toward
_CYCLE_HOLD = 22          # pulse ticks (~90ms each) to hold each cycled name (~2s)


def flash_intensity(cost, full_cost):
    """Map a turn's cost to 0..1 flash intensity against the full-burn ceiling."""
    if not full_cost or full_cost <= 0 or cost <= 0:
        return 0.0
    return max(0.0, min(cost / full_cost, 1.0))


def project_name(cwd, max_len=18):
    """Short project label for a responding agent: basename of its cwd."""
    name = Path(cwd).name or str(cwd) or "?"
    if len(name) > max_len:
        name = name[: max_len - 1] + "…"
    return name


def cycle_index(n, tick, hold):
    """Which of `n` items is shown at `tick`, holding each for `hold` ticks."""
    if n <= 1 or hold <= 0:
        return 0
    return (tick // hold) % n


def flash_delta(prev_total, total):
    """New spend since the last poll (0.0 if none).

    Replaces the old per-*response* coalescing, which keyed off a single global
    "is anything responding?" flag. With several agents answering at once that
    flag stays true across the whole concurrent window, so the "one turn" it
    measured summed every agent's spend into a single giant flash (e.g. +$2347).
    A plain per-poll delta against the (monotonic) cumulative total is small,
    correct, and independent of how many agents are active.
    """
    return max(0.0, total - prev_total)


def _heartbeat_intensities(beats):
    """Throb shape for `beats` heartbeats: rise to 1, fall back, repeat, settle."""
    seq = []
    for _ in range(beats):
        seq += [0.0, 0.55, 1.0, 0.5, 0.15]
    seq.append(0.0)
    return seq


def _clamp_into_rect(x, y, win_w, win_h, rx, ry, rw, rh):
    """Clamp (x, y) so a win_w x win_h window sits fully inside one rectangle."""
    max_x = rx + max(0, rw - win_w)
    max_y = ry + max(0, rh - win_h)
    return min(max(x, rx), max_x), min(max(y, ry), max_y)


def clamp_to_screen(x, y, win_w, win_h, screen_w, screen_h):
    """Keep a window fully within a single screen rectangle anchored at 0,0."""
    return _clamp_into_rect(x, y, win_w, win_h, 0, 0, screen_w, screen_h)


def parse_xrandr_monitors(text):
    """Parse `xrandr --listmonitors` into a list of (x, y, w, h) rectangles.

    Each monitor line carries a geometry token like ``1920/477x1080/268+1920+507``
    (width/mm x height/mm + x + y). Returns [] if nothing parses.
    """
    rects = []
    for m in re.finditer(r"(\d+)/\d+x(\d+)/\d+\+(\d+)\+(\d+)", text):
        w, h, x, y = (int(g) for g in m.groups())
        rects.append((x, y, w, h))
    return rects


def _enable_windows_dpi_awareness():
    """Opt into per-monitor DPI awareness on Windows so the widget isn't blurry.

    No-op on other platforms. Must run before the first Tk window is created.
    """
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor (Win 8.1+)
        except (OSError, AttributeError):
            ctypes.windll.user32.SetProcessDPIAware()        # system DPI (Vista+)
    except (OSError, AttributeError):
        pass  # not Windows, or the call is unavailable


def _windows_virtual_screen():
    """Bounding rect (x, y, w, h) of the whole Windows virtual desktop, or None.

    Uses the SM_*VIRTUALSCREEN metrics so multi-monitor setups report every
    display, unlike Tk's winfo_screenwidth (primary only).
    """
    try:
        import ctypes
        get = ctypes.windll.user32.GetSystemMetrics
        # SM_XVIRTUALSCREEN=76, SM_YVIRTUALSCREEN=77, SM_CXVIRTUALSCREEN=78, SM_CYVIRTUALSCREEN=79
        x, y, w, h = (get(76), get(77), get(78), get(79))
        if w > 0 and h > 0:
            return (x, y, w, h)
    except (OSError, AttributeError):
        pass
    return None


def clamp_to_monitors(x, y, win_w, win_h, monitors):
    """Keep a window fully within a real monitor.

    A saved position can become invalid when the monitor layout changes (an
    external display unplugged or moved), leaving the widget off-screen and
    seemingly "not starting". The virtual-screen bounding box isn't enough:
    monitors at different offsets leave dead zones with no physical display.
    So clamp into the monitor that contains the point, else the nearest one.

    `monitors` is a list of (x, y, w, h). Returns the input unchanged when no
    monitor info is available (best-effort fallback for the caller).
    """
    if not monitors:
        return x, y

    def contains(m):
        mx, my, mw, mh = m
        return mx <= x < mx + mw and my <= y < my + mh

    chosen = next((m for m in monitors if contains(m)), None)
    if chosen is None:
        def dist2(m):
            mx, my, mw, mh = m
            return (mx + mw / 2 - x) ** 2 + (my + mh / 2 - y) ** 2
        chosen = min(monitors, key=dist2)
    return _clamp_into_rect(x, y, win_w, win_h, *chosen)


def _hex_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _blend(a, b, t):
    t = max(0.0, min(1.0, t))
    ar, ag, ab = _hex_rgb(a)
    br, bg, bb = _hex_rgb(b)
    return f"#{round(ar+(br-ar)*t):02x}{round(ag+(bg-ag)*t):02x}{round(ab+(bb-ab)*t):02x}"


def running_models(sessions, model_map):
    """Normalized model ids that have a currently-responding agent.

    `sessions` is `status.responding_sessions()` output; `model_map` is
    session_id -> model. Used to tint the per-model breakdown in the color of
    whichever models are live right now.
    """
    out = set()
    for s in sessions:
        # Prefer the model the hook stamped on the status file (authoritative
        # for the whole turn); fall back to the transcript-derived map.
        raw = s.get("model") or model_map.get(s["session_id"])
        if not raw:  # normalize_model() defaults blanks to Opus — don't guess
            continue
        out.add(pricing.normalize_model(raw))
    return out


class UsageMonitorApp:
    def __init__(self, projects_dir=None, config_file=None):
        self.projects_dir = projects_dir or transcripts.default_projects_dir()
        self.config_file = config_file or config.config_path()
        self.cfg = config.load_config(self.config_file)
        self.cache = transcripts.TranscriptCache()

        self.root = tk.Tk()
        self.root.title("Claude Usage")
        self._winsys = self.root.tk.call("tk", "windowingsystem")  # aqua | win32 | x11
        # Frameless everywhere except macOS, where borderless (overrideredirect)
        # windows are unreliable on Aqua — use a normal titled window there.
        self._frameless = self._winsys != "aqua"
        if self._frameless:
            self.root.overrideredirect(True)  # no native title bar / min / close
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")
        self.root.resizable(False, False)
        self.root.pack_propagate(False)  # fixed size — content never resizes the window
        geo = f"{WINDOW_W}x{WINDOW_H}"
        if self.cfg.get("x") is not None and self.cfg.get("y") is not None:
            x, y = clamp_to_monitors(
                self.cfg["x"], self.cfg["y"], WINDOW_W, WINDOW_H,
                self._monitor_rects(),
            )
            geo += f"+{x}+{y}"
        self.root.geometry(geo)

        # Animation / effect state.
        self._cost_shown = 0.0           # currently-displayed cost (for roll-up)
        self._cost_target = 0.0
        self._cost_animating = False
        # Cumulative cost at the last refresh; the +$ flash shows the delta.
        self._last_total = None          # None until the first refresh baselines it
        self._hot = False                # recent burn in the top bucket -> pulse
        self._pulse_phase = 0.0
        self._flash_seq = []             # per-turn fade colors (built on each flash)
        self._flash_idx = 0              # index into _flash_seq; >= len means idle
        self._dragged = False            # did the last press actually move the window?
        self._bd_labels = []             # reused per-model breakdown segment labels

        # "Responding now" dot state (fed by usage_monitor.status).
        self._responding = False
        self._model_norm = None          # normalized model of the newest record (idle)
        self._responding_sessions = []   # [{session_id, cwd, ts}] currently responding
        self._model_map = {}             # session_id -> model, for per-agent dot color
        self._dot_phase = 0.0            # shimmer phase for the responding dots
        self._dot_tick = 0               # advances each pulse; drives the name cycle

        # Per-turn "heartbeat" burst on a pricey turn (overrides the hot pulse).
        self._burst_seq = []
        self._burst_idx = 0

        self._build_widgets()
        self._bind_drag()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _monitor_rects(self):
        """Monitor rectangles used to keep the restored window on-screen.

        Returns [] when we can't enumerate reliably, in which case the caller
        leaves the saved position untouched. We deliberately do NOT fall back
        to winfo_screen{width,height}: on Windows and macOS those report the
        *primary* monitor only, so clamping to them would drag a window that
        legitimately lives on a secondary monitor back onto the primary.
        """
        if self._winsys == "x11":
            # X11 reports the full virtual screen, but offset monitors leave
            # dead zones inside the bounding box — ask xrandr for the real rects.
            try:
                out = subprocess.run(
                    ["xrandr", "--listmonitors"],
                    capture_output=True, text=True, timeout=2,
                ).stdout
                rects = parse_xrandr_monitors(out)
                if rects:
                    return rects
            except (OSError, subprocess.SubprocessError):
                pass
            # Frameless on X11; a single-monitor bounding box is a safe net.
            return [(0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())]
        if self._winsys == "win32":
            # Frameless on Windows too, so it needs the net — but use the whole
            # virtual desktop (all monitors), not just the primary.
            rect = _windows_virtual_screen()
            if rect:
                return [rect]
            return []
        # aqua: a normal titled window the OS keeps reachable — don't clamp.
        return []

    def _label(self, parent, text, **kw):
        opts = dict(bg="#1e1e1e", fg="#dddddd", font=("TkDefaultFont", 10))
        opts.update(kw)
        return tk.Label(parent, text=text, **opts)

    def _build_widgets(self):
        # Top bar: responding-agent dots (left), per-turn flash + close (right).
        topbar = tk.Frame(self.root, bg="#1e1e1e")
        topbar.pack(fill="x", padx=8, pady=(6, 0))
        # Right-side widgets are packed first so the dot canvas fills what's left.
        close_btn = self._label(topbar, "✕", fg="#888888", font=("TkDefaultFont", 10, "bold"))
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda _e: self._on_close())
        self.flash_label = self._label(topbar, "", fg=_FLASH_GREY, font=("TkDefaultFont", 9))
        self.flash_label.pack(side="right", padx=(0, 8))
        # One model-colored dot per responding agent + a (cycling) project name.
        self.dots = tk.Canvas(topbar, height=_DOT_H, bg="#1e1e1e", highlightthickness=0)
        self.dots.pack(side="left", fill="x", expand=True)

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

        # Per-model usage breakdown. Each segment is tinted in its model
        # ("agent") color while a session on that model is responding, and dim
        # otherwise — a running indicator right under the total cost. A frame of
        # per-segment labels is needed because one Label can't be multi-colored.
        self.breakdown_frame = tk.Frame(body, bg="#1e1e1e")
        self.breakdown_frame.pack(anchor="w")

        # Sparkline of recent cost; click to cycle its range.
        self.spark = tk.Canvas(self.root, height=SPARK_H, bg="#1e1e1e", highlightthickness=0)
        self.spark.pack(fill="x", padx=8, pady=(2, 2))
        self.spark.bind("<Button-1>", self._cycle_spark_range)
        # Cached so per-bar label fit checks measure the exact render font.
        self._spark_font = tkfont.Font(font=("TkDefaultFont", 8))

        self._drag_targets = [self.root, topbar, self.dots, self.flash_label,
                              body, cost_row, self.tokens_label, self.cost_label,
                              self.delta_label, self.breakdown_frame]

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

    def _flash_turn(self, cost, intensity):
        """Per-turn flash, scaled to cost: pricier turns flash hotter and linger
        longer; a big enough turn also throbs the cost total."""
        intensity = max(0.0, min(intensity, 1.0))
        peak = _blend(_FLASH_GREEN, _FLASH_HOT, intensity)
        n = round(_FLASH_MIN_STEPS + (_FLASH_MAX_STEPS - _FLASH_MIN_STEPS) * intensity)
        self._flash_seq = [_blend(peak, _FLASH_GREY, i / (n - 1)) for i in range(n)]
        self.flash_label.config(text=f"+{fmt_cost(cost)}", fg=self._flash_seq[0])
        self._flash_idx = 1
        self.root.after(110, self._flash_step)
        if intensity >= _BURST_THRESHOLD:
            self._start_burst(beats=3 if intensity >= 0.85 else 2)

    def _flash_step(self):
        if self._flash_idx >= len(self._flash_seq):
            return  # stays at the final grey
        self.flash_label.config(fg=self._flash_seq[self._flash_idx])
        self._flash_idx += 1
        self.root.after(110, self._flash_step)

    def _update_turn_flash(self, records, mode):
        """Flash the +$ for new spend since the last refresh."""
        total = aggregate.rollup(records, mode)["total_cost"]
        if self._last_total is not None:      # skip the first load (baseline only)
            self._flash_cost(flash_delta(self._last_total, total))
        self._last_total = total

    def _flash_cost(self, turn_cost):
        if turn_cost <= 0.0005:           # ignore noise / no real new spend
            return
        intensity = flash_intensity(turn_cost, self.cfg.get("flash_full_cost", 0.25))
        self._flash_turn(turn_cost, intensity)

    def _start_burst(self, beats):
        self._burst_seq = _heartbeat_intensities(beats)
        self._burst_idx = 0
        self._burst_step()

    def _burst_step(self):
        if self._burst_idx >= len(self._burst_seq):
            self._burst_seq = []  # hand the cost color back to _pulse_step
            return
        t = self._burst_seq[self._burst_idx]
        self.cost_label.config(fg=_blend(_COST_BASE, _COST_BURST, t))
        self._burst_idx += 1
        self.root.after(_BURST_STEP_MS, self._burst_step)

    def _pulse_step(self):
        # A heartbeat burst temporarily owns the cost-number color.
        if not self._burst_seq:
            if self._hot:
                self._pulse_phase += 0.20
                t = (math.sin(self._pulse_phase) + 1) / 2
                self.cost_label.config(fg=_blend(_COST_BASE, _COST_HOT, t))
            else:
                self.cost_label.config(fg=_COST_BASE)
        if self._responding_sessions:
            self._dot_phase += 0.30
            self._dot_tick += 1
        self._render_dots()
        self.root.after(90, self._pulse_step)

    def _update_model_dot(self, model):
        # Newest record's model — used for the idle dot when nothing responds.
        self._model_norm = pricing.normalize_model(model) if model else None
        self._render_dots()

    def _dot_color(self, session):
        # Same model source as the breakdown (hook first, then transcript map)
        # so the dot and the per-agent tint can never disagree.
        raw = session.get("model") or self._model_map.get(session["session_id"], "")
        if not raw:
            return _DOT_UNKNOWN
        return _MODEL_COLORS.get(pricing.normalize_model(raw), _DOT_UNKNOWN)

    def _render_dots(self):
        """Draw the responding-agent dot cluster (or the idle model dot)."""
        c = self.dots
        c.delete("all")
        y = _DOT_H // 2
        sessions = self._responding_sessions

        if not sessions:  # idle: one steady dot + the newest model's short name
            if self._model_norm is None:
                c.create_oval(0, y - _DOT_R, 2 * _DOT_R, y + _DOT_R, fill=_DIM, width=0)
                c.create_text(2 * _DOT_R + 6, y, anchor="w", text="—", fill=_DIM,
                              font=("TkDefaultFont", 9))
                return
            base = _MODEL_COLORS.get(self._model_norm, _DOT_UNKNOWN)
            short = _MODEL_SHORT.get(self._model_norm, self._model_norm)
            c.create_oval(0, y - _DOT_R, 2 * _DOT_R, y + _DOT_R, fill=base, width=0)
            c.create_text(2 * _DOT_R + 6, y, anchor="w", text=short, fill=base,
                          font=("TkDefaultFont", 9))
            return

        n = len(sessions)
        active = cycle_index(n, self._dot_tick, _CYCLE_HOLD)
        t = (math.sin(self._dot_phase) + 1) / 2
        for i, s in enumerate(sessions):
            base = self._dot_color(s)
            # The currently-named agent's dot glows bright; the rest shimmer dim.
            lo, hi = (0.7, 1.0) if i == active else (0.2, 0.55)
            color = _blend(_DOT_DARK, base, lo + (hi - lo) * t)
            cx = _DOT_R + i * _DOT_GAP
            c.create_oval(cx - _DOT_R, y - _DOT_R, cx + _DOT_R, y + _DOT_R,
                          fill=color, width=0)
        text_x = _DOT_R + (n - 1) * _DOT_GAP + _DOT_R + 7
        name = project_name(sessions[active]["cwd"])
        c.create_text(text_x, y, anchor="w", text=name,
                      fill=_blend(self._dot_color(sessions[active]), "#f0f0f0", 0.5),
                      font=("TkDefaultFont", 9))

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
                self._draw_bar_label(c, fmt_spark_cost(v), x0, x1, y0, y1, color)
        c.create_text(2, 0, anchor="nw", text=self.cfg.get("spark_range", "24h"),
                      fill="#666666", font=("TkDefaultFont", 7))

    def _draw_bar_label(self, c, label, x0, x1, y0, y1, bar_color):
        """A small darker $ value at the bottom inside a bar, only if it fits.

        Skipped when the bar is too narrow for the text or too short to contain
        a line of it — so zero/tiny bars stay clean."""
        if not label:
            return
        f = self._spark_font
        if f.measure(label) > (x1 - x0) - 1:    # too narrow
            return
        ascent = f.metrics("ascent")
        if (y1 - y0) < ascent + 1:              # too short to hold a digit
            return
        # Anchor "s" pins the text box bottom (baseline + descent) at `y`;
        # pushing y down by the descent lands the digit baseline on the bar's
        # bottom edge so the number sits flush on it.
        baseline_y = y1 + f.metrics("descent") - 2
        c.create_text((x0 + x1) / 2, baseline_y, anchor="s", text=label,
                      fill=_blend(bar_color, "#000000", 0.62), font=f)

    def _cycle_spark_range(self, _event=None):
        self.cfg["spark_range"] = sparkline.next_range(self.cfg.get("spark_range", "24h"))
        config.save_config(self.config_file, self.cfg)
        self.refresh()

    def _bind_drag(self):
        for w in self._drag_targets:
            self._bind_drag_widget(w)

    def _bind_drag_widget(self, w):
        w.bind("<Button-1>", self._start_drag)
        w.bind("<B1-Motion>", self._on_drag)
        w.bind("<ButtonRelease-1>", self._end_drag)

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()
        self._dragged = False

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self._dragged = True
        self.root.geometry(f"+{x}+{y}")

    def _end_drag(self, _event=None):
        # Persist position the moment a drag ends, so the widget reopens where
        # the user left it even if the process is later killed (reboot, crash,
        # recovery) without a clean close. Previously position only persisted on
        # a settings change or ✕-close, so a kill reverted to a stale position.
        if self._dragged:
            self._dragged = False
            self._save()

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

        # Local-aware: the sparkline aligns day/hour buckets to this timezone,
        # so day bars reset at the user's midnight, not UTC. All other uses are
        # absolute-time comparisons/timestamps, unaffected by the offset.
        now = datetime.now().astimezone()
        result = aggregate.rollup(selected, mode)
        self.tokens_label.config(text=f"Tokens   {fmt_tokens(result['total_tokens'])}")
        self._set_cost(result["total_cost"])  # animated roll-up

        # Live responding state (hook-fed per-session files). Resolved here
        # because it also tints the per-model breakdown in each running agent's
        # color, alongside feeding the top responding-dot cluster.
        self._responding_sessions = status.responding_sessions(now=now.timestamp())
        self._responding = bool(self._responding_sessions)
        self._model_map = aggregate.model_by_session(records)
        self._render_breakdown(
            result["by_model"],
            running_models(self._responding_sessions, self._model_map),
        )

        win = self.delta_var.get()
        delta = aggregate.recent_delta(selected, now, aggregate.delta_seconds(win), mode)
        self.delta_label.config(
            text=f"+{fmt_cost(delta)} ({win})",
            fg=_COST_BASE if delta > 0 else _DIM,
        )

        newest = aggregate.latest_record(records)
        self._update_model_dot(newest.model if newest else None)
        self._update_turn_flash(records, mode)

        # Pulse the cost number when recent burn is in the top heat bucket.
        burn = aggregate.recent_delta(records, now, heat.COLOR_WINDOW_SECONDS, mode)
        self._hot = heat.bucket(burn) >= HOT_BUCKET

        self._draw_sparkline(sparkline.bucketize(
            records, now, self.cfg.get("spark_range", "24h"), mode))

        self.status_label.config(text=f"● updated {datetime.now().strftime('%H:%M:%S')}")

    def _render_breakdown(self, by_model, running):
        """Update the per-model usage line *in place*, tinting each model's
        segment in its model ("agent") color while a session on that model is
        responding, and dimming the rest. `running` is a set of normalized model
        ids.

        Labels are reused across refreshes — recreating them every tick made the
        line blink invisible→visible as Tk briefly painted the empty frame.
        """
        if by_model:
            tokens = []
            for i, (model, vals) in enumerate(
                    sorted(by_model.items(), key=lambda kv: -kv[1]["cost"])):
                if i:
                    tokens.append((" · ", "#555555"))
                color = _MODEL_COLORS.get(model, _DOT_UNKNOWN) if model in running else "#999999"
                tokens.append((f"{_MODEL_SHORT.get(model, model)} {fmt_cost(vals['cost'])}", color))
        else:
            tokens = [("no usage in range", "#999999")]

        # Grow the reusable label pool as needed (never shrink — just hide).
        while len(self._bd_labels) < len(tokens):
            lbl = self._label(self.breakdown_frame, "", font=("TkDefaultFont", 9))
            lbl.pack(side="left")
            self._bind_drag_widget(lbl)
            self._bd_labels.append(lbl)
        for lbl, (text, fg) in zip(self._bd_labels, tokens):
            lbl.config(text=text, fg=fg)
            if lbl.winfo_manager() != "pack":  # re-show one hidden earlier
                lbl.pack(side="left")
        for lbl in self._bd_labels[len(tokens):]:
            if lbl.winfo_manager() == "pack":
                lbl.pack_forget()

    def _tick(self):
        self.refresh()
        self.root.after(REFRESH_MS, self._tick)

    def run(self):
        self.root.after(0, self._tick)
        self.root.after(90, self._pulse_step)  # continuous; only glows when hot
        self.root.mainloop()


def main():
    _enable_windows_dpi_awareness()  # before any Tk window is created
    UsageMonitorApp().run()
