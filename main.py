"""
main.py — Monitor de disponibilidad de Proxmox para ESP32 con MicroPython

Verifica periódicamente si el servidor Proxmox responde vía HTTPS.
Ignora la validación SSL (certificado auto-firmado de Proxmox y
posible ausencia de CA raíz en la ESP32).
Si acumula 3 fallos consecutivos, envía una alerta por Telegram
y espera 10 minutos antes de reanudar la verificación.
"""

import network
import socket
import time
import gc


# ============================================================
# CONFIGURACIÓN — Ajusta estos valores a tu entorno
# ============================================================

WIFI_SSID     = "TU_SSID"
WIFI_PASSWORD = "TU_PASSWORD"

PROXMOX_HOST = "192.168.1.50"
PROXMOX_PORT = 8006  # Puerto HTTPS de la interfaz web de Proxmox VE

TELEGRAM_TOKEN = "TU_BOT_TOKEN"      # Token del bot de Telegram
TELEGRAM_CHAT_ID = "TU_CHAT_ID"      # ID del chat o grupo destinatario

CHECK_INTERVAL  = 30    # Segundos entre cada verificación
FAIL_THRESHOLD  = 3     # Fallos consecutivos necesarios para lanzar alerta
ALERT_COOLDOWN  = 600   # Segundos de silencio tras enviar una alerta (10 min)
REQUEST_TIMEOUT = 10    # Timeout en segundos para cada petición HTTPS


# ============================================================
# WI‑FI — Conexión y reconexión automática
# ============================================================

