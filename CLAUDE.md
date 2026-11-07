# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Monitor MicroPython para ESP32 que comprueba un servidor Proxmox por HTTPS, envía alertas por Telegram y sirve un dashboard en el puerto 80. El código que corre en la placa está en `src/` y solo usa la stdlib de MicroPython. `tests/` corre en CPython con stubs de hardware.

## Comandos de desarrollo

```bash
pytest -q                 # tests (pyproject.toml añade src/ al path)
pytest tests/test_monitor.py::test_reminder_only_after_cooldown   # un test
ruff check .              # lint
python -m mpy_cross src/app.py   # comprobar que compila para MicroPython
```

CI (`.github/workflows/ci.yml`) ejecuta ruff, pytest y mpy-cross 1.23 sobre todo `src/`.

## Placa (ESP32 con CP2102, VID:PID `10c4:ea60`)

- **Windows:** necesita el driver Silicon Labs CP210x VCP; sin él aparece "Error, código 28" y no hay puerto COM. Usar `COMx` como puerto.
- **WSL2:** `usbipd bind/attach --wsl` desde PowerShell como admin; aparece `/dev/ttyUSB0` (grupo `dialout`).
- **Arch Linux:** `/dev/ttyUSB0`, grupo `uucp`.
- Herramientas: `mpremote`, `esptool`, `mpy-cross` (pip, en `~/.venvs/esp32`).

```bash
./deploy.sh /dev/ttyUSB0 [--mpy] [--dry-run]     # Linux/WSL
.\deploy.ps1 -Port COM3 [-Mpy] [-DryRun]         # Windows
mpremote connect /dev/ttyUSB0                    # ver salida / REPL
```

Los scripts de despliegue hacen todo en una sola sesión de mpremote: borran los módulos de la placa (no el `.env`), copian `src/*` (o `.mpy` precompilados, salvo `boot.py`/`main.py`), copian `.env` y hacen `reset`.

**Si la placa no responde** (watchdog reiniciando o monitor ocupando el REPL): safe-boot. Pulsar EN/RST, soltar, y pulsar BOOT antes de 3 s. Pulsar BOOT *durante* el reset entra en modo descarga de firmware, no en safe-boot. Como último recurso: `esptool erase-flash` + `write-flash` del firmware y volver a desplegar.

## Arquitectura

- `main.py`: ventana de 3 s de safe-boot (`board.safe_boot_requested`) y luego `app.run()` dentro de un try que deja el REPL libre si algo falla.
- `app.py`: `App.tick()` es una vuelta del bucle (~1 s): alimenta el WDT, reconecta Wi-Fi, chequea si toca y sirve una petición HTTP. `Clock` acumula `ticks_diff` para tener ms monotónicos sin desborde (no usar `time.time()`: depende del RTC/NTP).
- `monitor.py`: máquina de estados pura. `on_check(ok, now_ms)` devuelve `DOWN`/`RECOVERY`/`None`; `on_sent(event, delivered, now_ms)` solo cambia el estado si Telegram aceptó el mensaje (si no, se reintenta en el siguiente chequeo). Los chequeos siguen su cadencia durante el cooldown; el cooldown solo espacia los recordatorios de caída.
- `config.py`: `load(path)` → objeto `Config` con valores y `problems` (avisos que se muestran en consola y dashboard). Sin efectos al importar.
- `net.py`: `https_request()` es el único sitio que abre sockets TLS. `wrap_tls()` prueba varias APIs de ssl y **nunca devuelve el socket en texto plano**. Solo pasa a la siguiente estrategia ante errores de API (`AttributeError`/`TypeError`); un `OSError` del handshake se propaga.
- `web.py`: `route()` y `build_response()` son puros (testeables); `serve()` atiende una petición por vuelta.
- Los módulos con lógica reciben la configuración por parámetro; solo `app.py` usa `config`.

## Restricciones de MicroPython

- Usar `.format()`, no f-strings (por compatibilidad con firmwares antiguos).
- El HTML se construye concatenando strings, no con `.format()` (las llaves del CSS chocarían).
- Emojis con escapes Unicode (`"\U0001F534"`), nunca bytes UTF-8 sueltos dentro de un `str`.
- Sin `time.time()` para medir intervalos; usar `Clock`.
- Comprobar siempre con mpy-cross 1.23 (CI lo hace) tras cambiar `src/`.
- `recv()`/`sendall()` en el socket del servidor web: más fiable que `read()`/`write()` con navegadores reales.
- El TLS de Telegram puede fallar en algunos firmwares (mbedTLS); el chequeo de Proxmox sí funciona.

## Configuración

Todo sale del `.env` de la placa (plantilla: `.env.example`; tabla completa en README). `.env` está en `.gitignore`: nunca commitear credenciales reales ni leer/mostrar su contenido.
