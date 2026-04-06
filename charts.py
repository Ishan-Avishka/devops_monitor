"""
charts.py - Reusable Matplotlib chart widgets embedded in Tkinter frames.
"""
import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
from utils import COLORS, FONTS, RingBuffer

# ── Matplotlib global style ───────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor":   COLORS["chart_bg"],
    "axes.facecolor":     COLORS["chart_bg"],
    "axes.edgecolor":     COLORS["border"],
    "axes.labelcolor":    COLORS["text_secondary"],
    "axes.grid":          True,
    "grid.color":         COLORS["grid_line"],
    "grid.linewidth":     0.5,
    "text.color":         COLORS["text_primary"],
    "xtick.color":        COLORS["text_muted"],
    "ytick.color":        COLORS["text_muted"],
    "xtick.labelsize":    7,
    "ytick.labelsize":    7,
    "lines.linewidth":    1.8,
    "lines.antialiased":  True,
    "figure.autolayout":  True,
})


# ─── LINE CHART ───────────────────────────────────────────────────────────────
class LiveLineChart(tk.Frame):
    """
    Animated line chart that updates from a RingBuffer.
    Supports multiple series.
    """
    def __init__(self, parent,
                 title: str = "",
                 series: list[tuple[str, str, RingBuffer]] = None,
                 y_label: str = "%",
                 y_max: float = 100.0,
                 height_in: float = 2.4,
                 width_in: float = 5.5,
                 interval_ms: int = 2000,
                 **kwargs):
        super().__init__(parent, bg=COLORS["chart_bg"], **kwargs)
        self._series = series or []
        self._y_max = y_max
        self._interval = interval_ms

        self._fig = Figure(figsize=(width_in, height_in), dpi=90)
        self._ax  = self._fig.add_subplot(111)
        if title:
            self._ax.set_title(title, color=COLORS["accent_blue"],
                               fontsize=9, pad=4)
        self._ax.set_ylabel(y_label, fontsize=7)
        self._ax.set_ylim(0, y_max)
        self._ax.spines["top"].set_visible(False)
        self._ax.spines["right"].set_visible(False)

        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._lines = {}
        self._ani = animation.FuncAnimation(
            self._fig, self._update,
            interval=interval_ms, blit=False, cache_frame_data=False
        )

    def _update(self, frame):
        self._ax.cla()
        self._ax.set_ylim(0, self._y_max)
        self._ax.grid(True, color=COLORS["grid_line"], linewidth=0.5)
        self._ax.spines["top"].set_visible(False)
        self._ax.spines["right"].set_visible(False)
        self._ax.set_facecolor(COLORS["chart_bg"])
        legend_patches = []
        for label, color, buf in self._series:
            data = buf.get()
            if data:
                xs = list(range(len(data)))
                self._ax.plot(xs, data, color=color, linewidth=1.8,
                              label=label)
                self._ax.fill_between(xs, data,
                                      color=color, alpha=0.12)
                legend_patches.append(
                    mpatches.Patch(color=color, label=label))
        if len(self._series) > 1 and legend_patches:
            self._ax.legend(handles=legend_patches, loc="upper left",
                            fontsize=7,
                            facecolor=COLORS["bg_card"],
                            edgecolor=COLORS["border"],
                            labelcolor=COLORS["text_primary"])
        self._canvas.draw_idle()

    def add_series(self, label: str, color: str, buf: RingBuffer):
        self._series.append((label, color, buf))

    def destroy(self):
        try:
            self._ani.event_source.stop()
        except Exception:
            pass
        super().destroy()


