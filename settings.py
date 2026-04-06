"""
settings.py - Application settings panel.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import importlib.util
from utils import COLORS, FONTS, make_card
import database as db


class SettingsPanel(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        tk.Label(self, text="⚙  SETTINGS",
                 bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                 font=FONTS["heading"]).pack(anchor="w", pady=(0, 12))

        # General card
        gen_card, gen_inner = make_card(self, "General")
        gen_card.pack(fill="x", pady=(0, 10))

        self._setting_vars = {}
        self._build_setting_row(gen_inner, "refresh_interval",
                                "Refresh Interval (s)", "3", "int",
                                range_=(1, 60))
        self._build_setting_row(gen_inner, "history_length",
                                "History Length (points)", "60", "int",
                                range_=(10, 300))
        self._build_setting_row(gen_inner, "log_level",
                                "Log Level", "INFO", "combo",
                                choices=["DEBUG","INFO","WARNING","ERROR"])
        self._build_setting_row(gen_inner, "docker_enabled",
                                "Enable Docker Monitor", "1", "bool")
        self._build_setting_row(gen_inner, "notifications",
                                "Desktop Notifications", "1", "bool")

        # Alert thresholds card
        alert_card, alert_inner = make_card(self, "Alert Thresholds")
        alert_card.pack(fill="x", pady=(0, 10))
        self._build_setting_row(alert_inner, "cpu_warn_threshold",
                                "CPU Warning %", "85", "int")
        self._build_setting_row(alert_inner, "cpu_crit_threshold",
                                "CPU Critical %", "95", "int")
        self._build_setting_row(alert_inner, "mem_warn_threshold",
                                "RAM Warning %", "80", "int")
        self._build_setting_row(alert_inner, "mem_crit_threshold",
                                "RAM Critical %", "95", "int")
        self._build_setting_row(alert_inner, "disk_warn_threshold",
                                "Disk Warning %", "85", "int")
        self._build_setting_row(alert_inner, "disk_crit_threshold",
                                "Disk Critical %", "95", "int")

        # User management card
        user_card, user_inner = make_card(self, "User Management")
        user_card.pack(fill="x", pady=(0, 10))
        self._user_tree = self._build_user_tree(user_inner)
        user_btns = tk.Frame(user_inner, bg=COLORS["bg_card"])
        user_btns.pack(fill="x", pady=6)
        ttk.Button(user_btns, text="Add User",
                   command=self._add_user_dialog).pack(side="left", padx=3)
        ttk.Button(user_btns, text="Delete Selected",
                   command=self._delete_user).pack(side="left", padx=3)
        ttk.Button(user_btns, text="Refresh",
                   command=self._load_users).pack(side="left", padx=3)

        # Diagnostics card
        diag_card, diag_inner = make_card(self, "Diagnostics")
        diag_card.pack(fill="x", pady=(0, 10))
        diag_btns = tk.Frame(diag_inner, bg=COLORS["bg_card"])
        diag_btns.pack(fill="x", pady=(0, 4))
        ttk.Button(diag_btns, text="Refresh Diagnostics",
                   command=self._refresh_diagnostics).pack(side="left")
        self._diag_text = tk.Text(
            diag_inner,
            bg=COLORS["bg_panel"],
            fg=COLORS["text_primary"],
            font=FONTS["mono_small"],
            relief="flat",
            height=8,
            wrap="word",
            state="disabled",
        )
        self._diag_text.pack(fill="x")

        # Save button
        save_row = tk.Frame(self, bg=COLORS["bg_dark"])
        save_row.pack(fill="x", pady=10)
        ttk.Button(save_row, text="💾  Save All Settings",
                   style="Accent.TButton",
                   command=self._save_settings).pack(side="left")
        ttk.Button(save_row, text="Reset to Defaults",
                   command=self._reset_defaults).pack(side="left", padx=8)

    def _build_setting_row(self, parent, key, label, default,
                            widget_type, range_=None, choices=None):
        row = tk.Frame(parent, bg=COLORS["bg_card"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label + ":",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=FONTS["small"], width=26, anchor="e").pack(
            side="left", padx=(4, 8))

        var: tk.Variable
        if widget_type == "int":
            var = tk.IntVar(value=int(default))
        else:
            var = tk.StringVar(value=default)
        self._setting_vars[key] = var

        if widget_type == "bool":
            ttk.Checkbutton(row, variable=var,
                            onvalue="1", offvalue="0").pack(side="left")
        elif widget_type == "combo" and choices:
            ttk.Combobox(row, textvariable=var, values=choices,
                         width=14, state="readonly").pack(side="left")
        elif widget_type == "int" and range_:
            ttk.Scale(row, variable=var,
                      from_=range_[0], to=range_[1],
                      orient="horizontal", length=160).pack(side="left")
            tk.Label(row, textvariable=var,
                     bg=COLORS["bg_card"], fg=COLORS["accent_green"],
                     font=FONTS["mono_small"], width=5).pack(side="left", padx=4)
        else:
            ttk.Entry(row, textvariable=var, width=20).pack(side="left")

    def _build_user_tree(self, parent) -> ttk.Treeview:
        cols = ("id", "username", "role", "created")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=4)
        hdrs = {"id":("ID",40), "username":("Username",140),
                "role":("Role",80), "created":("Created",180)}
        for c, (h, w) in hdrs.items():
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w")
        tree.pack(fill="x")
        return tree

    def _load_settings(self):
        current = db.get_all_settings()
        for key, var in self._setting_vars.items():
            if key in current:
                if isinstance(var, tk.IntVar):
                    try:
                        var.set(int(float(current[key])))
                    except ValueError:
                        pass
                else:
                    var.set(current[key])
        self._load_users()
        self._refresh_diagnostics()

    def _load_users(self):
        for item in self._user_tree.get_children():
            self._user_tree.delete(item)
        for u in db.get_users():
            self._user_tree.insert("", "end",
                values=(u["id"], u["username"],
                        u["role"], u.get("created","")[:19]))

    def _save_settings(self):
        for key, var in self._setting_vars.items():
            db.set_setting(key, var.get())
        messagebox.showinfo("Settings", "Settings saved successfully.")

    def _reset_defaults(self):
        defaults = {
            "refresh_interval": "3",
            "history_length":   "60",
            "notifications":    "1",
            "log_level":        "INFO",
            "docker_enabled":   "1",
            "cpu_warn_threshold": "85",
            "cpu_crit_threshold": "95",
            "mem_warn_threshold": "80",
            "mem_crit_threshold": "95",
            "disk_warn_threshold":"85",
            "disk_crit_threshold":"95",
        }
        for key, val in defaults.items():
            if key in self._setting_vars:
                self._setting_vars[key].set(val)
            db.set_setting(key, val)
        messagebox.showinfo("Settings", "Defaults restored.")

    def _add_user_dialog(self):
        win = tk.Toplevel(self)
        win.title("Add User")
        win.configure(bg=COLORS["bg_dark"])
        win.geometry("300x200")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        fields = {"Username": tk.StringVar(),
                  "Password": tk.StringVar(),
                  "Role":     tk.StringVar(value="viewer")}
        for i, (label, var) in enumerate(fields.items()):
            tk.Label(win, text=label + ":",
                     bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                     font=FONTS["body"]).grid(row=i, column=0, padx=14, pady=8, sticky="e")
            show = "*" if label == "Password" else ""
            if label == "Role":
                ttk.Combobox(win, textvariable=var,
                             values=["admin","viewer","operator"],
                             width=18, state="readonly").grid(
                    row=i, column=1, padx=6, pady=8)
            else:
                ttk.Entry(win, textvariable=var, width=20, show=show).grid(
                    row=i, column=1, padx=6, pady=8)

        def _save():
            u = fields["Username"].get().strip()
            p = fields["Password"].get()
            r = fields["Role"].get()
            if not u or not p:
                messagebox.showwarning("Validation", "Username and password required.")
                return
            db.add_user(u, p, r)
            win.destroy()
            self._load_users()

        ttk.Button(win, text="Create User", style="Accent.TButton",
                   command=_save).grid(row=3, column=0, columnspan=2, pady=10)

    def _delete_user(self):
        sel = self._user_tree.selection()
        if not sel:
            return
        uid = self._user_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Delete", "Delete this user?"):
            db.delete_user(uid)
            self._load_users()

    def _refresh_diagnostics(self):
        lines = [
            f"DB path: {db.DB_PATH}",
            f"Docker SDK: {'available' if importlib.util.find_spec('docker') else 'missing'}",
            f"Paramiko SSH: {'available' if importlib.util.find_spec('paramiko') else 'missing'}",
            "Recent errors:",
        ]
        errors = db.get_last_error_logs(limit=5)
        if not errors:
            lines.append("  (none)")
        else:
            for item in errors:
                lines.append(
                    f"  [{item['ts'][:19]}] {item['source']}: {item['message'][:90]}"
                )

        self._diag_text.configure(state="normal")
        self._diag_text.delete(1.0, "end")
        self._diag_text.insert("end", "\n".join(lines))
        self._diag_text.configure(state="disabled")