"""board.py — watchdog de hardware y safe-boot con el boton BOOT (GPIO0).

Safe-boot: tras un reset, pulsar BOOT durante la ventana de arranque (3 s)
impide que arranque el monitor y deja el REPL libre para subir archivos.
OJO: BOOT pulsado *en el momento del reset* pone el ESP32 en modo descarga
de firmware; hay que pulsarlo despues de soltar EN/RST.
"""
import time

_wdt = None


def safe_boot_requested(window_s=3, pin_no=0):
    """Espera window_s segundos; True si BOOT se pulsa durante la espera."""
    try:
        from machine import Pin
        pin = Pin(pin_no, Pin.IN, Pin.PULL_UP)
    except Exception:
        time.sleep(window_s)
        return False
    print("[Boot] Pulsa BOOT en los proximos {0} s para safe-boot ...".format(window_s))
    for _ in range(window_s * 20):
        if pin.value() == 0:
            return True
        time.sleep(0.05)
    return False


def wdt_start(timeout_s):
    """Activa el watchdog. timeout_s <= 0 lo deja desactivado."""
    global _wdt
    if timeout_s <= 0:
        return False
    try:
        from machine import WDT
        _wdt = WDT(timeout=timeout_s * 1000)
    except Exception as e:
        print("[WDT] No disponible: {0}".format(e))
        return False
    print("[WDT] Activo ({0} s). Para usar el REPL: reset y pulsa BOOT.".format(timeout_s))
    return True


def wdt_active():
    return _wdt is not None


def feed():
    if _wdt is not None:
        _wdt.feed()
