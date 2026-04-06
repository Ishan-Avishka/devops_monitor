"""
utils.py - Shared utilities, constants, and theming for DevOps Monitor
"""
import tkinter as tk
from tkinter import ttk
import time
import datetime
import threading


# ─── COLOR PALETTE ────────────────────────────────────────────────────────────
COLORS = {
    "bg_dark":       "#0A0E1A",
    "bg_panel":      "#0F1628",
    "bg_card":       "#141C35",
    "bg_hover":      "#1A2340",
    "accent_blue":   "#00D4FF",
    "accent_green":  "#00FF88",
    "accent_red":    "#FF3366",
    "accent_yellow": "#FFD700",
    "accent_purple": "#9B59B6",
    "accent_orange": "#FF6B35",
    "text_primary":  "#E8EAF6",
    "text_secondary":"#7986CB",
    "text_muted":    "#3D4A6B",
    "border":        "#1E2D4A",
    "border_bright": "#2E4070",
    "success":       "#00FF88",
    "warning":       "#FFD700",
    "danger":        "#FF3366",
    "info":          "#00D4FF",
    "chart_bg":      "#0A0E1A",
    "grid_line":     "#1A2340",
}

# ─── FONTS ────────────────────────────────────────────────────────────────────
FONTS = {
    "title":      ("Courier New", 20, "bold"),
    "heading":    ("Courier New", 14, "bold"),
    "subheading": ("Courier New", 11, "bold"),
    "body":       ("Courier New", 10),
    "small":      ("Courier New", 9),
    "mono":       ("Courier New", 10),
    "mono_small": ("Courier New", 9),
    "metric":     ("Courier New", 24, "bold"),
    "metric_sm":  ("Courier New", 16, "bold"),
    "label":      ("Courier New", 9),
}


# ─── CONFIGURE TTK STYLES ─────────────────────────────────────────────────────
def apply_theme(root: tk.Tk):
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".",
        background=COLORS["bg_dark"],
        foreground=COLORS["text_primary"],
        fieldbackground=COLORS["bg_card"],
        troughcolor=COLORS["bg_panel"],
        selectbackground=COLORS["accent_blue"],
        selectforeground=COLORS["bg_dark"],
        insertcolor=COLORS["accent_blue"],
        bordercolor=COLORS["border"],
        darkcolor=COLORS["bg_panel"],
        lightcolor=COLORS["bg_card"],
        relief="flat",
        font=FONTS["body"],
    )

    style.configure("TFrame", background=COLORS["bg_dark"])
    style.configure("Card.TFrame", background=COLORS["bg_card"],
                    relief="flat", borderwidth=1)

    style.configure("TLabel",
        background=COLORS["bg_dark"],
        foreground=COLORS["text_primary"],
        font=FONTS["body"],
    )
    style.configure("Title.TLabel",
        background=COLORS["bg_dark"],
        foreground=COLORS["accent_blue"],
        font=FONTS["title"],
    )
    style.configure("Heading.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_blue"],
        font=FONTS["heading"],
    )
    style.configure("Metric.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_green"],
        font=FONTS["metric"],
    )
    style.configure("MetricSm.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_green"],
        font=FONTS["metric_sm"],
    )
    style.configure("Muted.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["text_secondary"],
        font=FONTS["small"],
    )
    style.configure("Warning.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_yellow"],
        font=FONTS["body"],
    )
    style.configure("Danger.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_red"],
        font=FONTS["body"],
    )
    style.configure("Success.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_green"],
        font=FONTS["body"],
    )
    style.configure("Info.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["info"],
        font=FONTS["body"],
    )

    # Buttons
    style.configure("TButton",
        background=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
        bordercolor=COLORS["border_bright"],
        focuscolor=COLORS["accent_blue"],
        padding=(12, 6),
        font=FONTS["body"],
        relief="flat",
    )
    style.map("TButton",
        background=[("active", COLORS["bg_hover"]),
                    ("pressed", COLORS["accent_blue"])],
        foreground=[("active", COLORS["accent_blue"]),
                    ("pressed", COLORS["bg_dark"])],
    )
    style.configure("Accent.TButton",
        background=COLORS["accent_blue"],
        foreground=COLORS["bg_dark"],
        font=FONTS["subheading"],
        padding=(14, 8),
    )
    style.map("Accent.TButton",
        background=[("active", "#00AACC"), ("pressed", "#0088AA")],
    )
    style.configure("Danger.TButton",
        background=COLORS["accent_red"],
        foreground=COLORS["text_primary"],
        font=FONTS["body"],
        padding=(10, 5),
    )
    style.map("Danger.TButton",
        background=[("active", "#CC2244"), ("pressed", "#AA1133")],
    )
    style.configure("Success.TButton",
        background=COLORS["accent_green"],
        foreground=COLORS["bg_dark"],
        font=FONTS["body"],
        padding=(10, 5),
    )

    # Entry
    style.configure("TEntry",
        fieldbackground=COLORS["bg_panel"],
        foreground=COLORS["text_primary"],
        insertcolor=COLORS["accent_blue"],
        bordercolor=COLORS["border_bright"],
        padding=(8, 6),
        font=FONTS["mono"],
    )

    # Notebook
    style.configure("TNotebook",
        background=COLORS["bg_dark"],
        tabmargins=[2, 5, 2, 0],
        bordercolor=COLORS["border"],
    )
    style.configure("TNotebook.Tab",
        background=COLORS["bg_panel"],
        foreground=COLORS["text_secondary"],
        padding=(14, 8),
        font=FONTS["body"],
    )
    style.map("TNotebook.Tab",
        background=[("selected", COLORS["bg_card"]),
                    ("active", COLORS["bg_hover"])],
        foreground=[("selected", COLORS["accent_blue"]),
                    ("active", COLORS["text_primary"])],
    )

    # Treeview
    style.configure("Treeview",
        background=COLORS["bg_panel"],
        foreground=COLORS["text_primary"],
        fieldbackground=COLORS["bg_panel"],
        rowheight=26,
        font=FONTS["mono_small"],
        bordercolor=COLORS["border"],
    )
    style.configure("Treeview.Heading",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_blue"],
        font=FONTS["subheading"],
        relief="flat",
    )
    style.map("Treeview",
        background=[("selected", COLORS["accent_blue"])],
        foreground=[("selected", COLORS["bg_dark"])],
    )

    # Scrollbar
    style.configure("TScrollbar",
        background=COLORS["bg_panel"],
        troughcolor=COLORS["bg_dark"],
        bordercolor=COLORS["border"],
        arrowcolor=COLORS["text_secondary"],
        width=10,
    )

    # Progressbar
    style.configure("green.Horizontal.TProgressbar",
        troughcolor=COLORS["bg_panel"],
        background=COLORS["accent_green"],
        bordercolor=COLORS["border"],
        thickness=8,
    )
    style.configure("yellow.Horizontal.TProgressbar",
        troughcolor=COLORS["bg_panel"],
        background=COLORS["accent_yellow"],
        thickness=8,
    )
    style.configure("red.Horizontal.TProgressbar",
        troughcolor=COLORS["bg_panel"],
        background=COLORS["accent_red"],
        thickness=8,
    )
    style.configure("blue.Horizontal.TProgressbar",
        troughcolor=COLORS["bg_panel"],
        background=COLORS["accent_blue"],
        thickness=8,
    )

    # Combobox
    style.configure("TCombobox",
        fieldbackground=COLORS["bg_panel"],
        background=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
        arrowcolor=COLORS["accent_blue"],
        bordercolor=COLORS["border_bright"],
    )

    # Scale
    style.configure("TScale",
        background=COLORS["bg_dark"],
        troughcolor=COLORS["bg_panel"],
        sliderthickness=16,
    )

    return style


