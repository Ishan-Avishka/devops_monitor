"""
ssh_client.py - Paramiko-based SSH connection manager with command execution.
"""
import threading
import paramiko
import time
import socket
from typing import Optional
import database as db


class SSHClient:
    """
    Manages a single persistent SSH session.
    Thread-safe: all public methods can be called from any thread.
    """
    CONNECT_TIMEOUT = 10
    KEEPALIVE = 30

    def __init__(self, server: dict):
        self._server = server
        self._client: Optional[paramiko.SSHClient] = None
        self._lock = threading.Lock()
        self._connected = False
        self._error: str = ""

    # ── Connection ────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        with self._lock:
            try:
                self._client = paramiko.SSHClient()
                self._client.set_missing_host_key_policy(
                    paramiko.AutoAddPolicy())

                kwargs = dict(
                    hostname=self._server["host"],
                    port=int(self._server.get("port", 22)),
                    username=self._server.get("username", ""),
                    timeout=self.CONNECT_TIMEOUT,
                )
                key_path = self._server.get("key_path", "").strip()
                password = self._server.get("password", "").strip()

                if key_path:
                    kwargs["key_filename"] = key_path
                elif password:
                    kwargs["password"] = password

                self._client.connect(**kwargs)
                transport = self._client.get_transport()
                if transport:
                    transport.set_keepalive(self.KEEPALIVE)
                self._connected = True
                self._error = ""
                db.touch_server(self._server["id"])
                db.write_log("INFO", self._server["name"],
                             f"SSH connected to {self._server['host']}")
                return True
            except Exception as e:
                self._connected = False
                self._error = str(e)
                db.write_log("ERROR", self._server["name"],
                             f"SSH connect failed: {e}")
                return False

    def disconnect(self):
        with self._lock:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
            self._connected = False

    def is_connected(self) -> bool:
        if not self._connected or not self._client:
            return False
        try:
            transport = self._client.get_transport()
            return transport is not None and transport.is_active()
        except Exception:
            return False

    def reconnect(self) -> bool:
        self.disconnect()
        return self.connect()

    # ── Command Execution ─────────────────────────────────────────────────────
    def exec(self, command: str, timeout: int = 30) -> tuple[str, str, int]:
        """Execute a command; returns (stdout, stderr, exit_code)."""
        with self._lock:
            if not self.is_connected():
                return ("", "Not connected", -1)
            try:
                _, stdout, stderr = self._client.exec_command(
                    command, timeout=timeout)
                out = stdout.read().decode(errors="replace").strip()
                err = stderr.read().decode(errors="replace").strip()
                rc  = stdout.channel.recv_exit_status()
                return (out, err, rc)
            except Exception as e:
                self._connected = False
                return ("", str(e), -1)

    def exec_many(self, commands: list[str]) -> list[tuple]:
        """Execute multiple commands sequentially."""
        return [self.exec(cmd) for cmd in commands]

    # ── Remote Metrics ────────────────────────────────────────────────────────
    def get_metrics(self) -> dict:
        """
        Returns a dict of remote host metrics via shell commands.
        Works on Linux/Unix targets.
        """
        metrics = {
            "cpu_percent":  None,
            "mem_percent":  None,
            "disk_percent": None,
            "uptime":       "",
            "load_avg":     "",
            "kernel":       "",
        }
        if not self.is_connected():
            return metrics

        commands = {
            "cpu":    "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'",
            "mem":    "free | awk '/Mem/{printf \"%.1f\", $3/$2*100}'",
            "disk":   "df / | awk 'NR==2{print $5}' | tr -d '%'",
            "uptime": "uptime -p 2>/dev/null || uptime",
            "load":   "cat /proc/loadavg 2>/dev/null | cut -d' ' -f1-3",
            "kernel": "uname -r",
        }
        results = {}
        for key, cmd in commands.items():
            out, _, _ = self.exec(cmd, timeout=5)
            results[key] = out.strip()

        try:
            metrics["cpu_percent"]  = float(results.get("cpu", 0) or 0)
        except ValueError:
            pass
        try:
            metrics["mem_percent"]  = float(results.get("mem", 0) or 0)
        except ValueError:
            pass
        try:
            metrics["disk_percent"] = float(results.get("disk", 0) or 0)
        except ValueError:
            pass
        metrics["uptime"]   = results.get("uptime", "")
        metrics["load_avg"] = results.get("load",   "")
        metrics["kernel"]   = results.get("kernel", "")
        return metrics

    def get_processes(self, limit=20) -> list[dict]:
        """Return top N processes by CPU on remote host."""
        out, _, rc = self.exec(
            f"ps aux --sort=-%cpu | head -n {limit + 1} | "
            "awk 'NR>1{print $2,$3,$4,$11}'", timeout=8)
        if rc != 0:
            return []
        procs = []
        for line in out.splitlines():
            parts = line.split(None, 3)
            if len(parts) >= 4:
                procs.append({
                    "pid":  parts[0],
                    "cpu":  parts[1],
                    "mem":  parts[2],
                    "cmd":  parts[3],
                })
        return procs

    @property
    def server(self) -> dict:
        return self._server

    @property
    def last_error(self) -> str:
        return self._error