# ─── GAUGE ────────────────────────────────────────────────────────────────────
class GaugeChart(tk.Frame):
    """Semi-circular gauge for a single metric 0-100."""
    def __init__(self, parent, title: str = "",
                 width_in=2.0, height_in=1.5, **kwargs):
        super().__init__(parent, bg=COLORS["chart_bg"], **kwargs)
        self._title = title
        self._value = 0.0
        self._fig = Figure(figsize=(width_in, height_in), dpi=90)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._draw(0)

    def _draw(self, value: float):
        self._ax.cla()
        self._ax.set_aspect("equal")
        self._ax.axis("off")
        self._fig.patch.set_facecolor(COLORS["chart_bg"])

        # Background arc
        theta1, theta2 = 180, 0
        import numpy as np
        theta = [i * 3.14159 / 180 for i in range(181)]
        x_bg = [0.5 + 0.45 * __import__("math").cos(t) for t in theta]
        y_bg = [0.3 + 0.45 * __import__("math").sin(t) for t in theta]
        self._ax.plot(x_bg, y_bg, color=COLORS["border"], linewidth=6,
                      solid_capstyle="round")

        # Value arc
        frac = value / 100.0
        end_deg = int(180 * frac)
        if end_deg > 0:
            import math
            theta_v = [i * 3.14159 / 180 for i in range(end_deg + 1)]
            clr = (COLORS["accent_green"] if value < 70
                   else COLORS["accent_yellow"] if value < 90
                   else COLORS["accent_red"])
            x_v = [0.5 + 0.45 * math.cos(t) for t in theta_v]
            y_v = [0.3 + 0.45 * math.sin(t) for t in theta_v]
            self._ax.plot(x_v, y_v, color=clr, linewidth=6,
                         solid_capstyle="round")

        clr2 = (COLORS["accent_green"] if value < 70
                else COLORS["accent_yellow"] if value < 90
                else COLORS["accent_red"])
        self._ax.text(0.5, 0.2, f"{value:.0f}%",
                      ha="center", va="center", fontsize=11, fontweight="bold",
                      color=clr2, transform=self._ax.transAxes)
        self._ax.text(0.5, 0.05, self._title,
                      ha="center", va="center", fontsize=7,
                      color=COLORS["text_secondary"],
                      transform=self._ax.transAxes)
        self._canvas.draw_idle()

    def set_value(self, value: float):
        self._value = value
        self._draw(value)


# ─── BAR CHART ────────────────────────────────────────────────────────────────
class StaticBarChart(tk.Frame):
    """Simple horizontal bar chart for disk partitions, etc."""
    def __init__(self, parent, title: str = "",
                 width_in=4.0, height_in=2.2, **kwargs):
        super().__init__(parent, bg=COLORS["chart_bg"], **kwargs)
        self._title = title
        self._fig = Figure(figsize=(width_in, height_in), dpi=90)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

    def update(self, labels: list[str], values: list[float],
               colors: list[str] = None):
        self._ax.cla()
        self._ax.set_facecolor(COLORS["chart_bg"])
        self._ax.spines["top"].set_visible(False)
        self._ax.spines["right"].set_visible(False)
        if not labels:
            return
        clrs = colors or [COLORS["accent_blue"]] * len(labels)
        bars = self._ax.barh(labels, values, color=clrs, height=0.5)
        self._ax.set_xlim(0, 100)
        self._ax.set_xlabel("Usage %", fontsize=7, color=COLORS["text_secondary"])
        if self._title:
            self._ax.set_title(self._title, color=COLORS["accent_blue"],
                               fontsize=9, pad=4)
        for bar, v in zip(bars, values):
            self._ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                         f"{v:.1f}%", va="center", fontsize=7,
                         color=COLORS["text_primary"])
        self._canvas.draw_idle()


# ─── NETWORK AREA CHART ───────────────────────────────────────────────────────
class NetworkChart(tk.Frame):
    """Dual-axis chart showing upload / download bytes per second."""
    def __init__(self, parent,
                 sent_buf: RingBuffer, recv_buf: RingBuffer,
                 interval_ms: int = 2000,
                 width_in=5.5, height_in=2.4, **kwargs):
        super().__init__(parent, bg=COLORS["chart_bg"], **kwargs)
        self._sent = sent_buf
        self._recv = recv_buf
        self._fig = Figure(figsize=(width_in, height_in), dpi=90)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._ani = animation.FuncAnimation(
            self._fig, self._update,
            interval=interval_ms, blit=False, cache_frame_data=False
        )

    def _update(self, _frame):
        self._ax.cla()
        self._ax.set_facecolor(COLORS["chart_bg"])
        self._ax.spines["top"].set_visible(False)
        self._ax.spines["right"].set_visible(False)
        self._ax.grid(True, color=COLORS["grid_line"], linewidth=0.5)

        recv = self._recv.get()
        sent = self._sent.get()
        xs = list(range(max(len(recv), len(sent))))

        if recv:
            self._ax.fill_between(range(len(recv)), recv,
                                  color=COLORS["accent_green"], alpha=0.4)
            self._ax.plot(recv, color=COLORS["accent_green"],
                         linewidth=1.8, label="↓ Recv")
        if sent:
            self._ax.fill_between(range(len(sent)), sent,
                                  color=COLORS["accent_orange"], alpha=0.4)
            self._ax.plot(sent, color=COLORS["accent_orange"],
                         linewidth=1.8, label="↑ Sent")
        self._ax.legend(loc="upper left", fontsize=7,
                       facecolor=COLORS["bg_card"],
                       edgecolor=COLORS["border"],
                       labelcolor=COLORS["text_primary"])
        self._ax.set_title("Network I/O (bytes/s)",
                           color=COLORS["accent_blue"], fontsize=9, pad=4)
        self._canvas.draw_idle()

    def destroy(self):
        try:
            self._ani.event_source.stop()
        except Exception:
            pass
        super().destroy()