def connect_wifi():
    """Establece la conexión Wi‑Fi con reintentos. Retorna True si ok."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print(f"[WiFi] Ya conectado. IP: {wlan.ifconfig()[0]}")
        return True

    print(f"[WiFi] Conectando a '{WIFI_SSID}' …")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    # Esperar hasta 30 segundos por la conexión
    for _ in range(30):
        if wlan.isconnected():
            print(f"[WiFi] Conectado. IP: {wlan.ifconfig()[0]}")
            return True
        time.sleep(1)

    print("[WiFi] ERROR: no se pudo conectar tras 30 intentos.")
    return False


def ensure_wifi():
    """Verifica que el Wi‑Fi siga activo; reconecta si es necesario."""
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("[WiFi] Conexión perdida, reintentando …")
        return connect_wifi()
    return True


# ============================================================
# SSL — Envoltorio que desactiva la validación del certificado
# ============================================================

def ssl_wrap_no_verify(sock, hostname):
    """
    Envuelve un socket en SSL ignorando la validación del certificado.
    Prueba varias estrategias por compatibilidad con distintos builds
    de MicroPython (CERT_NONE puede llamarse distinto o no existir).
    Si nada funciona, devuelve el socket sin envolver.
    """
    try:
        import ssl as _ssl
    except ImportError:
        return sock  # Sin módulo SSL no se puede envolver

    CERT_NONE = getattr(_ssl, 'CERT_NONE', 0)

    estrategias = [
        lambda: _ssl.wrap_socket(sock, server_hostname=hostname, cert_reqs=CERT_NONE),
        lambda: _ssl.wrap_socket(sock, cert_reqs=CERT_NONE),
        lambda: _ssl.wrap_socket(sock, server_hostname=hostname),
        lambda: _ssl.wrap_socket(sock),
    ]

    for estrategia in estrategias:
        try:
            return estrategia()
        except (OSError, AttributeError, TypeError, ValueError):
            continue

    return sock  # Último recurso: socket sin SSL


# ============================================================
# PROXMOX — Petición HTTPS con certificado ignorado
# ============================================================

def check_proxmox():
    """
    Realiza una petición HTTPS mínima a Proxmox.
    Retorna True si el servidor responde (cualquier dato),
    False ante timeout, error de conexión o SSL.
    """
    sock = None
    try:
        addr = socket.getaddrinfo(PROXMOX_HOST, PROXMOX_PORT)[0][-1]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(REQUEST_TIMEOUT)
        sock.connect(addr)

        # Envolver en SSL sin validar el certificado auto‑firmado
        sock = ssl_wrap_no_verify(sock, PROXMOX_HOST)

        # Petición HTTP/1.1 mínima — solo necesitamos verificar que responda
        request = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {PROXMOX_HOST}:{PROXMOX_PORT}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        sock.write(request.encode())

        # Leer respuesta — con recibir cualquier dato alcanza
        data = sock.read(256)
        return len(data) > 0

    except OSError as e:
        print(f"  [Proxmox] Error de red: {e}")
        return False
    except Exception as e:
        print(f"  [Proxmox] Error inesperado: {e}")
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        gc.collect()


# ============================================================
# TELEGRAM — Notificación por la API del bot
# ============================================================

def url_encode(texto):
    """Codifica una cadena en formato URL (UTF‑8 + percent‑encoding)."""
    seguros = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.~-"
    )
    resultado = []
    for caracter in texto:
        if caracter in seguros:
            resultado.append(caracter)
        elif caracter == ' ':
            resultado.append('+')
        else:
            # Codificar cada byte de la representación UTF‑8 del carácter
            for byte in caracter.encode('utf-8'):
                resultado.append('%{:02X}'.format(byte))
    return ''.join(resultado)


def send_telegram(mensaje):
    """
    Envía un mensaje de texto al chat de Telegram configurado.
    Retorna True si el envío fue exitoso, False en caso contrario.
    """
    TELEGRAM_HOST = "api.telegram.org"
    TELEGRAM_PORT = 443

    path = f"/bot{TELEGRAM_TOKEN}/sendMessage"
    body = f"chat_id={TELEGRAM_CHAT_ID}&text={url_encode(mensaje)}"

    sock = None
    try:
        addr = socket.getaddrinfo(TELEGRAM_HOST, TELEGRAM_PORT)[0][-1]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(REQUEST_TIMEOUT)
        sock.connect(addr)

        # Telegram tiene certificado válido, pero la ESP32 puede carecer
        # de los certificados raíz necesarios para validarlo
        sock = ssl_wrap_no_verify(sock, TELEGRAM_HOST)

        peticion = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: {TELEGRAM_HOST}\r\n"
            f"Content-Type: application/x-www-form-urlencoded\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )
        sock.write(peticion.encode())

        respuesta = sock.read(512)
        if b"200 OK" in respuesta:
            print("  [Telegram] Alerta enviada correctamente.")
            return True
        else:
            print(f"  [Telegram] Respuesta inesperada: {respuesta[:120]}")
            return False

    except OSError as e:
        print(f"  [Telegram] Error de red: {e}")
        return False
    except Exception as e:
        print(f"  [Telegram] Error inesperado: {e}")
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        gc.collect()


# ============================================================
# BUCLE PRINCIPAL
# ============================================================

def main():
    print("\n=== Monitor de Proxmox para ESP32 ===")
    print(f"Objetivo:  {PROXMOX_HOST}:{PROXMOX_PORT}")
    print(f"Intervalo: {CHECK_INTERVAL}s  |  Umbral: {FAIL_THRESHOLD} fallos")
    print(f"Cooldown:  {ALERT_COOLDOWN}s (10 min)\n")

    # Conexión Wi‑Fi inicial — sin ella no podemos operar
    if not connect_wifi():
        print("[FATAL] Sin Wi‑Fi no se puede operar. Reinicia la ESP32.")
        return

    fail_count = 0               # Fallos consecutivos actuales
    last_alert = 0               # Timestamp de la última alerta enviada

    while True:
        try:
            if not ensure_wifi():
                time.sleep(10)   # Esperar antes de reintentar el Wi‑Fi
                continue

            print(f"[{time.time():.0f}] Verificando Proxmox …", end="")

            if check_proxmox():
                print(" OK")
                if fail_count > 0:
                    print(f"  -> Contador de fallos reiniciado (era {fail_count})")
                fail_count = 0
            else:
                fail_count += 1
                print(f" FALLO ({fail_count}/{FAIL_THRESHOLD})")

                if fail_count >= FAIL_THRESHOLD:
                    ahora = time.time()
                    if ahora - last_alert >= ALERT_COOLDOWN:
                        # Construir y enviar el mensaje de alerta
                        mensaje = (
                            "⚠️ ALERTA: Proxmox NO responde\n"
                            f"Host: {PROXMOX_HOST}:{PROXMOX_PORT}\n"
                            f"Fallos consecutivos: {fail_count}\n"
                            f"Tiempo desde arranque: {time.time():.0f}s"
                        )
                        print("  -> Enviando alerta por Telegram …")
                        send_telegram(mensaje)

                        last_alert = ahora
                        fail_count = 0

                        # Pausa larga para no saturar de notificaciones
                        print(
                            f"  -> Pausa de {ALERT_COOLDOWN}s (10 min) "
                            f"para evitar spam …"
                        )
                        time.sleep(ALERT_COOLDOWN)
                        continue
                    else:
                        restante = int(ALERT_COOLDOWN - (ahora - last_alert))
                        print(
                            f"  -> En cooldown ({restante}s restantes), "
                            f"no se reenvía alerta."
                        )

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n[INFO] Monitor detenido por el usuario.")
            break
        except Exception as e:
            print(f"[ERROR] Excepción en bucle principal: {e}")
            time.sleep(CHECK_INTERVAL)


# Punto de entrada — en MicroPython main.py se ejecuta directamente al boot
main()
