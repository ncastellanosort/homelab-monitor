"""wifi.py — conexion Wi-Fi con reintentos."""
import network
import time


def _wlan():
    return network.WLAN(network.STA_IF)


def connect(ssid, password, attempts=3, wait_s=15, on_wait=None):
    """Conecta a la red. on_wait() se llama cada segundo de espera."""
    wlan = _wlan()
    wlan.active(True)
    if wlan.isconnected():
        print("[WiFi] Ya conectado. IP: {0}".format(wlan.ifconfig()[0]))
        return True
    print("[WiFi] Conectando a '{0}' ...".format(ssid))
    # Reintentar varias veces (cold-boot puede necesitar mas tiempo)
    for intento in range(1, attempts + 1):
        wlan.connect(ssid, password)
        for _ in range(wait_s):
            if wlan.isconnected():
                print("[WiFi] Conectado. IP: {0}".format(wlan.ifconfig()[0]))
                return True
            if on_wait is not None:
                on_wait()
            time.sleep(1)
        print("[WiFi] Reintento {0}/{1} ...".format(intento, attempts))
    print("[WiFi] ERROR: no se pudo conectar tras {0} intentos.".format(attempts))
    return False


def is_connected():
    return _wlan().isconnected()


def ip():
    wlan = _wlan()
    return wlan.ifconfig()[0] if wlan.isconnected() else ""
