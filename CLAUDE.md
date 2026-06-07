# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Single-file MicroPython monitor (`main.py` + stub `boot.py`) for ESP32 that checks a Proxmox server via HTTPS every 30s and serves a live dashboard on port 80. No build system, no external dependencies — uses only MicroPython stdlib (`socket`, `ssl`, `network`, `time`, `gc`).

## ESP32 interaction (Arch Linux host)

Device at `/dev/ttyUSB0` (CP2102 UART bridge, VID:PID `10c4:ea60`, group `uucp`). Tools in `~/.venvs/esp32/`.

```bash
# Activar entorno
source ~/.venvs/esp32/bin/activate

# Subir main.py (dispara soft-reset, arranca el monitor)
mpremote connect /dev/ttyUSB0 cp main.py :main.py

# Ver dashboard
curl http://192.168.1.8:80/

# REPL serial
mpremote connect /dev/ttyUSB0
```

**Clean deployment** (cuando `mpremote cp` falla porque el REPL está bloqueado por el monitor corriendo):

```bash
esptool --port /dev/ttyUSB0 erase-flash
esptool --port /dev/ttyUSB0 --baud 460800 write-flash -z 0x1000 ESP32_GENERIC-*.bin
mpremote connect /dev/ttyUSB0 cp boot.py :boot.py
mpremote connect /dev/ttyUSB0 cp main.py :main.py   # este cp dispara el arranque
```

**Nota:** `mpremote cp` hace soft-reset automático tras cada copia, lo que ejecuta `main.py`. Para subir múltiples archivos en una sesión limpia, subir `boot.py` (stub) primero y `main.py` al final.

## Arquitectura de main.py

Archivo monolítico autónomo (~400 líneas) organizado en secciones:

| Líneas | Sección | Responsabilidad |
|--------|---------|-----------------|
| 13–31 | CONFIGURACION | Variables a editar antes de desplegar |
| 33–67 | WI-FI | `wifi_connect()`, `wifi_ensure()`, `wifi_ip()` — conexión con 3 reintentos |
| 70–83 | SSL helper | `_ssl_no_verify()` — cascada de 4 estrategias para ignorar certificados |
| 93–121 | PROXMOX | `proxmox_check()` — petición HTTPS mínima, retorna bool |
| 125–183 | TELEGRAM | `_url_encode()`, `telegram_send()` — POST a api.telegram.org |
| 187–299 | SERVIDOR WEB | `_web_render()`, `_web_start()`, `_web_serve()` — dashboard HTTP no bloqueante |
| 303–394 | BUCLE PRINCIPAL | `main()` — orquestador cooperativo (WiFi → check Proxmox → recovery alert → HTTP serve) |
| 399–412 | ENTRY POINT | `time.sleep(3)` + `try: main() except: print` para cold-boot |

### Decisiones de diseño

- **`recv()`/`sendall()` en vez de `read()`/`write()`** para el socket HTTP — más fiable en respuestas a navegadores reales.
- **`.format()` en vez de f-strings** para compatibilidad con MicroPython (no soporta `:.0f` en f-strings ni `f"\r\n"` con solo escapes).
- **HTML con string concatenation** en vez de `.format()` con `{{ }}` porque MicroPython no escapa llaves en `.format()`.
- **Cold-boot**: `time.sleep(3)` antes de `main()` para asegurar que WiFi y flash estén listos. `wifi_connect()` reintenta 3 veces (15s cada intento).
- **Telegram SSL limitado**: la biblioteca mbedTLS del firmware MicroPython v1.23 puede no soportar TLS 1.2+ con los cifrados de `api.telegram.org`. Las alertas de Telegram pueden fallar silenciosamente. La verificación a Proxmox sí funciona (TLS más básico con certificado auto-firmado).
- **Recovery alert**: `state["recovery_pending"]` se activa al enviar una alerta de caída y se limpia al enviar la de recuperación. Esto asegura que solo se notifica recuperación tras una caída confirmada (no en flappings leves).
- **Líneas actualizadas**: el bucle principal ahora abarca hasta ~430 líneas por las adiciones de recovery.

## Config variables

En `main.py` líneas 17–31: `WIFI_SSID`, `WIFI_PASSWORD`, `PROXMOX_HOST`, `PROXMOX_PORT`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `CHECK_INTERVAL`, `FAIL_THRESHOLD`, `ALERT_COOLDOWN`, `REQUEST_TIMEOUT`, `WEB_PORT`.

Nunca commitear credenciales reales. El repositorio usa placeholders (`TU_SSID`, `TU_BOT_TOKEN`, etc.).
