"""
memory_monitor.py - RAM & Swap monitoring with live charts.
"""
import tkinter as tk
from tkinter import ttk
import psutil
import threading
import time
import datetime
from utils import (COLORS, FONTS, make_card, sep, RingBuffer,
                   get_bar_style, get_value_color, format_bytes)
from charts import LiveLineChart, GaugeChart
from alerts import alert_engine
import database as db


class MemoryMonitor(ttk.Frame):
    HISTORY  = 60
    INTERVAL = 3

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")

        self._ram_buf  = RingBuffer(self.HISTORY)
        self._swap_buf = RingBuffer(self.HISTORY)
        self._running  = True

        self._build_ui()
        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="🧠  MEMORY MONITOR",
                 bg=COLORS["bg_dark"], fg=COLORS["accent_purple"],
                 font=FONTS["heading"]).pack(side="left")
        self._ts = tk.Label(hdr, text="",
                            bg=COLORS["bg_dark"], fg=COLORS["text_muted"],
                            font=FONTS["small"])
        self._ts.pack(side="right")

        # Gauges row
        top = tk.Frame(self, bg=COLORS["bg_dark"])
        top.pack(fill="x", pady=(0, 8))

        for attr, title, color in [
            ("_ram_gauge",  "RAM",  COLORS["accent_purple"]),
            ("_swap_gauge", "SWAP", COLORS["accent_orange"]),
        ]:
            card, inner = make_card(top, title)
            card.pack(side="left", fill="y", padx=(0, 6))
            gauge = GaugeChart(inner, title=f"{title} %",
                               width_in=2.2, height_in=1.8)
            gauge.pack()
            setattr(self, attr, gauge)

        # Detail cards
        details = tk.Frame(self, bg=COLORS["bg_dark"])
        details.pack(fill="x", pady=(0, 8))

        ram_card, ram_inner = make_card(details, "RAM Details")
        ram_card.pack(side="left", fill="both", expand=True, padx=(0, 4))
        swap_card, swap_inner = make_card(details, "SWAP Details")
        swap_card.pack(side="left", fill="both", expand=True)

        self._ram_vars  = self._build_detail_grid(ram_inner,
            ["Total", "Used", "Free", "Available", "Cached", "Buffers"])
        self._swap_vars = self._build_detail_grid(swap_inner,
            ["Total", "Used", "Free", "Usage %", "", ""])

        # Line chart
        chart_card, chart_inner = make_card(self, "Memory Usage — 60s History")
        chart_card.pack(fill="x", pady=(0, 8))
        self._chart = LiveLineChart(
            chart_inner,
            series=[
                ("RAM %",  COLORS["accent_purple"], self._ram_buf),
                ("SWAP %", COLORS["accent_orange"],  self._swap_buf),
            ],
            y_label="%", y_max=100,
            height_in=2.2, width_in=9.0,
            interval_ms=self.INTERVAL * 1000,
        )
        self._chart.pack(fill="x")

        # Top processes
        proc_card, proc_inner = make_card(self, "Top Memory Processes")
        proc_card.pack(fill="both", expand=True)
        self._proc_tree = self._build_proc_tree(proc_inner)

    def _build_detail_grid(self, parent, fields: list[str]) -> dict:
        vars_ = {}
        for i, f in enumerate(fields):
            if not f:
                continue
            row, col = divmod(i, 2)
            tk.Label(parent, text=f"{f}:",
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=FONTS["small"], width=12, anchor="e").grid(
                row=row, column=col * 2, padx=(4, 2), pady=2, sticky="e")
            var = tk.StringVar(value="—")
            vars_[f] = var
            tk.Label(parent, textvariable=var,
                     bg=COLORS["bg_card"], fg=COLORS["accent_green"],
                     font=FONTS["mono_small"], anchor="w").grid(
                row=row, column=col * 2 + 1, padx=(2, 8), pady=2, sticky="w")
        return vars_

    def _build_proc_tree(self, parent) -> ttk.Treeview:
        cols = ("pid", "name", "rss", "vms", "pct")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=6)
        hdrs = {"pid": ("PID", 60), "name": ("Process", 200),
                "rss": ("RSS", 100), "vms": ("VMS", 100), "pct": ("MEM %", 80)}
        for c, (h, w) in hdrs.items():
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w")
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
                db.write_log("ERROR", "MemoryMonitor", str(e))
            time.sleep(self.INTERVAL)

    def _collect(self):
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        self._ram_buf.append(mem.percent)
        self._swap_buf.append(swap.percent)

        alert_engine.check("localhost", "mem_percent", mem.percent)

        # Top procs by RSS
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info",
                                      "memory_percent"]):
            try:
                mi = p.info["memory_info"]
                procs.append((
                    p.info["pid"],
                    p.info["name"] or "?",
                    mi.rss if mi else 0,
                    mi.vms if mi else 0,
                    p.info["memory_percent"] or 0.0,
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: x[2], reverse=True)

        self.after(0, lambda: self._update_ui(mem, swap, procs[:20]))

    def _update_ui(self, mem, swap, procs):
        self._ts.config(text=datetime.datetime.now().strftime("%H:%M:%S"))

        self._ram_gauge.set_value(mem.percent)
        self._swap_gauge.set_value(swap.percent)

        rv = self._ram_vars
        rv["Total"].set(format_bytes(mem.total))
        rv["Used"].set(format_bytes(mem.used))
        rv["Free"].set(format_bytes(mem.free))
        rv["Available"].set(format_bytes(mem.available))
        rv["Cached"].set(format_bytes(getattr(mem, "cached", 0)))
        rv["Buffers"].set(format_bytes(getattr(mem, "buffers", 0)))

        sv = self._swap_vars
        sv["Total"].set(format_bytes(swap.total))
        sv["Used"].set(format_bytes(swap.used))
        sv["Free"].set(format_bytes(swap.free))
        sv["Usage %"].set(f"{swap.percent:.1f}%")

        # Process table
        for item in self._proc_tree.get_children():
            self._proc_tree.delete(item)
        for pid, name, rss, vms, pct in procs:
            self._proc_tree.insert("", "end",
                values=(pid, name, format_bytes(rss),
                        format_bytes(vms), f"{pct:.1f}%"))

    def destroy(self):
        self._running = False
        super().destroy()