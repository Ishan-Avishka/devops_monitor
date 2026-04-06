"""
logs_viewer.py - Structured log viewer with filtering and live tail.
"""
import tkinter as tk
from tkinter import ttk, filedialog
import threading
import time
import datetime
from utils import COLORS, FONTS, make_card
import database as db


LEVEL_COLORS = {
    "INFO":    COLORS["info"],
    "WARNING": COLORS["accent_yellow"],
    "WARN":    COLORS["accent_yellow"],
    "ERROR":   COLORS["accent_red"],
    "ALERT":   COLORS["accent_orange"],
    "DEBUG":   COLORS["text_secondary"],
    "CRITICAL":COLORS["accent_red"],
}


class LogsViewer(ttk.Frame):
    REFRESH_INTERVAL = 4    # seconds between auto-refresh

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        self._live_tail  = tk.BooleanVar(value=True)
        self._last_id    = 0
        self._running    = True
        self._build_ui()
        threading.Thread(target=self._auto_refresh, daemon=True).start()

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="📋  LOG VIEWER",
                 bg=COLORS["bg_dark"], fg=COLORS["accent_purple"],
                 font=FONTS["heading"]).pack(side="left")

        # Filter bar
        filter_bar = tk.Frame(self, bg=COLORS["bg_dark"])
        filter_bar.pack(fill="x", pady=(0, 6))

        tk.Label(filter_bar, text="Level:",
                 bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                 font=FONTS["small"]).pack(side="left")
        self._level_var = tk.StringVar(value="ALL")
        level_combo = ttk.Combobox(filter_bar,
                                   textvariable=self._level_var,
                                   values=["ALL", "INFO", "WARNING",
                                           "ERROR", "ALERT", "DEBUG"],
                                   width=10, state="readonly")
        level_combo.pack(side="left", padx=(2, 12))
        level_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        tk.Label(filter_bar, text="Source:",
                 bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                 font=FONTS["small"]).pack(side="left")
        self._source_var = tk.StringVar()
        ttk.Entry(filter_bar, textvariable=self._source_var,
                  width=18).pack(side="left", padx=(2, 12))

        tk.Label(filter_bar, text="Search:",
                 bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                 font=FONTS["small"]).pack(side="left")
        self._search_var = tk.StringVar()
        ttk.Entry(filter_bar, textvariable=self._search_var,
                  width=22).pack(side="left", padx=(2, 12))

        ttk.Button(filter_bar, text="Apply",
                   command=self._refresh).pack(side="left", padx=3)
        ttk.Button(filter_bar, text="Clear Logs",
                   command=self._clear_logs).pack(side="left", padx=3)
        ttk.Button(filter_bar, text="Export",
                   command=self._export).pack(side="left", padx=3)

        ttk.Checkbutton(filter_bar, text="Live Tail",
                        variable=self._live_tail).pack(side="right", padx=6)

        # Count label
        self._count_var = tk.StringVar(value="0 entries")
        tk.Label(filter_bar, textvariable=self._count_var,
                 bg=COLORS["bg_dark"], fg=COLORS["text_muted"],
                 font=FONTS["small"]).pack(side="right", padx=8)

        # Log text (color-coded)
        log_card, log_inner = make_card(self, "")
        log_card.pack(fill="both", expand=True)

        self._log_text = tk.Text(
            log_inner,
            bg=COLORS["bg_panel"],
            fg=COLORS["text_primary"],
            font=FONTS["mono_small"],
            relief="flat",
            state="disabled",
            wrap="word",
        )
        vsb = ttk.Scrollbar(log_inner, orient="vertical",
                            command=self._log_text.yview)
        hsb = ttk.Scrollbar(log_inner, orient="horizontal",
                            command=self._log_text.xview)
        self._log_text.configure(yscrollcommand=vsb.set,
                                  xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._log_text.pack(side="left", fill="both", expand=True)

        # Configure color tags
        for level, color in LEVEL_COLORS.items():
            self._log_text.tag_configure(level, foreground=color)
        self._log_text.tag_configure("TS",
            foreground=COLORS["text_muted"])
        self._log_text.tag_configure("SOURCE",
            foreground=COLORS["accent_blue"])

        # Tree view (structured)
        tree_card, tree_inner = make_card(self, "Structured Log Table")
        tree_card.pack(fill="x", pady=(8, 0))

        cols = ("ts", "level", "source", "message")
        self._tree = ttk.Treeview(tree_inner, columns=cols,
                                   show="headings", height=6)
        hdrs = {"ts":("Timestamp",150), "level":("Level",80),
                "source":("Source",120), "message":("Message",600)}
        for c, (h, w) in hdrs.items():
            self._tree.heading(c, text=h)
            self._tree.column(c, width=w, anchor="w")
        for level, color in LEVEL_COLORS.items():
            self._tree.tag_configure(level, foreground=color)
        vsb2 = ttk.Scrollbar(tree_inner, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb2.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb2.pack(side="right", fill="y")

    # ── Data ──────────────────────────────────────────────────────────────────
    def _refresh(self):
        level  = self._level_var.get()
        source = self._source_var.get().strip() or None
        search = self._search_var.get().strip()

        logs = db.get_logs(
            limit=1000,
            level=None if level == "ALL" else level,
            source=source,
        )
        if search:
            logs = [l for l in logs
                    if search.lower() in l["message"].lower()]

        # Text widget
        self._log_text.configure(state="normal")
        self._log_text.delete(1.0, "end")
        for entry in reversed(logs):
            ts  = entry.get("ts", "")[:19]
            lvl = entry.get("level", "INFO")
            src = entry.get("source", "")
            msg = entry.get("message", "")

            self._log_text.insert("end", f"[{ts}] ", "TS")
            self._log_text.insert("end", f"{lvl:<8}", lvl)
            self._log_text.insert("end", f" {src:<16} ", "SOURCE")
            self._log_text.insert("end", f"{msg}\n", lvl)

        if self._live_tail.get():
            self._log_text.see("end")
        self._log_text.configure(state="disabled")
        self._count_var.set(f"{len(logs)} entries")

        # Tree
        for item in self._tree.get_children():
            self._tree.delete(item)
        for entry in logs[:200]:
            lvl = entry.get("level", "INFO")
            self._tree.insert("", "end", tags=(lvl,),
                values=(entry.get("ts","")[:19],
                        lvl,
                        entry.get("source",""),
                        entry.get("message","")))

    def _clear_logs(self):
        from tkinter import messagebox
        if messagebox.askyesno("Clear Logs", "Delete all logs from database?"):
            db.clear_logs()
            self._refresh()

    def _export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        logs = db.get_logs(limit=10000)
        with open(path, "w") as f:
            for entry in reversed(logs):
                f.write(f"[{entry['ts']}] {entry['level']:<8} "
                        f"{entry['source']:<16} {entry['message']}\n")

    # ── Live Tail ─────────────────────────────────────────────────────────────
    def _auto_refresh(self):
        while self._running:
            if self._live_tail.get():
                try:
                    self.after(0, self._refresh)
                except Exception as e:
                    db.safe_write_log("WARNING", "LogsViewer", f"Auto refresh failed: {e}")
            time.sleep(self.REFRESH_INTERVAL)

    def destroy(self):
        self._running = False
        super().destroy()