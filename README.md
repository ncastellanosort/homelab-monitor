# ESP32 Proxmox Monitor

Proxmox VE availability monitor running on an ESP32 with MicroPython. Periodically checks if the server responds via HTTPS and sends Telegram alerts when it goes down.

## Features

- Wi‑Fi connection with automatic reconnection on dropout
- HTTPS requests ignoring SSL certificate validation (works with self‑signed certs and ESP32 devices without built‑in root CAs)
- Configurable failure threshold before triggering an alert
- 10‑minute cooldown after each alert to avoid notification spam
- Zero external dependencies — uses only MicroPython standard library (`socket`, `ssl`, `network`, `time`, `gc`)

## Requirements

- **ESP32** with at least 4 MB flash
- **MicroPython** 1.18 or later flashed on the board
- A **Telegram bot** token ([create one with @BotFather](https://t.me/BotFather))
- The **chat ID** of the alert recipient

## Flashing and deployment (Arch Linux)

```bash
# 1. Install tools
sudo pacman -S esptool
python -m venv ~/.venvs/esp32 && source ~/.venvs/esp32/bin/activate
pip install mpremote

# 2. Download MicroPython firmware
curl -LO https://micropython.org/resources/firmware/ESP32_GENERIC-20240602-v1.23.0.bin

# 3. Flash the ESP32 (adjust --port if needed)
esptool --port /dev/ttyUSB0 erase-flash
esptool --port /dev/ttyUSB0 --baud 460800 write-flash -z 0x1000 ESP32_GENERIC-*.bin

# 4. Edit configuration variables in main.py
#    WIFI_SSID, WIFI_PASSWORD, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

# 5. Upload the script
mpremote connect /dev/ttyUSB0 cp main.py :main.py
mpremote connect /dev/ttyUSB0 reset
```

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
```

## How it works

```
[Boot] → Connect Wi‑Fi → Loop:
  ├─ Proxmox responds → counter = 0 → wait 30s
  └─ Proxmox does NOT respond → counter++
       └─ counter >= 3 → Telegram alert → sleep 600s
```

1. Every 30 seconds a `GET /` request is sent to `https://192.168.1.50:8006/`
2. On failure (timeout or connection error) a counter increments
3. After 3 consecutive failures (~1.5 min) a Telegram alert is sent
4. After sending the alert, a 10‑minute pause prevents notification flooding
5. If the server starts responding again the failure counter resets to 0

## Monitoring serial output

```bash
mpremote connect /dev/ttyUSB0
```

Sample output:

```
=== Monitor de Proxmox para ESP32 ===
Objetivo:  192.168.1.50:8006
Intervalo: 30s  |  Umbral: 3 fallos
Cooldown:  600s (10 min)

[WiFi] Conectando a 'MyWiFi' …
[WiFi] Conectado. IP: 192.168.1.100
[12345] Verificando Proxmox … OK
[12375] Verificando Proxmox … OK
[12405] Verificando Proxmox … FALLO (1/3)
[12435] Verificando Proxmox … FALLO (2/3)
[12465] Verificando Proxmox … FALLO (3/3)
  -> Enviando alerta por Telegram …
  [Telegram] Alerta enviada correctamente.
  -> Pausa de 600s (10 min) para evitar spam …
```

## License

MIT
