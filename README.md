# ESP32 Proxmox Monitor

Monitor de disponibilidad para servidores Proxmox VE que corre en una ESP32 con MicroPython. Verifica periódicamente si el servidor responde vía HTTPS y envía alertas por Telegram si deja de hacerlo.

## Características

- Conexión Wi‑Fi con reconexión automática ante caídas
- Peticiones HTTPS ignorando el certificado SSL (válido tanto para certificados auto‑firmados como para ESP32 sin CAs raíz)
- Umbral configurable de fallos consecutivos antes de disparar la alerta
- Cooldown de 10 minutos tras cada alerta para evitar saturación de notificaciones
- Sin dependencias externas: solo usa módulos estándar de MicroPython (`socket`, `ssl`, `network`, `time`, `gc`)

## Requisitos

- **ESP32** con al menos 4 MB de flash
- **MicroPython** 1.18 o superior flasheado en la placa
- Un **bot de Telegram** con su token ([crear bot con @BotFather](https://t.me/BotFather))
- El **chat ID** del destinatario de las alertas

## Flasheo y despliegue (desde Arch Linux)

```bash
# 1. Instalar herramientas
sudo pacman -S esptool
python -m venv ~/.venvs/esp32 && source ~/.venvs/esp32/bin/activate
pip install mpremote

# 2. Descargar firmware MicroPython
curl -LO https://micropython.org/resources/firmware/ESP32_GENERIC-20240602-v1.23.0.bin

# 3. Flashear la ESP32 (ajusta --port si usas otro dispositivo)
esptool --port /dev/ttyUSB0 erase_flash
esptool --port /dev/ttyUSB0 --baud 460800 write_flash -z 0x1000 ESP32_GENERIC-*.bin

# 4. Editar variables de configuración en main.py
#    WIFI_SSID, WIFI_PASSWORD, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

# 5. Subir el script
mpremote connect /dev/ttyUSB0 cp main.py :main.py
mpremote connect /dev/ttyUSB0 reset
```

## Configuración

Editar las siguientes variables al inicio de `main.py`:

```python
WIFI_SSID     = "TU_SSID"
WIFI_PASSWORD = "TU_PASSWORD"

PROXMOX_HOST = "192.168.1.50"
PROXMOX_PORT = 8006

TELEGRAM_TOKEN = "123456:ABC-DEF1234ghikl"   # Token del bot
TELEGRAM_CHAT_ID = "123456789"                # ID del chat destino

CHECK_INTERVAL  = 30    # Segundos entre verificaciones
FAIL_THRESHOLD  = 3     # Fallos consecutivos para disparar alerta
ALERT_COOLDOWN  = 600   # Silencio tras alerta (10 minutos)
```

## Cómo funciona

```
[Boot] → Conectar Wi‑Fi → Loop:
  ├─ Proxmox responde → contador = 0 → esperar 30s
  └─ Proxmox NO responde → contador++
       └─ contador >= 3 → Telegram → dormir 600s
```

1. Cada 30 segundos se envía una petición `GET /` a `https://192.168.1.50:8006/`
2. Si falla (timeout o error de conexión), se incrementa un contador
3. Al acumular 3 fallos (~1.5 min), se envía una alerta por Telegram
4. Tras la alerta, se pausa durante 10 minutos para no saturar el dispositivo destino
5. Si el servidor vuelve a responder, el contador se reinicia a cero

## Monitorear salida serial

```bash
mpremote connect /dev/ttyUSB0
```

Ejemplo de salida:

```
=== Monitor de Proxmox para ESP32 ===
Objetivo:  192.168.1.50:8006
Intervalo: 30s  |  Umbral: 3 fallos
Cooldown:  600s (10 min)

[WiFi] Conectando a 'MiWiFi' …
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

## Licencia

MIT
