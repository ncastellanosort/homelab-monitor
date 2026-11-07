"""
main.py — punto de entrada del monitor de Proxmox (ESP32 + MicroPython).

MicroPython ejecuta este archivo tras boot.py. La logica vive en app.py.
"""
import board

# Ventana de 3 s tras el arranque: da tiempo a que WiFi y flash esten listos
# y permite entrar en safe-boot pulsando el boton BOOT.
if board.safe_boot_requested(3):
    print("[Safe-boot] Monitor NO iniciado. REPL libre para subir archivos.")
else:
    # Captura errores para dejar el REPL accesible. Si el watchdog esta
    # activo, la placa se reinicia sola a los pocos segundos.
    try:
        import app
        app.run()
    except Exception as e:
        import sys
        print("[FATAL] el monitor fallo:")
        sys.print_exception(e)
