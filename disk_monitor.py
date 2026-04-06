"""
disk_monitor.py - Disk usage & I/O monitoring.
"""
import tkinter as tk
from tkinter import ttk
import psutil
import threading
import time
import datetime
from utils import (COLORS, FONTS, make_card, sep, RingBuffer,
                   get_bar_style, get_value_color, format_bytes)
from charts import LiveLineChart, StaticBarChart
from alerts import alert_engine
import database as db


class DiskMonitor(ttk.Frame):
    HISTORY  = 60
    INTERVAL = 4

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        self._read_buf  = RingBuffer(self.HISTORY)
        self._write_buf = RingBuffer(self.HISTORY)
        self._prev_io   = None
        self._running   = True
        self._build_ui()
        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="💾  DISK MONITOR",
                 bg=COLORS["bg_dark"], fg=COLORS["accent_yellow"],
                 font=FONTS["heading"]).pack(side="left")
        self._ts = tk.Label(hdr, text="",
                            bg=COLORS["bg_dark"], fg=COLORS["text_muted"],
                            font=FONTS["small"])
        self._ts.pack(side="right")

        # Partition table
        part_card, part_inner = make_card(self, "Disk Partitions")
        part_card.pack(fill="x", pady=(0, 8))
        self._part_tree = self._build_part_tree(part_inner)

        # Bar chart + IO chart
        mid = tk.Frame(self, bg=COLORS["bg_dark"])
        mid.pack(fill="x", pady=(0, 8))

        bar_card, bar_inner = make_card(mid, "Partition Usage")
        bar_card.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self._bar_chart = StaticBarChart(bar_inner, width_in=4.0, height_in=2.8)
        self._bar_chart.pack(fill="both", expand=True)

        io_card, io_inner = make_card(mid, "Disk I/O (bytes/s)")
        io_card.pack(side="left", fill="both", expand=True)
        self._io_chart = LiveLineChart(
            io_inner,
            series=[
                ("Read  B/s",  COLORS["accent_green"], self._read_buf),
                ("Write B/s",  COLORS["accent_red"],   self._write_buf),
            ],
            y_label="B/s", y_max=50_000_000,
            height_in=2.8, width_in=4.5,
            interval_ms=self.INTERVAL * 1000,
        )
        self._io_chart.pack(fill="both", expand=True)

        # IO summary cards
        io_summary = tk.Frame(self, bg=COLORS["bg_dark"])
        io_summary.pack(fill="x", pady=(0, 8))
        self._io_vars = {}
        for label, key in [
            ("Read Speed",  "read_speed"),
            ("Write Speed", "write_speed"),
            ("Total Read",  "total_read"),
            ("Total Write", "total_write"),
        ]:
            card, inner = make_card(io_summary)
            card.pack(side="left", fill="x", expand=True, padx=3)
            var = tk.StringVar(value="—")
            self._io_vars[key] = var
            tk.Label(inner, textvariable=var,
                     bg=COLORS["bg_card"], fg=COLORS["accent_yellow"],
                     font=FONTS["metric_sm"]).pack()
            tk.Label(inner, text=label,
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=FONTS["small"]).pack()

    def _build_part_tree(self, parent) -> ttk.Treeview:
        cols = ("device", "mount", "fstype", "total",
                "used", "free", "pct")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=5)
        hdrs = {
            "device":  ("Device",    130),
            "mount":   ("Mount",     120),
            "fstype":  ("FS Type",    80),
            "total":   ("Total",      90),
            "used":    ("Used",       90),
            "free":    ("Free",       90),
            "pct":     ("Usage %",    80),
        }
        for c, (h, w) in hdrs.items():
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w")
        tree.tag_configure("warn",     foreground=COLORS["accent_yellow"])
        tree.tag_configure("critical", foreground=COLORS["accent_red"])
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return tree

    # ── Poll ──────────────────────────────────────────────────────────────────
    def _poll_loop(self):
        while self._running:
            try:
                self._collect()
            except Exception as e:
                db.write_log("ERROR", "DiskMonitor", str(e))
            time.sleep(self.INTERVAL)

    def _collect(self):
        partitions = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "device": part.device,
                    "mount":  part.mountpoint,
                    "fstype": part.fstype,
                    "total":  usage.total,
                    "used":   usage.used,
                    "free":   usage.free,
                    "pct":    usage.percent,
                })
                alert_engine.check("localhost", "disk_percent", usage.percent)
            except (PermissionError, FileNotFoundError):
                pass

        # I/O counters delta
        io = psutil.disk_io_counters()
        read_speed = write_speed = 0
        if io and self._prev_io:
            dt = self.INTERVAL
            read_speed  = (io.read_bytes  - self._prev_io.read_bytes)  / dt
            write_speed = (io.write_bytes - self._prev_io.write_bytes) / dt
        self._prev_io = io
        self._read_buf.append(max(0, read_speed))
        self._write_buf.append(max(0, write_speed))

        self.after(0, lambda: self._update_ui(
            partitions, io, read_speed, write_speed
        ))

    def _update_ui(self, partitions, io, read_speed, write_speed):
        self._ts.config(text=datetime.datetime.now().strftime("%H:%M:%S"))

        # Partition tree
        for item in self._part_tree.get_children():
            self._part_tree.delete(item)
        labels, values, colors = [], [], []
        for p in partitions:
            tag = ("critical" if p["pct"] >= 90
                   else "warn" if p["pct"] >= 75 else "")
            self._part_tree.insert("", "end", tags=(tag,),
                values=(p["device"], p["mount"], p["fstype"],
                        format_bytes(p["total"]),
                        format_bytes(p["used"]),
                        format_bytes(p["free"]),
                        f"{p['pct']:.1f}%"))
            labels.append(p["mount"])
            values.append(p["pct"])
            colors.append(
                COLORS["accent_red"]    if p["pct"] >= 90 else
                COLORS["accent_yellow"] if p["pct"] >= 75 else
                COLORS["accent_green"]
            )

        self._bar_chart.update(labels, values, colors)

        # IO vars
        v = self._io_vars
        v["read_speed"].set(format_bytes(int(read_speed)) + "/s")
        v["write_speed"].set(format_bytes(int(write_speed)) + "/s")
        if io:
            v["total_read"].set(format_bytes(io.read_bytes))
            v["total_write"].set(format_bytes(io.write_bytes))

    def destroy(self):
        self._running = False
        super().destroy()