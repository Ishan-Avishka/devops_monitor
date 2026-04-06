# ⬡ DevOps Monitoring Dashboard

An industrial-grade desktop DevOps monitoring tool built with Python & Tkinter.
Monitors local system resources, remote servers via SSH, and Docker containers — all in a dark terminal-inspired UI.

---

## 📁 File Structure

```
devops_monitor/
├── main.py              ← Entry point: initializes DB, shows login, launches dashboard
├── login.py             ← Login screen with credential verification
├── dashboard.py         ← Main window: sidebar navigation, overview panel, status bar
├── cpu_monitor.py       ← CPU usage, per-core bars, live line chart, gauges
├── memory_monitor.py    ← RAM & Swap monitoring, top processes, live chart
├── disk_monitor.py      ← Partitions table, I/O chart, horizontal bar chart
├── network_monitor.py   ← Interface stats, connections table, live I/O chart
├── server_manager.py    ← Remote server CRUD, SSH connect/disconnect, terminal tab
├── ssh_client.py        ← Paramiko SSH wrapper: connect, exec, get_metrics()
├── docker_monitor.py    ← Container list, start/stop/restart, log viewer
├── alerts.py            ← Alert engine (rule evaluation), AlertsPanel, toast notifications
├── logs_viewer.py       ← Structured log viewer with filtering, live tail, export
├── charts.py            ← Reusable Matplotlib widgets: LiveLineChart, GaugeChart, etc.
├── database.py          ← SQLite layer: users, servers, alerts, settings, logs
├── settings.py          ← Settings panel: thresholds, user management, preferences
├── utils.py             ← Color palette, fonts, ttk theme, shared helpers
├── requirements.txt     ← Python package dependencies
└── setup.py             ← Package setup for pip installation
```

---

## 🛠 Setup Instructions

### Prerequisites

- **Python 3.9+** (Python 3.11+ recommended)
- **pip** package manager
- **Docker** (optional — only needed for Docker monitoring)
- **SSH targets** (optional — only needed for remote server monitoring)

---

### Step 1 — Clone / Download

```bash
git clone https://github.com/your-org/devops-monitor.git
cd devops-monitor
```

Or simply place all files in a folder called `devops_monitor/`.

---

### Step 2 — Create a Virtual Environment (Recommended)

```bash
# Create venv
python -m venv venv

# Activate (Linux / macOS)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

---

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

#### Full dependency list (`requirements.txt`):

| Package        | Version   | Purpose                              |
|----------------|-----------|--------------------------------------|
| `psutil`       | ≥ 5.9.8   | CPU, RAM, Disk, Network, Process data|
| `matplotlib`   | ≥ 3.8.4   | Live line charts, gauges, bar charts |
| `paramiko`     | ≥ 3.4.0   | SSH connections to remote servers    |
| `docker`       | ≥ 7.0.0   | Docker container monitoring via API  |
| `Pillow`       | ≥ 10.3.0  | Image support (icons, screenshots)   |
| `requests`     | ≥ 2.31.0  | HTTP health checks                   |
| `cryptography` | ≥ 42.0.5  | Required by paramiko                 |
| `bcrypt`       | ≥ 4.1.3   | Password hashing (login system)      |

> **Note:** `tkinter` and `sqlite3` are part of the Python standard library.
> On some Linux systems you may need: `sudo apt install python3-tk`

---

### Step 4 — Run the Application

```bash
cd devops_monitor
python main.py
```

#### Default login credentials:
```
Username: admin
Password: admin123
```

> Change these immediately in **Settings → User Management** after first login.

---

### Step 5 (Optional) — Install as a Package

```bash
cd devops_monitor
pip install -e .

