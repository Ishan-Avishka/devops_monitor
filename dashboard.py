"""
dashboard.py - Main application window with sidebar navigation and all monitoring panels.
"""
import tkinter as tk
from tkinter import ttk
import threading
import time
import datetime
import psutil
import importlib.util
from utils import (COLORS, FONTS, apply_theme, make_card,
                   sep, StatusDot, format_bytes, format_uptime, UiEventQueue)
import database as db
from alerts import alert_engine, NotificationToast


# ── Lazy imports (keep startup fast) ──────────────────────────────────────────
def _import_panels():
    from cpu_monitor     import CPUMonitor
    from memory_monitor  import MemoryMonitor
    from disk_monitor    import DiskMonitor
    from network_monitor import NetworkMonitor
    from docker_monitor  import DockerMonitor
    from server_manager  import ServerManagerPanel
    from alerts          import AlertsPanel
    from logs_viewer     import LogsViewer
    from settings        import SettingsPanel
    return (CPUMonitor, MemoryMonitor, DiskMonitor, NetworkMonitor,
            DockerMonitor, ServerManagerPanel, AlertsPanel,
            LogsViewer, SettingsPanel)


class Dashboard(tk.Tk):
    SIDEBAR_W = 200
    TOPBAR_H  = 40
    STATUS_INTERVAL = 2     # seconds

    def __init__(self, user: dict):
        super().__init__()
        self._user = user
        apply_theme(self)

        self.title("DevOps Monitor — Dashboard")
        self.configure(bg=COLORS["bg_dark"])
        self.geometry("1400x860")
        self.minsize(1100, 700)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._current_page = None
        self._alert_count  = tk.StringVar(value="0")
        self._notif_enabled = bool(int(db.get_setting("notifications", "1")))
        self._ui_queue = UiEventQueue(self)

        self._build_topbar()
        self._build_sidebar()
        self._build_main()
        self._build_statusbar()

        alert_engine.register_observer(self._on_alert)
        threading.Thread(target=self._status_loop, daemon=True).start()

        # Show Overview first
        self.after(100, lambda: self._navigate("overview"))

    # ─────────────────────────────────────────────────────────────────────────
    # Layout builders
    # ─────────────────────────────────────────────────────────────────────────
    def _build_topbar(self):
        bar = tk.Frame(self, bg=COLORS["bg_panel"], height=self.TOPBAR_H)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # Logo
        tk.Label(bar, text=" ⬡ DEVOPS MONITOR",
                 bg=COLORS["bg_panel"], fg=COLORS["accent_blue"],
                 font=("Courier New", 13, "bold")).pack(side="left",
                                                         padx=16)
        sep(bar, vertical=True).pack(side="left", fill="y", pady=6)

        # Right side
        right = tk.Frame(bar, bg=COLORS["bg_panel"])
        right.pack(side="right", padx=12)

        # Alert badge
        alert_badge = tk.Frame(right, bg=COLORS["accent_red"], padx=6)
        alert_badge.pack(side="right", padx=6)
        tk.Label(alert_badge, text="⚠",
                 bg=COLORS["accent_red"], fg="white",
                 font=FONTS["small"]).pack(side="left")
        tk.Label(alert_badge, textvariable=self._alert_count,
                 bg=COLORS["accent_red"], fg="white",
                 font=FONTS["small"]).pack(side="left")

        # User badge
        tk.Label(right,
                 text=f"  {self._user['username'].upper()}  "
                      f"[{self._user['role']}]",
                 bg=COLORS["bg_panel"],
                 fg=COLORS["text_secondary"],
                 font=FONTS["small"]).pack(side="right")

        # Clock
        self._clock_var = tk.StringVar()
        tk.Label(bar, textvariable=self._clock_var,
                 bg=COLORS["bg_panel"],
                 fg=COLORS["text_muted"],
                 font=FONTS["mono"]).pack(side="right", padx=12)
        self._tick_clock()

    def _tick_clock(self):
        self._clock_var.set(datetime.datetime.now().strftime(
            "%Y-%m-%d  %H:%M:%S"))
        self.after(1000, self._tick_clock)

    def _build_sidebar(self):
        self._sidebar = tk.Frame(self, bg=COLORS["bg_panel"],
                                  width=self.SIDEBAR_W)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        tk.Frame(self._sidebar, bg=COLORS["border"], height=1).pack(
            fill="x", pady=(0, 8))

        # Navigation items: (icon, label, page_key)
        nav_items = [
            ("◈",  "Overview",       "overview"),
            ("⚡",  "CPU",            "cpu"),
            ("🧠", "Memory",          "memory"),
            ("💾", "Disk",            "disk"),
            ("🌐", "Network",         "network"),
            ("🐳", "Docker",          "docker"),
            ("🖥",  "Servers",         "servers"),
            ("⚠",  "Alerts",          "alerts"),
            ("📋", "Logs",            "logs"),
            ("⚙",  "Settings",       "settings"),
        ]
        self._nav_btns: dict[str, tk.Label] = {}
        for icon, label, key in nav_items:
            btn = self._make_nav_btn(icon, label, key)
            btn.pack(fill="x", padx=8, pady=1)
            self._nav_btns[key] = btn

        sep(self._sidebar).pack(fill="x", pady=8, padx=8)

        # Mini stats at bottom of sidebar
        self._sidebar_stats = tk.Frame(self._sidebar, bg=COLORS["bg_panel"])
        self._sidebar_stats.pack(fill="x", side="bottom", pady=8, padx=8)
        self._mini_vars: dict[str, tk.StringVar] = {}
        for label, key, color in [
            ("CPU",  "cpu",  COLORS["accent_blue"]),
            ("RAM",  "ram",  COLORS["accent_purple"]),
            ("DISK", "disk", COLORS["accent_yellow"]),
        ]:
            row = tk.Frame(self._sidebar_stats, bg=COLORS["bg_panel"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label,
                     bg=COLORS["bg_panel"], fg=COLORS["text_muted"],
                     font=FONTS["label"], width=5).pack(side="left")
            var = tk.StringVar(value="—%")
            self._mini_vars[key] = var
            tk.Label(row, textvariable=var,
                     bg=COLORS["bg_panel"], fg=color,
                     font=FONTS["mono_small"]).pack(side="left")

        sep(self._sidebar).pack(fill="x", pady=8, padx=8)
        integ = tk.Frame(self._sidebar, bg=COLORS["bg_panel"])
        integ.pack(fill="x", side="bottom", padx=8, pady=(0, 6))
        tk.Label(integ, text="Integrations",
                 bg=COLORS["bg_panel"], fg=COLORS["text_muted"],
                 font=FONTS["label"]).pack(anchor="w")
        self._add_integration_badge(
            integ,
            "Docker SDK",
            bool(importlib.util.find_spec("docker")),
        )
        self._add_integration_badge(
            integ,
            "Paramiko SSH",
            bool(importlib.util.find_spec("paramiko")),
        )

    def _add_integration_badge(self, parent, name: str, available: bool):
        color = COLORS["accent_green"] if available else COLORS["accent_red"]
        state = "ready" if available else "missing"
        tk.Label(parent, text=f"• {name}: {state}",
                 bg=COLORS["bg_panel"], fg=color,
                 font=FONTS["label"]).pack(anchor="w")

    def _make_nav_btn(self, icon: str, label: str, key: str) -> tk.Label:
        frame = tk.Frame(self._sidebar, bg=COLORS["bg_panel"],
                         cursor="hand2")
        tk.Label(frame, text=f"  {icon}  {label}",
                 bg=COLORS["bg_panel"],
                 fg=COLORS["text_secondary"],
                 font=FONTS["body"],
                 anchor="w").pack(fill="x", padx=8, pady=5)
        frame.bind("<Button-1>", lambda _e, k=key: self._navigate(k))
        for child in frame.winfo_children():
            child.bind("<Button-1>", lambda _e, k=key: self._navigate(k))
        frame.bind("<Enter>", lambda _e, f=frame: self._nav_hover(f, True))
        frame.bind("<Leave>", lambda _e, f=frame: self._nav_hover(f, False))
        return frame

    def _nav_hover(self, frame, enter: bool):
        if frame == self._nav_btns.get(self._current_page):
            return
        bg = COLORS["bg_hover"] if enter else COLORS["bg_panel"]
        frame.configure(bg=bg)
        for c in frame.winfo_children():
            c.configure(bg=bg)

    def _highlight_nav(self, key: str):
        for k, frame in self._nav_btns.items():
            is_active = (k == key)
            bg = COLORS["bg_card"] if is_active else COLORS["bg_panel"]
            fg = COLORS["accent_blue"] if is_active else COLORS["text_secondary"]
            frame.configure(bg=bg)
            for c in frame.winfo_children():
                c.configure(bg=bg, fg=fg)

    def _build_main(self):
        self._main = tk.Frame(self, bg=COLORS["bg_dark"])
        self._main.pack(side="left", fill="both", expand=True)

    def _build_statusbar(self):
        sb = tk.Frame(self, bg=COLORS["bg_panel"], height=24)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self._sb_vars = {}
        for label, key, color in [
            ("CPU:", "cpu", COLORS["accent_blue"]),
            ("RAM:", "ram", COLORS["accent_purple"]),
            ("NET↓:", "net_d", COLORS["accent_green"]),
            ("NET↑:", "net_u", COLORS["accent_orange"]),
        ]:
            tk.Label(sb, text=label,
                     bg=COLORS["bg_panel"], fg=COLORS["text_muted"],
                     font=FONTS["label"]).pack(side="left", padx=(8, 0))
            var = tk.StringVar(value="—")
            self._sb_vars[key] = var
            tk.Label(sb, textvariable=var,
                     bg=COLORS["bg_panel"], fg=color,
                     font=FONTS["mono_small"]).pack(side="left", padx=(2, 8))

        self._sb_alert_var = tk.StringVar(value="No alerts")
        tk.Label(sb, textvariable=self._sb_alert_var,
                 bg=COLORS["bg_panel"], fg=COLORS["accent_yellow"],
                 font=FONTS["label"]).pack(side="right", padx=8)

    # ─────────────────────────────────────────────────────────────────────────
    # Navigation
    # ─────────────────────────────────────────────────────────────────────────
    def _navigate(self, key: str):
        if self._current_page == key:
            return
        self._current_page = key
        self._highlight_nav(key)

        # Clear and destroy previous page widgets so monitor threads can stop.
        for widget in self._main.winfo_children():
            widget.destroy()

        scroll_frame = _ScrollableFrame(self._main)
        scroll_frame.pack(fill="both", expand=True)
        loading = tk.Label(scroll_frame.inner,
                           text="Loading panel...",
                           bg=COLORS["bg_dark"], fg=COLORS["text_muted"],
                           font=FONTS["body"])
        loading.pack(pady=30)
        self.update_idletasks()

        panel = self._get_panel(key, scroll_frame.inner)
        loading.destroy()
        panel.pack(fill="both", expand=True, padx=16, pady=12)

    def _get_panel(self, key: str, host: tk.Frame) -> tk.Frame:
        (CPUMonitor, MemoryMonitor, DiskMonitor, NetworkMonitor,
         DockerMonitor, ServerManagerPanel, AlertsPanel,
         LogsViewer, SettingsPanel) = _import_panels()

        panel_map = {
            "overview": lambda: OverviewPanel(host),
            "cpu":      lambda: CPUMonitor(host),
            "memory":   lambda: MemoryMonitor(host),
            "disk":     lambda: DiskMonitor(host),
            "network":  lambda: NetworkMonitor(host),
            "docker":   lambda: DockerMonitor(host),
            "servers":  lambda: ServerManagerPanel(host),
            "alerts":   lambda: AlertsPanel(host),
            "logs":     lambda: LogsViewer(host),
            "settings": lambda: SettingsPanel(host),
        }
        factory = panel_map.get(key)
        if not factory:
            return tk.Frame(host, bg=COLORS["bg_dark"])
        return factory()

    # ─────────────────────────────────────────────────────────────────────────
    # Status loop
    # ─────────────────────────────────────────────────────────────────────────
    def _status_loop(self):
        prev_net = psutil.net_io_counters()
        while True:
            try:
                cpu  = psutil.cpu_percent(interval=1)
                mem  = psutil.virtual_memory().percent
                net  = psutil.net_io_counters()
                disk = psutil.disk_usage("/").percent
                dt   = self.STATUS_INTERVAL

                rd = (net.bytes_recv - prev_net.bytes_recv) / dt
                ud = (net.bytes_sent - prev_net.bytes_sent) / dt
                prev_net = net

                alerts = db.get_alerts(limit=1, acknowledged=False)
                last   = alerts[0]["message"][:40] if alerts else "No alerts"
                n_alerts = db.get_active_alert_count()

                self._ui_queue.post(
                    self._update_status,
                    cpu,
                    mem,
                    rd,
                    ud,
                    disk,
                    last,
                    n_alerts,
                )
            except Exception as e:
                db.safe_write_log("ERROR", "Dashboard", f"Status loop failed: {e}")
            time.sleep(self.STATUS_INTERVAL)

    def _update_status(self, cpu, mem, recv, sent, disk, last_alert, n_alerts):
        self._sb_vars["cpu"].set(f"{cpu:.0f}%")
        self._sb_vars["ram"].set(f"{mem:.0f}%")
        self._sb_vars["net_d"].set(format_bytes(int(recv)) + "/s")
        self._sb_vars["net_u"].set(format_bytes(int(sent)) + "/s")
        self._sb_alert_var.set(f"⚠ {last_alert}")
        self._alert_count.set(str(n_alerts))
        # Sidebar mini
        self._mini_vars["cpu"].set(f"{cpu:.0f}%")
        self._mini_vars["ram"].set(f"{mem:.0f}%")
        self._mini_vars["disk"].set(f"{disk:.0f}%")

    def _on_alert(self, alert: dict):
        """Receive new alerts from the engine."""
        if self._notif_enabled:
            self.after(0, lambda: NotificationToast(
                self, alert["message"], alert["severity"]
            ))

    def _on_close(self):
        self._ui_queue.stop()
        for widget in self._main.winfo_children():
            try:
                widget.destroy()
            except Exception as e:
                db.safe_write_log("WARNING", "Dashboard", f"Widget destroy failed: {e}")
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: scrollable container
# ─────────────────────────────────────────────────────────────────────────────
class _ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS["bg_dark"], **kwargs)
        canvas = tk.Canvas(self, bg=COLORS["bg_dark"],
                           highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(canvas, bg=COLORS["bg_dark"])
        win_id = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda _e: canvas.configure(
                            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win_id, width=e.width))
        self._canvas = canvas
        canvas.bind("<Enter>", self._bind_wheel)
        canvas.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _event):
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)

    def _unbind_wheel(self, _event):
        self._canvas.unbind("<MouseWheel>")

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def destroy(self):
        self._canvas.unbind("<MouseWheel>")
        super().destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Overview Panel (summary of all metrics)
