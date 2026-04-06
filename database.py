"""database.py - SQLite persistence layer for servers, alerts, settings, users, and logs."""
import datetime
import hashlib
import sqlite3
from pathlib import Path


APP_DIR = Path.home() / ".devops_monitor"
DB_PATH = APP_DIR / "devops.db"


def _get_conn() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_dicts(rows):
    return [dict(r) for r in rows]


# ─── INIT DATABASE ─────────────────────────────────────────────────────────────
def init_db():
    """Create all tables and seed default data."""
    conn = _get_conn()
    cur = conn.cursor()

    tables = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'viewer',
            created TEXT
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER DEFAULT 22,
            username TEXT,
            password TEXT,
            key_path TEXT,
            tags TEXT,
            enabled INTEGER DEFAULT 1,
            last_seen TEXT
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server TEXT,
            metric TEXT,
            value REAL,
            threshold REAL,
            severity TEXT,
            message TEXT,
            ts TEXT,
            acknowledged INTEGER DEFAULT 0
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            metric TEXT,
            threshold REAL,
            operator TEXT DEFAULT '>',
            severity TEXT DEFAULT 'warning',
            enabled INTEGER DEFAULT 1,
            UNIQUE(name, metric, severity)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            level TEXT,
            source TEXT,
            message TEXT
        )
        """,
    ]

    for sql in tables:
        cur.execute(sql)

    # ── Seed admin user (password: admin123) ──────────────────────────────────
    pw_hash = hashlib.sha256("admin123".encode()).hexdigest()
    cur.execute(
        """
        INSERT OR IGNORE INTO users (username, password, role, created)
        VALUES (?, ?, ?, ?)
        """,
        ("admin", pw_hash, "admin", datetime.datetime.now().isoformat()),
    )

    # ── Seed default alert rules ───────────────────────────────────────────────
    default_rules = [
        ("High CPU",      "cpu_percent",  85.0, ">", "warning"),
        ("Critical CPU",  "cpu_percent",  95.0, ">", "critical"),
        ("High RAM",      "mem_percent",  80.0, ">", "warning"),
        ("Critical RAM",  "mem_percent",  95.0, ">", "critical"),
        ("High Disk",     "disk_percent", 85.0, ">", "warning"),
        ("Critical Disk", "disk_percent", 95.0, ">", "critical"),
    ]
    for name, metric, thr, op, sev in default_rules:
        cur.execute(
            """
            INSERT OR IGNORE INTO alert_rules
            (name, metric, threshold, operator, severity)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, metric, thr, op, sev),
        )

    # ── Seed default settings ─────────────────────────────────────────────────
    defaults = {
        "refresh_interval":   "3",
        "history_length":     "60",
        "notifications":      "1",
        "log_level":          "INFO",
        "theme":              "dark",
        "docker_enabled":     "1",
        "cpu_warn_threshold": "85",
        "cpu_crit_threshold": "95",
        "mem_warn_threshold": "80",
        "mem_crit_threshold": "95",
        "disk_warn_threshold":"85",
        "disk_crit_threshold":"95",
    }
    for k, v in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (k, v),
        )

    cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_source ON logs(source)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts)")

    conn.commit()
    cur.close()
    conn.close()
    print(f"[DB] SQLite database initialized at {DB_PATH}")


# ─── USERS ────────────────────────────────────────────────────────────────────
def verify_user(username: str, password: str) -> dict | None:
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (username, pw_hash)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def get_users() -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, created FROM users")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return _rows_to_dicts(rows)


def add_user(username: str, password: str, role: str = "viewer"):
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password, role, created) VALUES (?, ?, ?, ?)",
        (username, pw_hash, role, datetime.datetime.now().isoformat())
    )
    conn.commit()
    cur.close()
    conn.close()


def delete_user(user_id: int):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    cur.close()
    conn.close()


def update_user_password(username: str, new_password: str):
    pw_hash = hashlib.sha256(new_password.encode()).hexdigest()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET password=? WHERE username=?",
        (pw_hash, username)
    )
    conn.commit()
    cur.close()
    conn.close()


# ─── SERVERS ──────────────────────────────────────────────────────────────────
def get_servers() -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM servers WHERE enabled=1")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return _rows_to_dicts(rows)


def add_server(name, host, port=22, username="",
               password="", key_path="", tags=""):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO servers (name, host, port, username, password, key_path, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, host, port, username, password, key_path, tags))
    conn.commit()
    cur.close()
    conn.close()


def update_server(server_id: int, **kwargs):
    if not kwargs:
        return
    conn = _get_conn()
    cur = conn.cursor()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    cur.execute(
        f"UPDATE servers SET {sets} WHERE id=?",
        (*kwargs.values(), server_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def delete_server(server_id: int):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM servers WHERE id=?", (server_id,))
    conn.commit()
    cur.close()
    conn.close()


def touch_server(server_id: int):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE servers SET last_seen=? WHERE id=?",
        (datetime.datetime.now().isoformat(), server_id)
    )
    conn.commit()
    cur.close()
    conn.close()


# ─── ALERTS ───────────────────────────────────────────────────────────────────
def add_alert(server: str, metric: str, value: float,
              threshold: float, severity: str, message: str):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO alerts (server, metric, value, threshold, severity, message, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (server, metric, value, threshold, severity, message,
          datetime.datetime.now().isoformat()))
    conn.commit()
    cur.close()
    conn.close()


def get_alerts(limit: int = 200, acknowledged: bool = False) -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    ack  = 1 if acknowledged else 0
    cur.execute("""
        SELECT * FROM alerts
        WHERE acknowledged=?
        ORDER BY ts DESC
        LIMIT ?
    """, (ack, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return _rows_to_dicts(rows)


def acknowledge_alert(alert_id: int):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (alert_id,))
    conn.commit()
    cur.close()
    conn.close()


def acknowledge_all_alerts():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE alerts SET acknowledged=1")
    conn.commit()
    cur.close()
    conn.close()


def get_alert_rules() -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alert_rules WHERE enabled=1")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return _rows_to_dicts(rows)


# ─── SETTINGS ─────────────────────────────────────────────────────────────────
def get_setting(key: str, default=None):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, str(value)))
    conn.commit()
    cur.close()
    conn.close()


def get_all_settings() -> dict:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ─── LOGS ─────────────────────────────────────────────────────────────────────
def write_log(level: str, source: str, message: str):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO logs (ts, level, source, message)
        VALUES (?, ?, ?, ?)
    """, (datetime.datetime.now().isoformat(), level, source, message))
    conn.commit()
    cur.close()
    conn.close()


def get_logs(limit: int = 500, level: str = None,
             source: str = None) -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    query = "SELECT * FROM logs"
    params = []
    conditions = []

    if level:
        conditions.append("level=?")
        params.append(level)
    if source:
        conditions.append("source LIKE ?")
        params.append(f"%{source}%")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return _rows_to_dicts(rows)


def clear_logs():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM logs")
    conn.commit()
    cur.close()
    conn.close()