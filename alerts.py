"""
alerts.py - Alert engine: evaluates metrics against rules and fires notifications.
"""
import threading
import datetime
import tkinter as tk
from tkinter import ttk
from utils import COLORS, FONTS, make_card, sep, StatusDot, timestamp_now, UiEventQueue
import database as db


# ─── ALERT ENGINE ─────────────────────────────────────────────────────────────
class AlertEngine:
    """
    Singleton engine.  Call check(server, metric, value) from any monitor.
    Observers (callbacks) are notified on new alerts.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._observers = []
        self._cooldown: dict[str, datetime.datetime] = {}
        self._cooldown_secs = 60          # don't re-fire same alert within 60 s
        self._rules = []
        self._reload_rules()
        self._rule_timer = None

    def _reload_rules(self):
        self._rules = db.get_alert_rules()

    def register_observer(self, cb):
        """cb(alert_dict) will be called on new alerts."""
        self._observers.append(cb)

    def unregister_observer(self, cb):
        if cb in self._observers:
            self._observers.remove(cb)

    def check(self, server: str, metric: str, value: float):
        for rule in self._rules:
            if rule["metric"] != metric:
                continue
            triggered = False
            op = rule.get("operator", ">")
            thr = float(rule["threshold"])
            if op == ">"  and value >  thr: triggered = True
            if op == ">=" and value >= thr: triggered = True
            if op == "<"  and value <  thr: triggered = True
            if op == "<=" and value <= thr: triggered = True
            if op == "==" and value == thr: triggered = True

            if triggered:
                key = f"{server}:{rule['name']}"
                now = datetime.datetime.now()
                last = self._cooldown.get(key)
                if last and (now - last).total_seconds() < self._cooldown_secs:
                    continue
                self._cooldown[key] = now
                alert = {
                    "server":    server,
                    "metric":    metric,
                    "value":     value,
                    "threshold": thr,
                    "severity":  rule["severity"],
                    "message":   f"[{rule['severity'].upper()}] {rule['name']}: "
                                 f"{metric}={value:.1f} {op} {thr}",
                    "ts":        timestamp_now(),
                }
                db.add_alert(**{k: alert[k] for k in
                                ("server","metric","value",
                                 "threshold","severity","message")})
                db.write_log("ALERT", server,
                             f"{rule['name']}: {metric}={value:.1f}")
                for obs in self._observers:
                    try:
                        obs(alert)
                    except Exception as e:
                        db.safe_write_log("ERROR", "AlertEngine", f"Observer failed: {e}")


alert_engine = AlertEngine()


# ─── ALERT PANEL (UI) ─────────────────────────────────────────────────────────
class AlertsPanel(ttk.Frame):
    SEV_COLORS = {
        "critical": COLORS["accent_red"],
        "warning":  COLORS["accent_yellow"],
        "info":     COLORS["info"],
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        self._ui_queue = UiEventQueue(self)
        self._build_ui()
        alert_engine.register_observer(self._on_new_alert)
        self._refresh()

    # ── Build ──
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="⚠  ALERT MANAGER",
                 bg=COLORS["bg_dark"], fg=COLORS["accent_red"],
                 font=FONTS["heading"]).pack(side="left")

        btn_frame = tk.Frame(hdr, bg=COLORS["bg_dark"])
        btn_frame.pack(side="right")
        ttk.Button(btn_frame, text="Ack All",
                   command=self._ack_all).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Show Acked",
                   command=self._show_acked).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Refresh",
                   command=self._refresh).pack(side="left", padx=4)

        # Summary cards
        summary_row = tk.Frame(self, bg=COLORS["bg_dark"])
        summary_row.pack(fill="x", pady=(0, 10))
        self._crit_var = tk.StringVar(value="0")
        self._warn_var = tk.StringVar(value="0")
        self._total_var = tk.StringVar(value="0")
        for label, var, color in [
            ("CRITICAL", self._crit_var, COLORS["accent_red"]),
            ("WARNING",  self._warn_var, COLORS["accent_yellow"]),
            ("TOTAL",    self._total_var, COLORS["info"]),
        ]:
            card, inner = make_card(summary_row)
            card.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(inner, textvariable=var,
                     bg=COLORS["bg_card"], fg=color,
                     font=FONTS["metric"]).pack()
            tk.Label(inner, text=label,
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=FONTS["small"]).pack()

        # Treeview
        tree_frame = tk.Frame(self, bg=COLORS["bg_dark"])
        tree_frame.pack(fill="both", expand=True)

        cols = ("ts", "server", "metric", "value", "severity", "message")
        self._tree = ttk.Treeview(tree_frame, columns=cols,
                                   show="headings", height=18)
        widths = {"ts": 150, "server": 120, "metric": 130,
                  "value": 80, "severity": 90, "message": 400}
        for c in cols:
            self._tree.heading(c, text=c.upper())
            self._tree.column(c, width=widths.get(c, 100), anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Tags for severity colors
        self._tree.tag_configure("critical", foreground=COLORS["accent_red"])
        self._tree.tag_configure("warning",  foreground=COLORS["accent_yellow"])
        self._tree.tag_configure("info",     foreground=COLORS["info"])

        # Action buttons
        act = tk.Frame(self, bg=COLORS["bg_dark"])
        act.pack(fill="x", pady=6)
        ttk.Button(act, text="Acknowledge Selected",
                   command=self._ack_selected).pack(side="left", padx=4)
        ttk.Button(act, text="Clear Acknowledged",
                   command=self._clear_acked).pack(side="left", padx=4)

        self._show_acked_flag = False

    # ── Data ──
    def _refresh(self):
        alerts = db.get_alerts(limit=300, acknowledged=self._show_acked_flag)
        for item in self._tree.get_children():
            self._tree.delete(item)

        crits = warns = 0
        for a in alerts:
            sev = a.get("severity", "info")
            if sev == "critical": crits += 1
            elif sev == "warning": warns += 1
            self._tree.insert("", "end", iid=str(a["id"]),
                values=(a["ts"], a.get("server","local"),
                        a["metric"], f"{a['value']:.1f}",
                        sev.upper(), a["message"]),
                tags=(sev,))

        self._crit_var.set(str(crits))
        self._warn_var.set(str(warns))
        self._total_var.set(str(len(alerts)))

    def _ack_selected(self):
        sel = self._tree.selection()
        for iid in sel:
            db.acknowledge_alert(int(iid))
        self._refresh()

    def _ack_all(self):
        db.acknowledge_all_alerts()
        self._refresh()

    def _clear_acked(self):
        self._show_acked_flag = False
        self._refresh()

    def _show_acked(self):
        self._show_acked_flag = True
        self._refresh()

    def _on_new_alert(self, alert: dict):
        """Called by AlertEngine on main or background thread."""
        self._ui_queue.post(self._append_alert_row, alert)

    def _append_alert_row(self, alert: dict):
        if self._show_acked_flag:
            return
        sev = alert.get("severity", "info")
        self._tree.insert(
            "",
            0,
            values=(
                alert.get("ts", "")[:19],
                alert.get("server", "local"),
                alert.get("metric", ""),
                f"{float(alert.get('value', 0)):.1f}",
                sev.upper(),
                alert.get("message", ""),
            ),
            tags=(sev,),
        )
        try:
            total = int(self._total_var.get()) + 1
            self._total_var.set(str(total))
            if sev == "critical":
                self._crit_var.set(str(int(self._crit_var.get()) + 1))
            elif sev == "warning":
                self._warn_var.set(str(int(self._warn_var.get()) + 1))
        except ValueError:
            self._refresh()

    def destroy(self):
        alert_engine.unregister_observer(self._on_new_alert)
        self._ui_queue.stop()
        super().destroy()


# ─── NOTIFICATION TOAST ───────────────────────────────────────────────────────
class NotificationToast(tk.Toplevel):
    """Small popup notification in the corner of the screen."""
    def __init__(self, master, message: str, severity: str = "warning",
                 duration: int = 5000):
        super().__init__(master)
        sev_colors = {
            "critical": COLORS["accent_red"],
            "warning":  COLORS["accent_yellow"],
            "info":     COLORS["info"],
        }
        color = sev_colors.get(severity, COLORS["accent_blue"])

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=COLORS["bg_card"])

        # Position bottom-right
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"360x80+{sw - 380}+{sh - 120}")

        tk.Frame(self, bg=color, width=4).pack(side="left", fill="y")
        body = tk.Frame(self, bg=COLORS["bg_card"])
        body.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "🔵")
        tk.Label(body, text=f"{icon}  {severity.upper()}",
                 bg=COLORS["bg_card"], fg=color,
                 font=FONTS["subheading"]).pack(anchor="w")
        tk.Label(body, text=message[:60],
                 bg=COLORS["bg_card"], fg=COLORS["text_primary"],
                 font=FONTS["small"], wraplength=300,
                 justify="left").pack(anchor="w")

        tk.Button(self, text="✕", bg=COLORS["bg_card"],
                  fg=COLORS["text_muted"], relief="flat",
                  command=self.destroy, font=FONTS["small"]).pack(
            side="right", anchor="n", padx=4, pady=4)

        self.after(duration, self.destroy)