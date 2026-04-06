"""
server_manager.py - UI panel to manage remote server connections and view their metrics.
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
from utils import (COLORS, FONTS, make_card, sep, StatusDot,
                   format_bytes, format_uptime)
from ssh_client import SSHClient
from alerts import alert_engine
import database as db


class ServerManagerPanel(ttk.Frame):
    POLL_INTERVAL = 15

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        self._clients: dict[int, SSHClient] = {}   # id -> SSHClient
        self._running = True
        self._build_ui()
        self._load_servers()
        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="🖥  SERVER MANAGER",
                 bg=COLORS["bg_dark"], fg=COLORS["accent_orange"],
                 font=FONTS["heading"]).pack(side="left")
        btns = tk.Frame(hdr, bg=COLORS["bg_dark"])
        btns.pack(side="right")
        ttk.Button(btns, text="+ Add Server",
                   command=self._add_server_dialog).pack(side="left", padx=3)
        ttk.Button(btns, text="⟳ Refresh",
                   command=self._load_servers).pack(side="left", padx=3)

        # Server list pane + detail pane
        paned = tk.PanedWindow(self, orient="horizontal",
                               bg=COLORS["bg_dark"],
                               sashwidth=6, sashrelief="flat",
                               sashpad=2)
        paned.pack(fill="both", expand=True)

        # Left: server list
        left_frame = tk.Frame(paned, bg=COLORS["bg_dark"])
        paned.add(left_frame, minsize=260)

        list_card, list_inner = make_card(left_frame, "Servers")
        list_card.pack(fill="both", expand=True)

        self._server_list = tk.Listbox(
            list_inner,
            bg=COLORS["bg_panel"],
            fg=COLORS["text_primary"],
            selectbackground=COLORS["accent_blue"],
            selectforeground=COLORS["bg_dark"],
            font=FONTS["mono"],
            relief="flat",
            borderwidth=0,
            activestyle="none",
        )
        self._server_list.pack(fill="both", expand=True)
        self._server_list.bind("<<ListboxSelect>>", self._on_server_select)

        act_frame = tk.Frame(list_inner, bg=COLORS["bg_card"])
        act_frame.pack(fill="x", pady=(6, 0))
        ttk.Button(act_frame, text="Connect",
                   command=self._connect_selected).pack(side="left", padx=3)
        ttk.Button(act_frame, text="Disconnect",
                   command=self._disconnect_selected).pack(side="left", padx=3)
        ttk.Button(act_frame, text="Delete",
                   command=self._delete_selected).pack(side="left", padx=3)

        # Right: detail
        right_frame = tk.Frame(paned, bg=COLORS["bg_dark"])
        paned.add(right_frame, minsize=500)

        detail_card, detail_inner = make_card(right_frame, "Server Details")
        detail_card.pack(fill="both", expand=True)
        self._detail_frame = detail_inner

        self._detail_placeholder = tk.Label(
            self._detail_frame,
            text="Select a server to view details",
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"],
            font=FONTS["body"],
        )
        self._detail_placeholder.pack(expand=True)

        # Notebook for detail
        self._detail_nb = ttk.Notebook(self._detail_frame)

        # Tab: overview
        self._ov_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(self._ov_frame, text="Overview")
        self._build_overview(self._ov_frame)

        # Tab: terminal-like output
        self._term_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(self._term_frame, text="Terminal")
        self._build_terminal(self._term_frame)

        # Tab: process list
        self._proc_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(self._proc_frame, text="Processes")
        self._build_proc_view(self._proc_frame)

    def _build_overview(self, parent):
        self._ov_vars = {}
        fields = [
            ("Host",        "host"),
            ("Port",        "port"),
            ("Status",      "status"),
            ("Kernel",      "kernel"),
            ("Uptime",      "uptime"),
            ("Load Avg",    "load"),
            ("CPU %",       "cpu"),
            ("RAM %",       "mem"),
            ("Disk %",      "disk"),
        ]
        for i, (label, key) in enumerate(fields):
            row, col = divmod(i, 3)
            tk.Label(parent, text=label + ":",
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=FONTS["small"], width=10, anchor="e").grid(
                row=row, column=col * 2, padx=(8, 2), pady=4, sticky="e")
            var = tk.StringVar(value="—")
            self._ov_vars[key] = var
            tk.Label(parent, textvariable=var,
                     bg=COLORS["bg_card"], fg=COLORS["accent_green"],
                     font=FONTS["mono_small"], anchor="w").grid(
                row=row, column=col * 2 + 1, padx=(2, 12), pady=4, sticky="w")

    def _build_terminal(self, parent):
        hdr = tk.Frame(parent, bg=COLORS["bg_card"])
        hdr.pack(fill="x", pady=4)
        tk.Label(hdr, text="Command:",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=FONTS["small"]).pack(side="left")
        self._cmd_entry = ttk.Entry(hdr, width=50)
        self._cmd_entry.pack(side="left", padx=4)
        self._cmd_entry.bind("<Return>", self._run_command)
        ttk.Button(hdr, text="Run", command=self._run_command).pack(side="left")
        ttk.Button(hdr, text="Clear",
                   command=lambda: self._term_output.delete(1.0, "end")).pack(
            side="left", padx=4)

        self._term_output = tk.Text(
            parent,
            bg=COLORS["bg_panel"],
            fg=COLORS["accent_green"],
            insertbackground=COLORS["accent_blue"],
            font=FONTS["mono"],
            relief="flat",
            wrap="word",
            state="disabled",
        )
        sb = ttk.Scrollbar(parent, orient="vertical",
                          command=self._term_output.yview)
        self._term_output.configure(yscrollcommand=sb.set)
        self._term_output.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _build_proc_view(self, parent):
        hdr = tk.Frame(parent, bg=COLORS["bg_card"])
        hdr.pack(fill="x")
        ttk.Button(hdr, text="⟳ Refresh Processes",
                   command=self._refresh_procs).pack(side="left", padx=4, pady=4)

        cols = ("pid", "cpu", "mem", "cmd")
        self._proc_tree = ttk.Treeview(parent, columns=cols,
                                        show="headings", height=12)
        hdrs = {"pid": ("PID", 60), "cpu": ("CPU%", 70),
                "mem": ("MEM%", 70), "cmd": ("Command", 400)}
        for c, (h, w) in hdrs.items():
            self._proc_tree.heading(c, text=h)
            self._proc_tree.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(parent, orient="vertical",
                            command=self._proc_tree.yview)
        self._proc_tree.configure(yscrollcommand=vsb.set)
        self._proc_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # ── Server List ───────────────────────────────────────────────────────────
    def _load_servers(self):
        self._servers = db.get_servers()
        self._server_list.delete(0, "end")
        for s in self._servers:
            status = "●" if (s["id"] in self._clients and
                             self._clients[s["id"]].is_connected()) else "○"
            self._server_list.insert(
                "end", f"  {status}  {s['name']} ({s['host']})")

    def _selected_server(self) -> dict | None:
        sel = self._server_list.curselection()
        if not sel:
            return None
        return self._servers[sel[0]]

    def _on_server_select(self, _event=None):
        srv = self._selected_server()
        if not srv:
            return
        self._detail_placeholder.pack_forget()
        self._detail_nb.pack(fill="both", expand=True)
        self._ov_vars["host"].set(srv["host"])
        self._ov_vars["port"].set(str(srv.get("port", 22)))
        client = self._clients.get(srv["id"])
        if client and client.is_connected():
            self._ov_vars["status"].set("● Connected")
            self._refresh_overview(srv["id"])
        else:
            self._ov_vars["status"].set("○ Disconnected")

    def _connect_selected(self):
        srv = self._selected_server()
        if not srv:
            return
        def _do_connect():
            client = SSHClient(srv)
            ok = client.connect()
            if ok:
                self._clients[srv["id"]] = client
                self.after(0, self._load_servers)
                self.after(0, lambda: self._ov_vars["status"].set("● Connected"))
            else:
                self.after(0, lambda: messagebox.showerror(
                    "SSH Error",
                    f"Failed to connect to {srv['host']}:\n{client.last_error}",
                ))
        threading.Thread(target=_do_connect, daemon=True).start()

    def _disconnect_selected(self):
        srv = self._selected_server()
        if not srv:
            return
        client = self._clients.pop(srv["id"], None)
        if client:
            client.disconnect()
        self._load_servers()
        self._ov_vars["status"].set("○ Disconnected")

    def _delete_selected(self):
        srv = self._selected_server()
        if not srv:
            return
        if messagebox.askyesno("Delete", f"Delete server '{srv['name']}'?"):
            self._disconnect_selected()
            db.delete_server(srv["id"])
            self._load_servers()

    # ── Add Server Dialog ─────────────────────────────────────────────────────
    def _add_server_dialog(self):
        win = tk.Toplevel(self)
        win.title("Add Server")
        win.configure(bg=COLORS["bg_dark"])
        win.resizable(False, False)
        win.geometry("420x360")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        fields = [
            ("Name",     "name",     "My Server"),
            ("Host/IP",  "host",     "192.168.1.1"),
            ("Port",     "port",     "22"),
            ("Username", "username", "ubuntu"),
            ("Password", "password", ""),
            ("Key Path", "key_path", "~/.ssh/id_rsa"),
            ("Tags",     "tags",     "production,web"),
        ]
        entries = {}
        for i, (label, key, placeholder) in enumerate(fields):
            tk.Label(win, text=label + ":",
                     bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                     font=FONTS["body"]).grid(
                row=i, column=0, padx=16, pady=6, sticky="e")
            var = tk.StringVar(value=placeholder)
            show = "*" if key == "password" else ""
            ent = ttk.Entry(win, textvariable=var, width=30, show=show)
            ent.grid(row=i, column=1, padx=8, pady=6, sticky="w")
            entries[key] = var

        def _save():
            db.add_server(
                name=entries["name"].get(),
                host=entries["host"].get(),
                port=int(entries["port"].get() or 22),
                username=entries["username"].get(),
                password=entries["password"].get(),
                key_path=entries["key_path"].get(),
                tags=entries["tags"].get(),
            )
            win.destroy()
            self._load_servers()

        ttk.Button(win, text="Add Server", style="Accent.TButton",
                   command=_save).grid(
            row=len(fields), column=0, columnspan=2, pady=12)

    # ── Overview Refresh ──────────────────────────────────────────────────────
    def _refresh_overview(self, server_id: int):
        client = self._clients.get(server_id)
        if not client or not client.is_connected():
            return
        def _fetch():
            m = client.get_metrics()
            self.after(0, lambda: self._apply_overview(m))
        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_overview(self, m: dict):
        v = self._ov_vars
        v["kernel"].set(m.get("kernel", "—"))
        v["uptime"].set(m.get("uptime", "—"))
        v["load"].set(m.get("load_avg", "—"))
        cpu = m.get("cpu_percent")
        mem = m.get("mem_percent")
        dsk = m.get("disk_percent")
        v["cpu"].set(f"{cpu:.1f}%" if cpu is not None else "—")
        v["mem"].set(f"{mem:.1f}%" if mem is not None else "—")
        v["disk"].set(f"{dsk:.1f}%" if dsk is not None else "—")

    def _run_command(self, _event=None):
        srv = self._selected_server()
        if not srv:
            return
        client = self._clients.get(srv["id"])
        if not client or not client.is_connected():
            messagebox.showwarning("Not Connected",
                                   "Please connect to the server first.")
            return
        cmd = self._cmd_entry.get().strip()
        if not cmd:
            return
        self._cmd_entry.delete(0, "end")
        def _exec():
            out, err, rc = client.exec(cmd)
            result = f"\n$ {cmd}\n{out}"
            if err:
                result += f"\n[stderr] {err}"
            result += f"\n[exit: {rc}]\n"
            self.after(0, lambda: self._append_terminal(result))
        threading.Thread(target=_exec, daemon=True).start()

    def _append_terminal(self, text: str):
        self._term_output.configure(state="normal")
        self._term_output.insert("end", text)
        self._term_output.see("end")
        self._term_output.configure(state="disabled")

    def _refresh_procs(self):
        srv = self._selected_server()
        if not srv:
            return
        client = self._clients.get(srv["id"])
        if not client or not client.is_connected():
            return
        def _fetch():
            procs = client.get_processes()
            self.after(0, lambda: self._update_procs(procs))
        threading.Thread(target=_fetch, daemon=True).start()

    def _update_procs(self, procs):
        for item in self._proc_tree.get_children():
            self._proc_tree.delete(item)
        for p in procs:
            self._proc_tree.insert("", "end",
                values=(p["pid"], p["cpu"], p["mem"], p["cmd"]))

    # ── Background Poller ─────────────────────────────────────────────────────
    def _poll_loop(self):
        while self._running:
            for sid, client in list(self._clients.items()):
                if client.is_connected():
                    try:
                        m = client.get_metrics()
                        srv_name = client.server["name"]
                        if m.get("cpu_percent") is not None:
                            alert_engine.check(srv_name, "cpu_percent",
                                               m["cpu_percent"])
                        if m.get("mem_percent") is not None:
                            alert_engine.check(srv_name, "mem_percent",
                                               m["mem_percent"])
                        if m.get("disk_percent") is not None:
                            alert_engine.check(srv_name, "disk_percent",
                                               m["disk_percent"])
                    except Exception:
                        pass
            time.sleep(self.POLL_INTERVAL)

    def destroy(self):
        self._running = False
        for c in self._clients.values():
            c.disconnect()
        super().destroy()