def get_bar_style(value: float) -> str:
    """Return progressbar style based on percentage."""
    if value >= 90:
        return "red.Horizontal.TProgressbar"
    elif value >= 70:
        return "yellow.Horizontal.TProgressbar"
    return "green.Horizontal.TProgressbar"


def get_value_color(value: float) -> str:
    """Return color string based on percentage."""
    if value >= 90:
        return COLORS["danger"]
    elif value >= 70:
        return COLORS["warning"]
    return COLORS["success"]


def format_bytes(num_bytes: int, suffix="B") -> str:
    for unit in ["", "K", "M", "G", "T", "P"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}{suffix}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} E{suffix}"


def format_uptime(seconds: float) -> str:
    td = datetime.timedelta(seconds=int(seconds))
    days = td.days
    hours, rem = divmod(td.seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    return f"{hours:02d}h {minutes:02d}m {secs:02d}s"


def timestamp_now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_in_thread(func, *args, daemon=True, **kwargs):
    """Launch a function in a background daemon thread."""
    t = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=daemon)
    t.start()
    return t


class RingBuffer:
    """Fixed-size circular buffer for time-series data."""
    def __init__(self, maxlen: int = 60):
        self._buf = []
        self._maxlen = maxlen

    def append(self, val):
        self._buf.append(val)
        if len(self._buf) > self._maxlen:
            self._buf.pop(0)

    def get(self):
        return list(self._buf)

    def __len__(self):
        return len(self._buf)


def make_card(parent, title: str = "", padx=10, pady=10) -> tuple:
    """
    Create a styled card frame.
    Returns (outer_frame, inner_frame).
    """
    outer = tk.Frame(parent, bg=COLORS["bg_card"],
                     highlightbackground=COLORS["border"],
                     highlightthickness=1)
    if title:
        header = tk.Frame(outer, bg=COLORS["bg_card"])
        header.pack(fill="x", padx=padx, pady=(pady, 4))
        tk.Label(header, text=title,
                 bg=COLORS["bg_card"],
                 fg=COLORS["accent_blue"],
                 font=FONTS["subheading"]).pack(side="left")
        tk.Frame(outer, bg=COLORS["border"], height=1).pack(fill="x",
                                                             padx=padx // 2)

    inner = tk.Frame(outer, bg=COLORS["bg_card"])
    inner.pack(fill="both", expand=True, padx=padx, pady=pady)
    return outer, inner


def sep(parent, color=None, vertical=False):
    """Create a separator line."""
    c = color or COLORS["border"]
    if vertical:
        return tk.Frame(parent, bg=c, width=1)
    return tk.Frame(parent, bg=c, height=1)


class StatusDot(tk.Canvas):
    """Animated blinking status indicator dot."""
    def __init__(self, parent, color=None, size=10, **kwargs):
        super().__init__(parent,
                         width=size, height=size,
                         bg=COLORS["bg_card"],
                         highlightthickness=0,
                         **kwargs)
        self._color = color or COLORS["accent_green"]
        self._size = size
        self._state = True
        self._dot = self.create_oval(2, 2, size - 2, size - 2,
                                     fill=self._color, outline="")
        self._blink()

    def set_color(self, color: str):
        self._color = color
        self.itemconfig(self._dot, fill=color)

    def _blink(self):
        c = self._color if self._state else self["bg"]
        self.itemconfig(self._dot, fill=c)
        self._state = not self._state
        self.after(800, self._blink)