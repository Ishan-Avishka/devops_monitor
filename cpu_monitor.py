"""
cpu_monitor.py - CPU usage monitoring panel with live charts.
"""
import tkinter as tk
from tkinter import ttk
import psutil
import threading
import time
from utils import (COLORS, FONTS, make_card, sep, RingBuffer,
                   get_bar_style, get_value_color, format_uptime)
from charts import LiveLineChart, GaugeChart
from alerts import alert_engine
import database as db


class CPUMonitor(ttk.Frame):
    HISTORY = 60      # data points kept
    INTERVAL = 2      # seconds between refreshes

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")

        # Buffers
        self._cpu_buf   = RingBuffer(self.HISTORY)
        self._freq_buf  = RingBuffer(self.HISTORY)
        self._core_bufs: list[RingBuffer] = []
        self._running = True

        self._build_ui()
        self._poller = threading.Thread(target=self._poll_loop,
                                        daemon=True)
        self._poller.start()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="⚡  CPU MONITOR",
                 bg=COLORS["bg_dark"], fg=COLORS["accent_blue"],
                 font=FONTS["heading"]).pack(side="left")
        self._ts_label = tk.Label(hdr, text="",
                                  bg=COLORS["bg_dark"],
                                  fg=COLORS["text_muted"],
                                  font=FONTS["small"])
        self._ts_label.pack(side="right")

        # Top row: gauge + summary cards
        top = tk.Frame(self, bg=COLORS["bg_dark"])
        top.pack(fill="x", pady=(0, 8))

        # Gauge
        gauge_card, gauge_inner = make_card(top, "Overall CPU")
        gauge_card.pack(side="left", fill="y", padx=(0, 6))
        self._gauge = GaugeChart(gauge_inner, title="CPU %",
                                 width_in=2.2, height_in=1.8)
        self._gauge.pack()

        # Summary
        summary_card, summary_inner = make_card(top, "System Info")
        summary_card.pack(side="left", fill="both", expand=True)
        grid = tk.Frame(summary_inner, bg=COLORS["bg_card"])
        grid.pack(fill="both", expand=True)

        self._info_vars = {}
        fields = [
            ("CPU Usage",    "_cpu_pct"),
            ("Cores (log.)", "_cpu_count"),
            ("Cores (phys.)", "_cpu_phys"),
            ("Frequency",    "_cpu_freq"),
            ("Model",        "_cpu_model"),
            ("Uptime",       "_cpu_uptime"),
            ("User %",       "_cpu_user"),
            ("System %",     "_cpu_sys"),
            ("Idle %",       "_cpu_idle"),
        ]
        for row_idx, (label, key) in enumerate(fields):
            tk.Label(grid, text=label + ":",
                     bg=COLORS["bg_card"],
                     fg=COLORS["text_secondary"],
                     font=FONTS["small"],
                     width=14, anchor="e").grid(
                row=row_idx // 3, column=(row_idx % 3) * 2,
                padx=(8, 2), pady=2, sticky="e")
            var = tk.StringVar(value="—")
            self._info_vars[key] = var
            tk.Label(grid, textvariable=var,
                     bg=COLORS["bg_card"],
                     fg=COLORS["accent_green"],
                     font=FONTS["mono_small"],
                     anchor="w").grid(
                row=row_idx // 3, column=(row_idx % 3) * 2 + 1,
                padx=(2, 12), pady=2, sticky="w")

        # Live line chart
        chart_card, chart_inner = make_card(self, "CPU Usage — 60s History")
        chart_card.pack(fill="x", pady=(0, 8))
        self._line_chart = LiveLineChart(
            chart_inner,
            series=[("Total CPU %", COLORS["accent_blue"], self._cpu_buf)],
            y_label="%", y_max=100,
            height_in=2.2, width_in=9.0,
            interval_ms=self.INTERVAL * 1000,
        )
        self._line_chart.pack(fill="x")

        # Per-core section
        core_card, self._core_frame = make_card(self, "Per-Core Usage")
        core_card.pack(fill="x", pady=(0, 8))
        self._core_bars: list[tuple] = []  # (bar_widget, label_widget, var)

        # Progress bar row
        prog_card, self._prog_frame = make_card(self, "Core Usage Bars")
        prog_card.pack(fill="x")

    def _build_core_bars(self, n_cores: int):
        """Create per-core progress bars (called once)."""
        for widget in self._prog_frame.winfo_children():
            widget.destroy()
        for widget in self._core_frame.winfo_children():
            widget.destroy()
        self._core_bars = []
        cols = 4
        for i in range(n_cores):
            row, col = divmod(i, cols)
            cell = tk.Frame(self._prog_frame, bg=COLORS["bg_card"])
            cell.grid(row=row, column=col, padx=6, pady=4, sticky="ew")
            tk.Label(cell, text=f"Core {i}",
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=FONTS["label"]).pack(anchor="w")
            var = tk.DoubleVar(value=0)
            bar = ttk.Progressbar(cell, variable=var,
                                  maximum=100, length=140,
                                  style="green.Horizontal.TProgressbar")
            bar.pack(fill="x")
            pct_var = tk.StringVar(value="0%")
            tk.Label(cell, textvariable=pct_var,
                     bg=COLORS["bg_card"], fg=COLORS["accent_green"],
                     font=FONTS["label"]).pack(anchor="e")
            self._core_bars.append((bar, var, pct_var))
            self._prog_frame.columnconfigure(col, weight=1)

            # Line chart per core
            if not self._core_bufs or len(self._core_bufs) <= i:
                self._core_bufs.append(RingBuffer(self.HISTORY))

    # ── Polling ───────────────────────────────────────────────────────────────
    def _poll_loop(self):
        # One-time static info
        cpu_info = self._static_info()
        first = True
        while self._running:
            try:
                self._collect(cpu_info, first)
                first = False
            except Exception as e:
                db.write_log("ERROR", "CPUMonitor", str(e))
            time.sleep(self.INTERVAL)

    def _static_info(self) -> dict:
        info = {
            "count_log":  psutil.cpu_count(logical=True),
            "count_phys": psutil.cpu_count(logical=False),
            "model":      "Unknown",
        }
        try:
            import platform
            info["model"] = platform.processor()[:40] or "N/A"
        except Exception:
            pass
        return info

    def _collect(self, static: dict, first: bool):
        pct      = psutil.cpu_percent(interval=1)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        times    = psutil.cpu_times_percent(interval=None)
        freq_obj = psutil.cpu_freq()
        freq     = freq_obj.current if freq_obj else 0
        uptime   = time.time() - psutil.boot_time()

        self._cpu_buf.append(pct)
        self._freq_buf.append(freq)
        for i, c in enumerate(per_core):
            while len(self._core_bufs) <= i:
                self._core_bufs.append(RingBuffer(self.HISTORY))
            self._core_bufs[i].append(c)

        # Fire alerts
        alert_engine.check("localhost", "cpu_percent", pct)

        # Update UI on main thread
        self.after(0, lambda: self._update_ui(
            pct, per_core, times, freq, uptime, static, first
        ))

    def _update_ui(self, pct, per_core, times, freq, uptime, static, first):
        import datetime
        self._ts_label.config(
            text=datetime.datetime.now().strftime("%H:%M:%S"))

        self._gauge.set_value(pct)

        v = self._info_vars
        v["_cpu_pct"].set(f"{pct:.1f}%")
        v["_cpu_count"].set(str(static["count_log"]))
        v["_cpu_phys"].set(str(static["count_phys"]))
        v["_cpu_freq"].set(f"{freq:.0f} MHz")
        v["_cpu_model"].set(static["model"])
        v["_cpu_uptime"].set(format_uptime(uptime))
        v["_cpu_user"].set(f"{times.user:.1f}%")
        v["_cpu_sys"].set(f"{times.system:.1f}%")
        v["_cpu_idle"].set(f"{times.idle:.1f}%")

        if first or len(self._core_bars) != len(per_core):
            self._build_core_bars(len(per_core))

        for i, (bar, var, pct_var) in enumerate(self._core_bars):
            c = per_core[i] if i < len(per_core) else 0
            var.set(c)
            pct_var.set(f"{c:.0f}%")
            style = get_bar_style(c)
            bar.configure(style=style)

    def destroy(self):
        self._running = False
        super().destroy()