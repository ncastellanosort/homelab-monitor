# ESP32 Proxmox Monitor

[![GitHub release](https://img.shields.io/github/v/release/ncastellanosort/homelab-monitor?style=flat-square)](https://github.com/ncastellanosort/homelab-monitor/releases)

Proxmox VE availability monitor running on an ESP32 with MicroPython. Periodically checks if the server responds via HTTPS, sends Telegram alerts when it goes down, and serves a live HTTP dashboard on port 80.

## Features

- Wi‑Fi connection with automatic reconnection and cold-boot retries (3 attempts)
- HTTPS health checks ignoring SSL certificate validation (works with self‑signed certs)
- **HTTP dashboard** on port 80 — real-time status, accessible from any device on the LAN
- Configurable failure threshold before triggering an alert
- 10‑minute cooldown after each alert to avoid notification spam
- Telegram notification on boot (device online, dashboard URL)
- Telegram recovery notification when Proxmox comes back online after an outage
- Zero external dependencies — uses only MicroPython standard library (`socket`, `ssl`, `network`, `time`, `gc`)

## Requirements

- **ESP32** with at least 4 MB flash
- **MicroPython** 1.18 or later flashed on the board
- A **Telegram bot** token ([create one with @BotFather](https://t.me/BotFather))
- The **chat ID** of the alert recipient

> **Note:** Telegram alerts may fail on MicroPython firmware v1.23 and older due to the bundled mbedTLS library not supporting TLS 1.2+ ciphers required by `api.telegram.org`. The Proxmox check and HTTP dashboard are unaffected. Upgrading to MicroPython v1.24+ may resolve this.

## Flashing and deployment (Arch Linux)

```bash
# 1. Install tools
sudo pacman -S esptool
python -m venv ~/.venvs/esp32 && source ~/.venvs/esp32/bin/activate
pip install mpremote

# 2. Download MicroPython firmware
curl -LO https://micropython.org/resources/firmware/ESP32_GENERIC-20240602-v1.23.0.bin

# 3. Clean flash (recommended for first deploy)
esptool --port /dev/ttyUSB0 erase-flash
esptool --port /dev/ttyUSB0 --baud 460800 write-flash -z 0x1000 ESP32_GENERIC-*.bin

# 4. Edit credentials in main.py (lines 17–24)
#    WIFI_SSID, WIFI_PASSWORD, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

# 5. Upload files (order matters: boot.py first, main.py last)
source ~/.venvs/esp32/bin/activate
mpremote connect /dev/ttyUSB0 cp boot.py :boot.py
mpremote connect /dev/ttyUSB0 cp main.py :main.py   # triggers auto-start
```

> **Why clean flash?** `mpremote cp` triggers a soft-reset after each upload, which runs `main.py`. A clean flash ensures no stale files interfere with the deployment sequence.

## Configuration

Edit the following variables at the top of `main.py`:

```python
WIFI_SSID     = "YOUR_SSID"
WIFI_PASSWORD = "YOUR_PASSWORD"

PROXMOX_HOST = "192.168.1.50"
PROXMOX_PORT = 8006

TELEGRAM_TOKEN = "123456:ABC-DEF1234ghikl"   # Bot token
TELEGRAM_CHAT_ID = "123456789"                # Destination chat ID

CHECK_INTERVAL  = 30    # Seconds between health checks
FAIL_THRESHOLD  = 3     # Consecutive failures to trigger alert
ALERT_COOLDOWN  = 600   # Silence period after alert (10 minutes)
WEB_PORT        = 80    # HTTP dashboard port
```

## Architecture

Single-file monolithic design (`main.py`, ~400 lines) organized in sections:

| Section | Responsibility |
|---------|---------------|
| CONFIGURACION | All user-configurable variables |
| WI‑FI | Connection with 3 retries for cold-boot reliability |
| SSL helper | 4‑strategy cascade to disable cert validation across MicroPython builds |
| PROXMOX | Minimal HTTPS `GET /` request, returns bool |
| TELEGRAM | URL-encode + POST to Bot API |
| SERVIDOR WEB | Non‑blocking HTTP server with HTML dashboard |
| BUCLE PRINCIPAL | Cooperative loop: Wi‑Fi watchdog → Proxmox check (with recovery alert) → HTTP serve |
| ENTRY POINT | 3s cold-boot delay + `try/except` to keep REPL accessible on crash |

## How it works

```
[Boot] → 3s delay → Connect Wi‑Fi (3 retries) → Telegram boot alert → Loop:
  ├─ Proxmox responds → counter = 0 → serve HTTP → wait 30s
  │    └─ Was down before? → Telegram recovery alert
  └─ Proxmox does NOT respond → counter++
       └─ counter >= 3 → Telegram alert → cooldown 600s (HTTP still served)
```

## HTTP Dashboard

Access from any browser on the LAN:

```
http://<ESP32_IP>:80/
```

Displays: Proxmox status (ONLINE/OFFLINE), host, failure count, last alert time, Wi‑Fi IP, uptime. Auto-refreshes every 30 seconds. Dark theme, mobile-friendly.

## Monitoring serial output

```bash
mpremote connect /dev/ttyUSB0
```

Sample output:

```
=== Proxmox Monitor v3 ===
Host: 192.168.1.50:8006  |  Intervalo: 30s
Dashboard: http://<IP>:80/

[WiFi] Conectando a 'MyWiFi' …
[WiFi] Conectado. IP: 192.168.1.100
[Web] Dashboard en http://192.168.1.100:80/
[Boot] Enviando notificacion a Telegram …
[45] Verificando Proxmox … OK
[75] Verificando Proxmox … OK
[105] Verificando Proxmox … FALLO (1/3)
[135] Verificando Proxmox … FALLO (2/3)
[165] Verificando Proxmox … FALLO (3/3)
  -> Enviando alerta …
  [Telegram] Alerta enviada.
  -> Cooldown 600s (10 min)
[195] Verificando Proxmox … OK
  -> Enviando alerta de recuperacion …
  [Telegram] Alerta enviada.
```

## License

MIT
