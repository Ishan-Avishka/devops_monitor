"""
network_monitor.py - Network interface monitoring with speed/packet tracking.
"""
import tkinter as tk
from tkinter import ttk
import psutil
import threading
import time
import datetime
from utils import (COLORS, FONTS, make_card, sep, RingBuffer, format_bytes)
from charts import NetworkChart
import database as db


class NetworkMonitor(ttk.Frame):
    HISTORY  = 60
    INTERVAL = 2

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        self._sent_buf  = RingBuffer(self.HISTORY)
        self._recv_buf  = RingBuffer(self.HISTORY)
        self._prev_io   = {}
        self._running   = True
        self._build_ui()
        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="🌐  NETWORK MONITOR",
                 bg=COLORS["bg_dark"], fg=COLORS["accent_green"],
                 font=FONTS["heading"]).pack(side="left")
        self._ts = tk.Label(hdr, text="",
                            bg=COLORS["bg_dark"], fg=COLORS["text_muted"],
                            font=FONTS["small"])
        self._ts.pack(side="right")

        # Speed summary cards
        speed_row = tk.Frame(self, bg=COLORS["bg_dark"])
        speed_row.pack(fill="x", pady=(0, 8))
        self._speed_vars = {}
        for label, key, color in [
            ("↓ Download",   "recv_speed",   COLORS["accent_green"]),
            ("↑ Upload",     "sent_speed",   COLORS["accent_orange"]),
            ("Total Recv",   "total_recv",   COLORS["info"]),
            ("Total Sent",   "total_sent",   COLORS["accent_purple"]),
            ("Packets Recv", "pkts_recv",    COLORS["text_primary"]),
            ("Packets Sent", "pkts_sent",    COLORS["text_primary"]),
            ("Errors In",    "errs_in",      COLORS["accent_red"]),
            ("Errors Out",   "errs_out",     COLORS["accent_red"]),
        ]:
            card, inner = make_card(speed_row)
            card.pack(side="left", fill="x", expand=True, padx=2)
            var = tk.StringVar(value="—")
            self._speed_vars[key] = var
            tk.Label(inner, textvariable=var,
                     bg=COLORS["bg_card"], fg=color,
                     font=FONTS["metric_sm"]).pack()
            tk.Label(inner, text=label,
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=FONTS["label"]).pack()

        # Network chart
        chart_card, chart_inner = make_card(self, "Network I/O — 60s History")
        chart_card.pack(fill="x", pady=(0, 8))
        self._net_chart = NetworkChart(
            chart_inner,
            sent_buf=self._sent_buf,
            recv_buf=self._recv_buf,
            interval_ms=self.INTERVAL * 1000,
            width_in=9.5, height_in=2.4,
        )
        self._net_chart.pack(fill="x")

        # Interface table
        iface_card, iface_inner = make_card(self, "Network Interfaces")
        iface_card.pack(fill="x", pady=(0, 8))
        self._iface_tree = self._build_iface_tree(iface_inner)

        # Active connections
        conn_card, conn_inner = make_card(self, "Active Connections (TCP)")
        conn_card.pack(fill="both", expand=True)
        conn_hdr = tk.Frame(conn_inner, bg=COLORS["bg_card"])
        conn_hdr.pack(fill="x", pady=(0, 4))
        self._conn_count = tk.StringVar(value="0 connections")
        tk.Label(conn_hdr, textvariable=self._conn_count,
                 bg=COLORS["bg_card"], fg=COLORS["accent_blue"],
                 font=FONTS["small"]).pack(side="right")
        self._conn_tree = self._build_conn_tree(conn_inner)

    def _build_iface_tree(self, parent) -> ttk.Treeview:
        cols = ("iface", "ip", "mask", "mac", "speed", "status")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=4)
        hdrs = {
            "iface":  ("Interface", 110),
            "ip":     ("IP Address", 140),
            "mask":   ("Netmask",    130),
            "mac":    ("MAC",        140),
            "speed":  ("Speed",       80),
            "status": ("Status",      80),
        }
        for c, (h, w) in hdrs.items():
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w")
        tree.tag_configure("up",   foreground=COLORS["accent_green"])
        tree.tag_configure("down", foreground=COLORS["accent_red"])
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return tree

    def _build_conn_tree(self, parent) -> ttk.Treeview:
        cols = ("local", "remote", "status", "pid")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=6)
        hdrs = {
            "local":  ("Local Address",  180),
            "remote": ("Remote Address", 180),
            "status": ("Status",         100),
            "pid":    ("PID",             60),
        }
        for c, (h, w) in hdrs.items():
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w")
        tree.tag_configure("ESTABLISHED", foreground=COLORS["accent_green"])
        tree.tag_configure("LISTEN",      foreground=COLORS["info"])
        tree.tag_configure("TIME_WAIT",   foreground=COLORS["accent_yellow"])
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
                db.write_log("ERROR", "NetworkMonitor", str(e))
            time.sleep(self.INTERVAL)

    def _collect(self):
        io = psutil.net_io_counters()
        iface_io = psutil.net_io_counters(pernic=True)
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        sent_speed = recv_speed = 0
        if hasattr(self, "_prev_total"):
            dt = self.INTERVAL
            sent_speed = (io.bytes_sent - self._prev_total.bytes_sent) / dt
            recv_speed = (io.bytes_recv - self._prev_total.bytes_recv) / dt
        self._prev_total = io
        self._sent_buf.append(max(0, sent_speed))
        self._recv_buf.append(max(0, recv_speed))

        # Interfaces
        ifaces = []
        for name, addr_list in addrs.items():
            ip = mask = mac = ""
            for a in addr_list:
                import socket
                if a.family == socket.AF_INET:
                    ip   = a.address
                    mask = a.netmask or ""
                elif a.family == psutil.AF_LINK:
                    mac  = a.address
            stat = stats.get(name)
            spd  = f"{stat.speed} Mbps" if stat and stat.speed else "N/A"
            up   = "UP" if stat and stat.isup else "DOWN"
            ifaces.append((name, ip, mask, mac, spd, up))

        # Connections
        try:
            conns = []
            for c in psutil.net_connections(kind="tcp")[:50]:
                la = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
                ra = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
                conns.append((la, ra, c.status, c.pid or ""))
        except psutil.AccessDenied:
            conns = []

        self.after(0, lambda: self._update_ui(
            io, sent_speed, recv_speed, ifaces, conns
        ))

    def _update_ui(self, io, sent_speed, recv_speed, ifaces, conns):
        self._ts.config(text=datetime.datetime.now().strftime("%H:%M:%S"))

        v = self._speed_vars
        v["recv_speed"].set(format_bytes(int(recv_speed)) + "/s")
        v["sent_speed"].set(format_bytes(int(sent_speed)) + "/s")
        v["total_recv"].set(format_bytes(io.bytes_recv))
        v["total_sent"].set(format_bytes(io.bytes_sent))
        v["pkts_recv"].set(f"{io.packets_recv:,}")
        v["pkts_sent"].set(f"{io.packets_sent:,}")
        v["errs_in"].set(str(io.errin))
        v["errs_out"].set(str(io.errout))

        for item in self._iface_tree.get_children():
            self._iface_tree.delete(item)
        for row in ifaces:
            tag = "up" if row[5] == "UP" else "down"
            self._iface_tree.insert("", "end", values=row, tags=(tag,))

        for item in self._conn_tree.get_children():
            self._conn_tree.delete(item)
        for la, ra, status, pid in conns:
            self._conn_tree.insert("", "end",
                values=(la, ra, status, pid), tags=(status,))
        self._conn_count.set(f"{len(conns)} connections")

    def destroy(self):
        self._running = False
        super().destroy()