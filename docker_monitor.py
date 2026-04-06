"""
docker_monitor.py - Docker container monitoring panel.
Falls back gracefully when Docker is unavailable.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import datetime
from utils import COLORS, FONTS, make_card, sep, StatusDot, format_bytes
import database as db

try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False


def _get_client():
    if not DOCKER_AVAILABLE:
        return None
    try:
        return docker.from_env(timeout=5)
    except Exception:
        return None


class DockerMonitor(ttk.Frame):
    INTERVAL = 5

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        self._running = True
        self._docker  = _get_client()
        self._build_ui()
        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="🐳  DOCKER MONITOR",
                 bg=COLORS["bg_dark"], fg=COLORS["info"],
                 font=FONTS["heading"]).pack(side="left")
        self._status_label = tk.Label(hdr, text="",
                                      bg=COLORS["bg_dark"],
                                      fg=COLORS["text_muted"],
                                      font=FONTS["small"])
        self._status_label.pack(side="right")

        btn_row = tk.Frame(self, bg=COLORS["bg_dark"])
        btn_row.pack(fill="x", pady=(0, 6))
        ttk.Button(btn_row, text="⟳ Refresh",
                   command=self._manual_refresh).pack(side="left", padx=3)
        ttk.Button(btn_row, text="Start Selected",
                   command=self._start_container).pack(side="left", padx=3)
        ttk.Button(btn_row, text="Stop Selected",
                   command=self._stop_container).pack(side="left", padx=3)
        ttk.Button(btn_row, text="Restart Selected",
                   command=self._restart_container).pack(side="left", padx=3)
        ttk.Button(btn_row, text="View Logs",
                   command=self._view_logs).pack(side="left", padx=3)

        # Summary stats row
        stat_row = tk.Frame(self, bg=COLORS["bg_dark"])
        stat_row.pack(fill="x", pady=(0, 8))
        self._stat_vars = {}
        for label, key, color in [
            ("Running",  "running",  COLORS["accent_green"]),
            ("Stopped",  "stopped",  COLORS["accent_red"]),
            ("Paused",   "paused",   COLORS["accent_yellow"]),
            ("Total",    "total",    COLORS["info"]),
            ("Images",   "images",   COLORS["accent_purple"]),
        ]:
            card, inner = make_card(stat_row)
            card.pack(side="left", fill="x", expand=True, padx=3)
            var = tk.StringVar(value="—")
            self._stat_vars[key] = var
            tk.Label(inner, textvariable=var,
                     bg=COLORS["bg_card"], fg=color,
                     font=FONTS["metric_sm"]).pack()
            tk.Label(inner, text=label,
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=FONTS["small"]).pack()

        # Container table
        tree_card, tree_inner = make_card(self, "Containers")
        tree_card.pack(fill="both", expand=True)
        self._tree = self._build_tree(tree_inner)

        # Log viewer sub-panel
        log_card, log_inner = make_card(self, "Container Logs")
        log_card.pack(fill="x", pady=(8, 0))
        log_hdr = tk.Frame(log_inner, bg=COLORS["bg_card"])
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text="Container:",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=FONTS["small"]).pack(side="left")
        self._log_container_var = tk.StringVar()
        self._log_combo = ttk.Combobox(log_hdr,
                                        textvariable=self._log_container_var,
                                        width=24, state="readonly")
        self._log_combo.pack(side="left", padx=4)
        ttk.Button(log_hdr, text="Tail Logs",
                   command=self._tail_logs).pack(side="left")

        self._log_text = tk.Text(log_inner,
                                  bg=COLORS["bg_panel"],
                                  fg=COLORS["accent_green"],
                                  font=FONTS["mono_small"],
                                  height=8, relief="flat",
                                  state="disabled")
        lsb = ttk.Scrollbar(log_inner, orient="vertical",
                            command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=lsb.set)
        self._log_text.pack(side="left", fill="both", expand=True,
                             pady=(4, 0))
        lsb.pack(side="right", fill="y")

    def _build_tree(self, parent) -> ttk.Treeview:
        cols = ("id", "name", "image", "status", "ports",
                "cpu_pct", "mem_usage", "created")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=10)
        hdrs = {
            "id":        ("ID",       70),
            "name":      ("Name",    160),
            "image":     ("Image",   180),
            "status":    ("Status",  100),
            "ports":     ("Ports",   160),
            "cpu_pct":   ("CPU%",     70),
            "mem_usage": ("Memory",   90),
            "created":   ("Created", 130),
        }
        for c, (h, w) in hdrs.items():
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w")
        tree.tag_configure("running", foreground=COLORS["accent_green"])
        tree.tag_configure("exited",  foreground=COLORS["accent_red"])
        tree.tag_configure("paused",  foreground=COLORS["accent_yellow"])
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return tree

    # ── Poll ──────────────────────────────────────────────────────────────────
    def _poll_loop(self):
        while self._running:
            self._manual_refresh()
            time.sleep(self.INTERVAL)

    def _manual_refresh(self):
        if not DOCKER_AVAILABLE:
            self.after(0, lambda: self._status_label.config(
                text="docker SDK not installed", fg=COLORS["accent_yellow"]))
            return
        if not self._docker:
            self._docker = _get_client()
        if not self._docker:
            self.after(0, lambda: self._status_label.config(
                text="Docker not running", fg=COLORS["accent_red"]))
            return

        threading.Thread(target=self._fetch_data, daemon=True).start()

    def _fetch_data(self):
        try:
            containers = self._docker.containers.list(all=True)
            images     = self._docker.images.list()
            data = []
            for c in containers:
                # Attempt to get stats (non-blocking)
                cpu_pct = "—"
                mem_str = "—"
                try:
                    stats = c.stats(stream=False)
                    cpu_delta = (stats["cpu_stats"]["cpu_usage"]["total_usage"] -
                                 stats["precpu_stats"]["cpu_usage"]["total_usage"])
                    sys_delta = (stats["cpu_stats"]["system_cpu_usage"] -
                                 stats["precpu_stats"]["system_cpu_usage"])
                    n_cpus = stats["cpu_stats"].get("online_cpus", 1)
                    if sys_delta > 0:
                        cpu_pct = f"{(cpu_delta/sys_delta)*n_cpus*100:.1f}%"
                    mem_u = stats["memory_stats"].get("usage", 0)
                    mem_l = stats["memory_stats"].get("limit", 1)
                    mem_str = (f"{format_bytes(mem_u)} / "
                               f"{format_bytes(mem_l)}")
                except Exception:
                    pass

                ports_raw = c.ports
                ports = ", ".join(
                    f"{k.split('/')[0]}→{v[0]['HostPort']}"
                    for k, v in ports_raw.items() if v
                ) if ports_raw else ""

                data.append({
                    "id":        c.short_id,
                    "name":      c.name,
                    "image":     c.image.tags[0] if c.image.tags else c.image.short_id,
                    "status":    c.status,
                    "ports":     ports,
                    "cpu_pct":   cpu_pct,
                    "mem_usage": mem_str,
                    "created":   c.attrs.get("Created", "")[:19],
                    "_full_id":  c.id,
                })
            self.after(0, lambda: self._update_ui(data, len(images)))
        except Exception as e:
            db.write_log("ERROR", "DockerMonitor", str(e))
            self.after(0, lambda: self._status_label.config(
                text=f"Error: {e}", fg=COLORS["accent_red"]))

    def _update_ui(self, data, n_images):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._status_label.config(text=f"Updated {ts}", fg=COLORS["text_muted"])

        running = sum(1 for d in data if d["status"] == "running")
        stopped = sum(1 for d in data if d["status"] == "exited")
        paused  = sum(1 for d in data if d["status"] == "paused")
        self._stat_vars["running"].set(str(running))
        self._stat_vars["stopped"].set(str(stopped))
        self._stat_vars["paused"].set(str(paused))
        self._stat_vars["total"].set(str(len(data)))
        self._stat_vars["images"].set(str(n_images))

        for item in self._tree.get_children():
            self._tree.delete(item)
        names = []
        for d in data:
            tag = d["status"] if d["status"] in ("running","exited","paused") else ""
            self._tree.insert("", "end", iid=d["_full_id"], tags=(tag,),
                values=(d["id"], d["name"], d["image"], d["status"],
                        d["ports"], d["cpu_pct"], d["mem_usage"],
                        d["created"]))
            names.append(d["name"])
        self._log_combo["values"] = names

    def _selected_container_id(self) -> str | None:
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _container_action(self, action: str):
        cid = self._selected_container_id()
        if not cid or not self._docker:
            return
        def _do():
            try:
                c = self._docker.containers.get(cid)
                getattr(c, action)()
                time.sleep(1)
                self._manual_refresh()
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Docker Error", str(e)))
        threading.Thread(target=_do, daemon=True).start()

    def _start_container(self):   self._container_action("start")
    def _stop_container(self):    self._container_action("stop")
    def _restart_container(self): self._container_action("restart")

    def _view_logs(self):
        cid = self._selected_container_id()
        if not cid or not self._docker:
            return
        def _fetch():
            try:
                c = self._docker.containers.get(cid)
                logs = c.logs(tail=200).decode(errors="replace")
                self.after(0, lambda: self._show_logs(logs))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Log Error", str(e)))
        threading.Thread(target=_fetch, daemon=True).start()

    def _tail_logs(self):
        name = self._log_container_var.get()
        if not name or not self._docker:
            return
        def _fetch():
            try:
                c = self._docker.containers.get(name)
                logs = c.logs(tail=100).decode(errors="replace")
                self.after(0, lambda: self._show_logs(logs))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Log Error", str(e)))
        threading.Thread(target=_fetch, daemon=True).start()

    def _show_logs(self, logs: str):
        self._log_text.configure(state="normal")
        self._log_text.delete(1.0, "end")
        self._log_text.insert("end", logs)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def destroy(self):
        self._running = False
        super().destroy()