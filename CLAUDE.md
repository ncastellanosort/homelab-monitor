# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

MicroPython script (`main.py`) that runs on an ESP32 to monitor a Proxmox server (192.168.1.50:8006) and send Telegram alerts when it stops responding. No build system, no dependencies beyond MicroPython stdlib.

## ESP32 interaction (Arch Linux host)

The ESP32 connects via USB at `/dev/ttyUSB0` (CP2102 UART bridge, VID:PID `10c4:ea60`). The `uucp` group owns the device.

```bash
# Flash MicroPython firmware (first time or full wipe)
esptool --port /dev/ttyUSB0 erase_flash
esptool --port /dev/ttyUSB0 --baud 460800 write_flash -z 0x1000 <firmware.bin>

# Upload main.py and reset
mpremote connect /dev/ttyUSB0 cp main.py :main.py
mpremote connect /dev/ttyUSB0 reset

# Open serial REPL
mpremote connect /dev/ttyUSB0
```

`mpremote` is installed in `~/.venvs/esp32/` — activate with `source ~/.venvs/esp32/bin/activate` before use.

## Architecture decisions in main.py

- **Raw sockets + SSL instead of `urequests`**: avoids dependency on external MicroPython libs and gives control over SSL cert validation.
- **`ssl_wrap_no_verify()` cascade**: tries 4 strategies to disable cert verification because MicroPython builds differ in how `CERT_NONE` is exposed. Needed for both Proxmox (self-signed cert) and Telegram (ESP32 may lack root CAs).
- **WiFi survival**: `ensure_wifi()` runs before every check cycle; if reconnection fails it waits 10s and retries rather than crashing.

## Config variables to change before deploy

In `main.py` lines ~20-27: `WIFI_SSID`, `WIFI_PASSWORD`, `PROXMOX_HOST`, `PROXMOX_PORT`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`.
