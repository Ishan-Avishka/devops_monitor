"""
login.py - Login screen with authentication.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from utils import COLORS, FONTS
import database as db


class LoginWindow(tk.Tk):
    """Standalone login window shown before the main dashboard."""

    def __init__(self):
        super().__init__()
        self.title("DevOps Monitor — Login")
        self.configure(bg=COLORS["bg_dark"])
        self.resizable(False, False)

        # Center on screen
        self.update_idletasks()
        w, h = 460, 520
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self._user_data = None
        self._build_ui()

    def _build_ui(self):
        outer = tk.Frame(self, bg=COLORS["bg_dark"])
        outer.pack(expand=True, fill="both")

        # ASCII/Unicode logo panel
        logo_frame = tk.Frame(outer, bg=COLORS["bg_panel"],
                               highlightbackground=COLORS["border"],
                               highlightthickness=1)
        logo_frame.pack(fill="x", padx=40, pady=(40, 0))

        tk.Label(logo_frame,
                 text="  ██████╗ ███████╗██╗   ██╗ ██████╗ ██████╗ ███████╗",
                 bg=COLORS["bg_panel"], fg=COLORS["accent_blue"],
                 font=("Courier New", 7)).pack(anchor="w")
        tk.Label(logo_frame,
                 text="  ██╔══██╗██╔════╝██║   ██║██╔═══██╗██╔══██╗██╔════╝",
                 bg=COLORS["bg_panel"], fg=COLORS["accent_blue"],
                 font=("Courier New", 7)).pack(anchor="w")
        tk.Label(logo_frame,
                 text="  ██║  ██║█████╗  ╚██╗ ██╔╝██║   ██║██████╔╝███████╗",
                 bg=COLORS["bg_panel"], fg=COLORS["accent_blue"],
                 font=("Courier New", 7)).pack(anchor="w")
        tk.Label(logo_frame,
                 text="  ██║  ██║██╔══╝   ╚████╔╝ ██║   ██║██╔═══╝ ╚════██║",
                 bg=COLORS["bg_panel"], fg=COLORS["text_secondary"],
                 font=("Courier New", 7)).pack(anchor="w")
        tk.Label(logo_frame,
                 text="  ██████╔╝███████╗  ╚██╔╝  ╚██████╔╝██║     ███████║",
                 bg=COLORS["bg_panel"], fg=COLORS["text_secondary"],
                 font=("Courier New", 7)).pack(anchor="w")
        tk.Label(logo_frame,
                 text="  ╚═════╝ ╚══════╝   ╚═╝    ╚═════╝ ╚═╝     ╚══════╝",
                 bg=COLORS["bg_panel"], fg=COLORS["text_muted"],
                 font=("Courier New", 7)).pack(anchor="w", pady=(0, 6))

        tk.Label(logo_frame,
                 text="  MONITORING DASHBOARD  v1.0.0",
                 bg=COLORS["bg_panel"], fg=COLORS["accent_orange"],
                 font=("Courier New", 9, "bold")).pack(anchor="w", pady=(0, 8))

        # Form
        form = tk.Frame(outer, bg=COLORS["bg_dark"])
        form.pack(padx=40, pady=20, fill="x")

        for label, attr, show in [
            ("USERNAME", "_user_entry", ""),
            ("PASSWORD", "_pass_entry", "●"),
        ]:
            tk.Label(form, text=label,
                     bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                     font=("Courier New", 8, "bold"),
                     anchor="w").pack(fill="x", pady=(10, 2))
            ent = ttk.Entry(form, show=show, font=FONTS["mono"])
            ent.pack(fill="x", ipady=6)
            setattr(self, attr, ent)

        self._user_entry.insert(0, "admin")

        # Status label
        self._status_var = tk.StringVar()
        tk.Label(form, textvariable=self._status_var,
                 bg=COLORS["bg_dark"], fg=COLORS["accent_red"],
                 font=FONTS["small"]).pack(pady=4)

        # Login button
        self._login_btn = ttk.Button(form,
                                      text="▶  LOGIN",
                                      style="Accent.TButton",
                                      command=self._attempt_login)
        self._login_btn.pack(fill="x", ipady=6, pady=(4, 0))

        # Bindings
        self._pass_entry.bind("<Return>", lambda _: self._attempt_login())
        self._user_entry.bind("<Return>", lambda _: self._pass_entry.focus())
        self._pass_entry.focus()

        # Footer
        tk.Label(outer,
                 text="Default credentials: admin / admin123",
                 bg=COLORS["bg_dark"], fg=COLORS["text_muted"],
                 font=FONTS["label"]).pack(pady=6)

    def _attempt_login(self):
        username = self._user_entry.get().strip()
        password = self._pass_entry.get()

        if not username or not password:
            self._status_var.set("Username and password required.")
            return

        self._login_btn.configure(state="disabled", text="Authenticating...")
        self.update()

        def _auth():
            user, err = db.authenticate_user(username, password)
            self.after(0, lambda: self._on_auth_result(user, err))

        threading.Thread(target=_auth, daemon=True).start()

    def _on_auth_result(self, user, err_msg=None):
        self._login_btn.configure(state="normal", text="▶  LOGIN")
        if user:
            self._user_data = user
            db.write_log("INFO", "auth",
                         f"Login: {user['username']} ({user['role']})")
            self.destroy()
        else:
            self._status_var.set(err_msg or "Invalid credentials. Try again.")
            self._pass_entry.delete(0, "end")
            self._pass_entry.focus()

    def get_user(self) -> dict | None:
        return self._user_data