# ─────────────────────────────────────────────────────────────────────────────
class OverviewPanel(ttk.Frame):
    INTERVAL = 3

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        self._running = True
        self._build_ui()
        threading.Thread(target=self._poll, daemon=True).start()

    def _build_ui(self):
        tk.Label(self, text="◈  SYSTEM OVERVIEW",
                 bg=COLORS["bg_dark"], fg=COLORS["accent_blue"],
                 font=FONTS["heading"]).pack(anchor="w", pady=(0, 12))

        # Metric cards row 1
        self._vars: dict[str, tk.StringVar] = {}
        row1_metrics = [
            ("⚡ CPU Usage",     "cpu_pct",   COLORS["accent_blue"],    " %"),
            ("🧠 Memory",        "mem_pct",   COLORS["accent_purple"],  " %"),
            ("💾 Disk (root)",   "disk_pct",  COLORS["accent_yellow"],  " %"),
            ("🌐 Net ↓",         "net_recv",  COLORS["accent_green"],   ""),
            ("🌐 Net ↑",         "net_sent",  COLORS["accent_orange"],  ""),
            ("🔲 Processes",     "procs",     COLORS["info"],           ""),
            ("🕒 Uptime",        "uptime",    COLORS["text_primary"],   ""),
            ("🔥 Load Avg",      "load",      COLORS["accent_red"],     ""),
        ]
        cards_row = tk.Frame(self, bg=COLORS["bg_dark"])
        cards_row.pack(fill="x", pady=(0, 12))
        for label, key, color, suffix in row1_metrics:
            card, inner = make_card(cards_row)
            card.pack(side="left", fill="x", expand=True, padx=3)
            var = tk.StringVar(value="—")
            self._vars[key] = var
            tk.Label(inner, textvariable=var,
                     bg=COLORS["bg_card"], fg=color,
                     font=FONTS["metric_sm"]).pack()
            tk.Label(inner, text=label,
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=FONTS["label"]).pack()

        # CPU cores mini bars
        cores_card, cores_inner = make_card(self, "CPU Cores")
        cores_card.pack(fill="x", pady=(0, 10))
        self._cores_inner = cores_inner
        self._core_bars: list[tuple] = []

        # Memory bar
        mem_card, mem_inner = make_card(self, "Memory Breakdown")
        mem_card.pack(fill="x", pady=(0, 10))
        self._mem_vars = {}
        for label, key, color in [
            ("RAM Used",  "ram_used",  COLORS["accent_purple"]),
            ("RAM Free",  "ram_free",  COLORS["accent_green"]),
            ("Swap Used", "swap_used", COLORS["accent_orange"]),
        ]:
            row = tk.Frame(mem_inner, bg=COLORS["bg_card"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{label}:",
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=FONTS["small"], width=12, anchor="e").pack(side="left")
            var = tk.StringVar(value="—")
            self._mem_vars[key] = var
            tk.Label(row, textvariable=var,
                     bg=COLORS["bg_card"], fg=color,
                     font=FONTS["mono_small"]).pack(side="left", padx=4)

        # Recent alerts
        alerts_card, alerts_inner = make_card(self, "Recent Alerts")
        alerts_card.pack(fill="x", pady=(0, 10))
        self._alert_text = tk.Text(alerts_inner,
                                    bg=COLORS["bg_panel"],
                                    fg=COLORS["text_primary"],
                                    font=FONTS["mono_small"],
                                    height=5, relief="flat",
                                    state="disabled")
        self._alert_text.tag_configure("critical", foreground=COLORS["accent_red"])
        self._alert_text.tag_configure("warning",  foreground=COLORS["accent_yellow"])
        self._alert_text.pack(fill="x")

    def _build_core_bars(self, n_cores):
        for w in self._cores_inner.winfo_children():
            w.destroy()
        self._core_bars = []
        cols = 8
        for i in range(n_cores):
            row, col = divmod(i, cols)
            cell = tk.Frame(self._cores_inner, bg=COLORS["bg_card"])
            cell.grid(row=row, column=col, padx=4, pady=3, sticky="ew")
            tk.Label(cell, text=f"C{i}",
                     bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                     font=FONTS["label"]).pack(anchor="w")
            var = tk.DoubleVar()
            bar = ttk.Progressbar(cell, variable=var, maximum=100, length=80,
                                   style="blue.Horizontal.TProgressbar")
            bar.pack()
            self._core_bars.append((bar, var))
            self._cores_inner.columnconfigure(col, weight=1)

    def _poll(self):
        prev_net = psutil.net_io_counters()
        first = True
        while self._running:
            try:
                cpu    = psutil.cpu_percent(interval=1)
                cores  = psutil.cpu_percent(interval=None, percpu=True)
                mem    = psutil.virtual_memory()
                swap   = psutil.swap_memory()
                disk   = psutil.disk_usage("/")
                net    = psutil.net_io_counters()
                procs  = len(psutil.pids())
                boot   = psutil.boot_time()
                uptime = time.time() - boot
                try:
                    load = psutil.getloadavg()
                    load_str = f"{load[0]:.2f} {load[1]:.2f} {load[2]:.2f}"
                except AttributeError:
                    load_str = "N/A"

                rd = (net.bytes_recv - prev_net.bytes_recv) / self.INTERVAL
                ud = (net.bytes_sent - prev_net.bytes_sent) / self.INTERVAL
                prev_net = net

                alerts = db.get_alerts(limit=5, acknowledged=False)
                self.after(0, lambda c=cpu, co=cores, m=mem, sw=swap,
                                      d=disk, r=rd, u=ud, p=procs,
                                      up=uptime, ld=load_str,
                                      al=alerts, f=first:
                    self._update(c, co, m, sw, d, r, u, p, up, ld, al, f))
                first = False
            except Exception as e:
                db.write_log("ERROR", "Overview", str(e))
            time.sleep(self.INTERVAL)

    def _update(self, cpu, cores, mem, swap, disk, rd, ud,
                procs, uptime, load_str, alerts, first):
        v = self._vars
        v["cpu_pct"].set(f"{cpu:.1f}%")
        v["mem_pct"].set(f"{mem.percent:.1f}%")
        v["disk_pct"].set(f"{disk.percent:.1f}%")
        v["net_recv"].set(format_bytes(int(rd)) + "/s")
        v["net_sent"].set(format_bytes(int(ud)) + "/s")
        v["procs"].set(str(procs))
        v["uptime"].set(format_uptime(uptime))
        v["load"].set(load_str)

        mv = self._mem_vars
        mv["ram_used"].set(format_bytes(mem.used))
        mv["ram_free"].set(format_bytes(mem.free))
        mv["swap_used"].set(format_bytes(swap.used))

        if first or len(self._core_bars) != len(cores):
            self._build_core_bars(len(cores))
        for i, (bar, var) in enumerate(self._core_bars):
            c = cores[i] if i < len(cores) else 0
            var.set(c)

        # Alerts
        self._alert_text.configure(state="normal")
        self._alert_text.delete(1.0, "end")
        if not alerts:
            self._alert_text.insert("end", "No active alerts.\n")
        else:
            for a in alerts:
                sev = a.get("severity", "info")
                tag = sev if sev in ("critical","warning") else ""
                self._alert_text.insert(
                    "end",
                    f"[{a['ts'][:19]}] {sev.upper():<8} {a['message']}\n",
                    tag)
        self._alert_text.configure(state="disabled")

    def destroy(self):
        self._running = False
        super().destroy()