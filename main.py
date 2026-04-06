"""
main.py - Entry point for DevOps Monitoring Dashboard.

Usage:
    python main.py
    python -m devops_monitor.main
"""
import sys
import os

# Ensure the package directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import messagebox


def main():
    # ── 1. Initialize database ─────────────────────────────────────────────
    try:
        import database as db
        db.init_db()
        db.write_log("INFO", "startup", "DevOps Monitor starting up")
    except Exception as e:
        messagebox.showerror("DB Error", f"Failed to initialize database:\n{e}")
        sys.exit(1)

    # ── 2. Prepare theme helper ──────────────────────────────────────────────
    from utils import apply_theme

    # ── 3. Show Login ──────────────────────────────────────────────────────
    from login import LoginWindow
    login = LoginWindow()
    apply_theme(login)
    login.mainloop()

    user = login.get_user()

    if not user:
        # User closed the login window without authenticating
        sys.exit(0)

    # ── 4. Launch Dashboard ────────────────────────────────────────────────
    try:
        from dashboard import Dashboard
        app = Dashboard(user)
        app.mainloop()
        db.write_log("INFO", "shutdown", "DevOps Monitor shut down cleanly")
    except Exception as e:
        db.write_log("ERROR", "startup", f"Dashboard launch failed: {e}")
        messagebox.showerror("Startup Error", f"Failed to launch dashboard:\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()