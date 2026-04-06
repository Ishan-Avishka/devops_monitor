"""database.py - SQLite persistence layer for servers, alerts, settings, users, and logs."""
import datetime
import hashlib
import sqlite3
from typing import Any, Optional
from pathlib import Path

import bcrypt
from cryptography.fernet import Fernet, InvalidToken


APP_DIR = Path.home() / ".devops_monitor"
DB_PATH = APP_DIR / "devops.db"
SECRET_KEY_PATH = APP_DIR / "secret.key"
LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW_MINUTES = 10


def _get_conn() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _get_or_create_secret_key() -> bytes:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    SECRET_KEY_PATH.write_bytes(key)
    SECRET_KEY_PATH.chmod(0o600)
    return key


def _get_cipher() -> Fernet:
    return Fernet(_get_or_create_secret_key())


def _encrypt_secret(value: str) -> str:
    if not value:
        return ""
    if value.startswith("enc:"):
        return value
    token = _get_cipher().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"enc:{token}"


def _decrypt_secret(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("enc:"):
        return value
    token = value[4:]
    try:
        return _get_cipher().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Keep original if we cannot decrypt (e.g., key rotation mismatch).
        return value


def _is_legacy_sha256(hash_value: str) -> bool:
    if not hash_value or len(hash_value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in hash_value.lower())


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    if _is_legacy_sha256(stored_hash):
        return hashlib.sha256(password.encode()).hexdigest() == stored_hash
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        return False


def _rows_to_dicts(rows):
    return [dict(r) for r in rows]


def _parse_iso_datetime(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def _lockout_state(cur: sqlite3.Cursor, username: str) -> tuple[bool, int]:
    cur.execute(
        "SELECT failed_count, locked_until FROM auth_failures WHERE username=?",
        (username,),
    )
    row = cur.fetchone()
    if not row:
        return (False, 0)
    locked_until = _parse_iso_datetime(row["locked_until"])
    if not locked_until:
        return (False, 0)
    delta = int((locked_until - datetime.datetime.now()).total_seconds())
    return (delta > 0, max(delta, 0))


def _record_failed_login(cur: sqlite3.Cursor, username: str):
    now = datetime.datetime.now()
    cur.execute(
        "SELECT failed_count FROM auth_failures WHERE username=?",
        (username,),
    )
    row = cur.fetchone()
    failed_count = int(row["failed_count"]) + 1 if row else 1
    lock_until = None
    if failed_count >= LOCKOUT_THRESHOLD:
        lock_until = (now + datetime.timedelta(minutes=LOCKOUT_WINDOW_MINUTES)).isoformat()
    cur.execute(
        """
        INSERT INTO auth_failures (username, failed_count, last_failed, locked_until)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(username)
        DO UPDATE SET
            failed_count=excluded.failed_count,
            last_failed=excluded.last_failed,
            locked_until=excluded.locked_until
        """,
        (username, failed_count, now.isoformat(), lock_until),
    )


def _clear_failed_login(cur: sqlite3.Cursor, username: str):
    cur.execute("DELETE FROM auth_failures WHERE username=?", (username,))


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
        CREATE TABLE IF NOT EXISTS auth_failures (
            username TEXT PRIMARY KEY,
            failed_count INTEGER DEFAULT 0,
            last_failed TEXT,
            locked_until TEXT
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
    pw_hash = _hash_password("admin123")
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ack_ts ON alerts(acknowledged, ts)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rules_metric_enabled ON alert_rules(metric, enabled)")

    # Migrate legacy plaintext server secrets to encrypted form.
    cur.execute("SELECT id, password, key_path FROM servers")
    for row in cur.fetchall():
        enc_pwd = _encrypt_secret(row["password"] or "")
        enc_key = _encrypt_secret(row["key_path"] or "")
        cur.execute(
            "UPDATE servers SET password=?, key_path=? WHERE id=?",
            (enc_pwd, enc_key, row["id"]),
        )

    conn.commit()
    cur.close()
    conn.close()
    print(f"[DB] SQLite database initialized at {DB_PATH}")


# ─── USERS ────────────────────────────────────────────────────────────────────
def verify_user(username: str, password: str) -> dict | None:
    user, _ = authenticate_user(username, password)
    return user


def authenticate_user(username: str, password: str) -> tuple[dict | None, str | None]:
    conn = _get_conn()
    cur = conn.cursor()
    locked, seconds_left = _lockout_state(cur, username)
    if locked:
        cur.close()
        conn.close()
        return (None, f"Account locked. Try again in {seconds_left}s.")

    cur.execute("SELECT * FROM users WHERE username=?", (username,))
    row = cur.fetchone()

    if not row or not _verify_password(password, row["password"]):
        _record_failed_login(cur, username)
        conn.commit()
        locked_now, remaining = _lockout_state(cur, username)
        cur.close()
        conn.close()
        if locked_now:
            return (None, f"Too many attempts. Locked for {remaining}s.")
        return (None, "Invalid credentials. Try again.")

    if _is_legacy_sha256(row["password"]):
        cur.execute(
            "UPDATE users SET password=? WHERE id=?",
            (_hash_password(password), row["id"]),
        )
    _clear_failed_login(cur, username)
    conn.commit()

    cur.close()
    conn.close()
    return (dict(row), None)


def get_users() -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, created FROM users")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return _rows_to_dicts(rows)


def add_user(username: str, password: str, role: str = "viewer"):
    pw_hash = _hash_password(password)
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
    pw_hash = _hash_password(new_password)
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
    servers = _rows_to_dicts(rows)
    for srv in servers:
        srv["password"] = _decrypt_secret(srv.get("password", ""))
        srv["key_path"] = _decrypt_secret(srv.get("key_path", ""))
    return servers


def add_server(name, host, port=22, username="",
               password="", key_path="", tags=""):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO servers (name, host, port, username, password, key_path, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        host,
        port,
        username,
        _encrypt_secret(password),
        _encrypt_secret(key_path),
        tags,
    ))
    conn.commit()
    cur.close()
    conn.close()


def update_server(server_id: int, **kwargs):
    if not kwargs:
        return
    if "password" in kwargs:
        kwargs["password"] = _encrypt_secret(kwargs["password"] or "")
    if "key_path" in kwargs:
        kwargs["key_path"] = _encrypt_secret(kwargs["key_path"] or "")

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


def get_active_alert_count() -> int:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM alerts WHERE acknowledged=0")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return int(row["n"] if row else 0)


def get_last_error_logs(limit: int = 20) -> list[dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ts, level, source, message FROM logs WHERE level='ERROR' ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
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


def safe_write_log(level: str, source: str, message: str):
    try:
        write_log(level, source, message)
    except Exception:
        print(f"[{level}] {source}: {message}")


def get_logs(limit: int = 500, level: Optional[str] = None,
             source: Optional[str] = None) -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    query = "SELECT * FROM logs"
    params: list[object] = []
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