# Then run from anywhere:
devops-monitor
```

---

## 🚀 Features Overview

### ◈ Overview Panel
- Live summary cards: CPU %, RAM %, Disk %, Network speeds, Process count, Uptime, Load Average
- Per-core mini progress bars
- Memory breakdown (Used / Free / Swap)
- Recent alert feed

### ⚡ CPU Monitor
- Overall CPU gauge (semi-circular)
- 60-second live history line chart
- Per-core usage bars (color-coded: green/yellow/red)
- System info: model, core counts, frequency, uptime, user/system/idle split

### 🧠 Memory Monitor
- RAM & Swap gauges
- Detailed breakdown: Total, Used, Free, Available, Cached, Buffers
- 60-second live dual-series chart (RAM % + Swap %)
- Top processes table by RSS memory

### 💾 Disk Monitor
- All mounted partitions: device, mount, FS type, total/used/free/usage%
- Color-coded partition table (yellow ≥75%, red ≥90%)
- Horizontal bar chart of partition usage
- Disk I/O chart (read/write bytes/s)
- Total read/write counters

### 🌐 Network Monitor
- Per-second download/upload speed cards
- Total bytes/packets/errors
- 60-second dual-series network I/O chart
- Network interfaces table (IP, MAC, speed, status)
- Active TCP connections table

### 🐳 Docker Monitor
- Container grid: ID, name, image, status, ports, CPU%, memory
- Summary cards: Running, Stopped, Paused, Total containers, Images
- Start / Stop / Restart containers
- View container logs (last 200 lines)
- Live log tail via combo selector

### 🖥 Server Manager
- Add/edit/delete remote servers with SSH credentials or key file
- Connect/disconnect per server
- Overview tab: live remote metrics (CPU, RAM, Disk, Kernel, Load)
- Terminal tab: run arbitrary shell commands over SSH
- Process tab: list top processes on remote host
- Background polling fires alerts for remote servers

### ⚠ Alert Manager
- Rule-based alert engine with configurable thresholds
- Default rules: CPU (85%/95%), RAM (80%/95%), Disk (85%/95%)
- Alert deduplication (60s cooldown per rule per server)
- Severity levels: warning / critical
- Acknowledge individual or all alerts
- Desktop toast notifications (bottom-right corner)

### 📋 Log Viewer
- Color-coded structured log display (INFO/WARNING/ERROR/ALERT/DEBUG)
- Filter by level, source, or free-text search
- Live tail mode (auto-refresh every 4s)
- Export to .txt file
- Structured table view (same data, row-by-row)
- Clear all logs

### ⚙ Settings
- Refresh interval, history buffer length
- Per-metric alert thresholds (with live sliders)
- Enable/disable Docker monitoring and notifications
- User management: add/delete users with role assignment (admin/operator/viewer)

---

## 🏗 Architecture Notes

```
main.py
  └─ db.init_db()         ← Creates ~/.devops_monitor/devops.db
  └─ LoginWindow          ← Tkinter Toplevel with credential check
  └─ Dashboard            ← Main Tk root window
        ├─ Topbar         ← Clock, alert badge, user info
        ├─ Sidebar        ← Navigation buttons + mini stats
        ├─ Main Frame     ← Scrollable panel host
        └─ Statusbar      ← Live CPU/RAM/Net/alert strip

AlertEngine (singleton)
  └─ check(server, metric, value)   ← Called from any monitor
  └─ notifies observers             ← Dashboard toast, AlertsPanel refresh

Database (SQLite at ~/.devops_monitor/devops.db)
  └─ users, servers, alerts, alert_rules, settings, logs
```

---

## 🐧 Linux / macOS Notes

```bash
# If tkinter is missing:
sudo apt install python3-tk          # Debian/Ubuntu
sudo dnf install python3-tkinter     # Fedora
brew install python-tk               # macOS (Homebrew)

# If Docker SDK has permission errors:
sudo usermod -aG docker $USER
# then log out and back in
```

## 🪟 Windows Notes

- Python 3.9+ includes tkinter by default
- Make sure Docker Desktop is running for Docker monitoring
- For SSH key auth, use standard OpenSSH key paths (e.g., `C:\Users\you\.ssh\id_rsa`)

---

## 📦 Package Versions Tested

| OS                | Python | Status |
|-------------------|--------|--------|
| Ubuntu 22.04 LTS  | 3.11   | ✅     |
| macOS 14 (M2)     | 3.12   | ✅     |
| Windows 11        | 3.11   | ✅     |
| Debian 12         | 3.11   | ✅     |

---

## 🔐 Security Notes

- Passwords are stored as SHA-256 hashes in the local SQLite database
- SSH passwords/keys are stored in plaintext in the local DB — use key-based auth where possible
- The database lives at `~/.devops_monitor/devops.db` (user-private path)
- This tool is intended for trusted local/internal network use

---

## 📜 License

MIT — free to use, modify, and distribute.