# ESP32 Proxmox Monitor

[![GitHub release](https://img.shields.io/github/v/release/ncastellanosort/homelab-monitor?style=flat-square)](https://github.com/ncastellanosort/homelab-monitor/releases)
[![CI](https://github.com/ncastellanosort/homelab-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/ncastellanosort/homelab-monitor/actions/workflows/ci.yml)

Proxmox VE availability monitor running on an ESP32 with MicroPython. It checks over HTTPS whether the server responds, sends Telegram alerts when it goes down and when it recovers, and serves a live dashboard on port 80.

## Features

- HTTPS health check of the Proxmox web UI (self-signed certificates accepted). Proxmox counts as up only when it returns a real HTTP response below 500.
- Telegram alerts: on boot, after `FAIL_THRESHOLD` consecutive failures, a reminder every `ALERT_COOLDOWN` seconds while it stays down, and a recovery message. Undelivered alerts are retried on the next check.
- Live dashboard (`/`) and JSON status API (`/api/status`).
- Credentials in a `.env` file on the board, never in the code.
- Hardware watchdog and a safe-boot button to always get the REPL back.
- Wi-Fi reconnection with retries.
- No dependencies beyond the MicroPython standard library.

## Requirements

- **ESP32** with at least 4 MB flash
- **MicroPython 1.23** or later on the board
- A **Telegram bot** token and the chat ID to send alerts to ([@BotFather](https://t.me/BotFather); see `.env.example`)
- The ESP32 must be able to reach Proxmox: if they are on different subnets/VLANs, the router has to allow traffic between them.

## Project layout

```
src/            code that runs on the ESP32
  main.py       entry point: 3 s safe-boot window, then app.run()
  app.py        main loop: Wi-Fi -> check -> alerts -> HTTP
  monitor.py    alert state machine (pure logic, no I/O)
  config.py     .env parsing and validation
  net.py        shared HTTPS helper (never falls back to plaintext)
  proxmox.py    health check
  notifier.py   Telegram messages and sending
  web.py        dashboard, JSON API and routing
  wifi.py       Wi-Fi connection
  board.py      watchdog and safe-boot (BOOT button)
  fmt.py        text formatting helpers
tests/          pytest suite (runs on CPython with hardware stubs)
deploy.sh       deploy script (Linux/macOS/WSL)
deploy.ps1      deploy script (Windows)
.env.example    configuration template
```

## Setup

### 1. Tools and USB driver

The board uses a CP2102 USB-UART bridge.

**Windows:** install the [Silicon Labs CP210x VCP driver](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers). The board should then show up as a `COMx` port in Device Manager.

```powershell
py -m venv $HOME\.venvs\esp32
$HOME\.venvs\esp32\Scripts\pip install mpremote esptool "mpy-cross>=1.23,<1.24"
```

**Linux:** the driver is built into the kernel. Add yourself to the serial group (`dialout` on Debian/Ubuntu, `uucp` on Arch) and log in again.

```bash
python -m venv ~/.venvs/esp32 && source ~/.venvs/esp32/bin/activate
pip install mpremote esptool "mpy-cross>=1.23,<1.24"
```

**WSL2:** forward the USB device from Windows with [usbipd-win](https://github.com/dorssel/usbipd-win) (`usbipd bind` / `usbipd attach --wsl`), then follow the Linux steps. The board appears as `/dev/ttyUSB0`.

### 2. Flash MicroPython (first time only)

```bash
curl -LO https://micropython.org/resources/firmware/ESP32_GENERIC-20240602-v1.23.0.bin
esptool --port /dev/ttyUSB0 erase-flash
esptool --port /dev/ttyUSB0 --baud 460800 write-flash -z 0x1000 ESP32_GENERIC-20240602-v1.23.0.bin
```

On Windows use `COM3` (or your port) instead of `/dev/ttyUSB0`.

### 3. Configure

```bash
cp .env.example .env
```

Fill in `.env`. It is in `.gitignore` and must never be committed.

| Key | Required | Default | Meaning |
|-----|----------|---------|---------|
| `WIFI_SSID`, `WIFI_PASSWORD` | yes | | Wi-Fi network |
| `PROXMOX_HOST`, `PROXMOX_PORT` | yes | `192.168.1.50`, `8006` | Proxmox web UI |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | for alerts | | Bot token and destination chat |
| `CHECK_INTERVAL` | no | `30` | Seconds between checks |
| `FAIL_THRESHOLD` | no | `3` | Consecutive failures before alerting |
| `ALERT_COOLDOWN` | no | `600` | Seconds between reminder alerts while down |
| `REQUEST_TIMEOUT` | no | `10` | Network timeout in seconds |
| `WEB_PORT` | no | `80` | Dashboard port |
| `WDT_TIMEOUT` | no | `60` | Watchdog in seconds (minimum 30, `0` disables it) |

Invalid values or leftover placeholders are reported on the serial console and on the dashboard. Without Telegram settings the monitor still runs, but alerts are disabled.

### 4. Deploy

```bash
./deploy.sh /dev/ttyUSB0          # Linux / WSL
```

```powershell
.\deploy.ps1 -Port COM3           # Windows
```

The script uploads `src/` and `.env` in one `mpremote` session, removes stale modules from the board and resets it. Options: `--mpy` / `-Mpy` precompiles the modules with `mpy-cross` (faster boot, less RAM), and `--dry-run` / `-DryRun` prints the command without running it. Without a port, `mpremote` picks the board automatically.

## Watchdog and safe-boot

The hardware watchdog restarts the board if the main loop freezes, for example on a stuck TLS handshake. It also means that after `Ctrl-C` in the REPL the board resets within `WDT_TIMEOUT` seconds.

To get a free REPL (to upload files or debug), use **safe-boot**:

1. Press and release **EN/RST**.
2. Within 3 seconds, press **BOOT**.

The console prints `[Safe-boot] Monitor NO iniciado` and the monitor does not start, so the watchdog stays off. Do not hold BOOT *while* pressing EN: that puts the ESP32 into firmware download mode instead.

## How it works

```
boot -> 3 s safe-boot window -> load .env -> start watchdog -> Wi-Fi -> boot message
loop (~1 s per turn, watchdog fed each turn):
  every CHECK_INTERVAL: GET https://PROXMOX_HOST:PORT/
    OK (HTTP < 500)  -> fail count = 0; if an outage was alerted -> recovery message
    failure          -> fail count + 1
                        >= FAIL_THRESHOLD and not alerted yet  -> down alert
                        still down after ALERT_COOLDOWN        -> reminder
  a message that Telegram did not accept is retried on the next check
  serve at most one HTTP request
```

## Dashboard and API

- `http://<ESP32_IP>/` shows status (ONLINE / OFFLINE / DESCONOCIDO before the first check), host, consecutive failures, last check result, last alert, Telegram delivery status, Wi-Fi IP, uptime and configuration warnings. It auto-refreshes every 30 s.
- `http://<ESP32_IP>/api/status` returns the same data as JSON.

Any other path returns 404.

## Serial output

```bash
mpremote connect /dev/ttyUSB0
```

```
[Boot] Pulsa BOOT en los proximos 3 s para safe-boot ...

=== Proxmox Monitor v2.0.0 ===
Host: 192.168.40.50:8006  |  Intervalo: 30s
Dashboard: http://<IP>:80/
========================================

[WDT] Activo (60 s). Para usar el REPL: reset y pulsa BOOT.
[WiFi] Conectando a 'MyWiFi' ...
[WiFi] Conectado. IP: 192.168.1.8
[Web] Dashboard en http://192.168.1.8:80/
[Boot] Enviando notificacion a Telegram ...
  [Telegram] Mensaje enviado.
[3s] Verificando Proxmox ... OK (HTTP 200)
[33s] Verificando Proxmox ... FALLO 1/3 (error de red: [Errno 116] ETIMEDOUT)
[1m 3s] Verificando Proxmox ... FALLO 2/3 (error de red: [Errno 116] ETIMEDOUT)
[1m 33s] Verificando Proxmox ... FALLO 3/3 (error de red: [Errno 116] ETIMEDOUT)
  -> Enviando alerta de caida ...
  [Telegram] Mensaje enviado.
[2m 3s] Verificando Proxmox ... OK (HTTP 200)
  -> Enviando alerta de recuperacion ...
  [Telegram] Mensaje enviado.
```

## Security notes

- TLS certificates are **not verified**, for Proxmox (self-signed) or for `api.telegram.org` (the firmware has no CA bundle). Traffic is encrypted, but someone on your local network could impersonate either server and capture the bot token. If that happens, revoke the token with `/revoke` in @BotFather.
- The HTTPS helper never falls back to plaintext. If TLS is unavailable, the request fails.
- The dashboard has no authentication and shows the Proxmox address. Keep it on a trusted LAN.

## Known limitations

Telegram may fail on some MicroPython builds whose bundled mbedTLS cannot negotiate with `api.telegram.org`. The dashboard then shows "ERROR en el ultimo envio" and alerts are retried on every check. The Proxmox check and the dashboard are unaffected. Upgrading MicroPython usually fixes it.

## Development

```bash
pip install pytest ruff "mpy-cross>=1.23,<1.24"
pytest -q          # tests on CPython with stubs for network/machine
ruff check .       # lint
```

CI (GitHub Actions) runs ruff and pytest, and compiles every module with `mpy-cross` 1.23 to catch syntax MicroPython does not support.

## License

MIT
