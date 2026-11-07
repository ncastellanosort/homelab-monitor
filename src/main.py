"""
main.py — punto de entrada del monitor de Proxmox (ESP32 + MicroPython).

MicroPython ejecuta este archivo tras boot.py. La logica vive en app.py.
"""
import time

# Arranque desde cold-boot: dar tiempo a que WiFi y flash esten listos
time.sleep(3)

# Ejecutar el monitor (captura errores para dejar el REPL accesible)
try:
    import app
    app.run()
except Exception as e:
    import sys
    print("[FATAL] el monitor fallo:")
    sys.print_exception(e)
