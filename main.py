"""
main.py — Monitor de Proxmox con dashboard web para ESP32 + MicroPython

Unico archivo autónomo. Verifica Proxmox vía HTTPS, envía alertas
por Telegram y sirve un dashboard HTTP en el puerto 80.
"""
import network
import socket
import time
import gc


# ============================================================
# CONFIGURACION — ajusta estos valores a tu entorno
# ============================================================

WIFI_SSID     = "TU_SSID"
WIFI_PASSWORD = "TU_PASSWORD"

PROXMOX_HOST = "192.168.1.50"
PROXMOX_PORT = 8006

TELEGRAM_TOKEN = "TU_BOT_TOKEN"
TELEGRAM_CHAT_ID = "TU_CHAT_ID"

CHECK_INTERVAL  = 30
FAIL_THRESHOLD  = 3
ALERT_COOLDOWN  = 600
REQUEST_TIMEOUT = 10
WEB_PORT        = 80


# ============================================================
# WI-FI
# ============================================================

def wifi_connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        print("[WiFi] Ya conectado. IP: {0}".format(wlan.ifconfig()[0]))
        return True
    print("[WiFi] Conectando a '{0}' ...".format(WIFI_SSID))
    # Reintentar hasta 3 veces (cold-boot puede necesitar mas tiempo)
    for intento in range(1, 4):
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        for _ in range(15):
            if wlan.isconnected():
                print("[WiFi] Conectado. IP: {0}".format(wlan.ifconfig()[0]))
                return True
            time.sleep(1)
        print("[WiFi] Reintento {0}/3 ...".format(intento))
    print("[WiFi] ERROR: no se pudo conectar tras 3 intentos.")
    return False


def wifi_ensure():
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("[WiFi] Conexion perdida, reintentando ...")
        return wifi_connect()
    return True


def wifi_ip():
    wlan = network.WLAN(network.STA_IF)
    return wlan.ifconfig()[0] if wlan.isconnected() else ""


# ============================================================
# SSL helper (ignora certificados auto-firmados)
# ============================================================

def _ssl_no_verify(sock, hostname):
    try:
        import ssl as _ssl
    except ImportError:
        return sock
    CERT_NONE = getattr(_ssl, 'CERT_NONE', 0)
    for strat in [
        lambda: _ssl.wrap_socket(sock, server_hostname=hostname, cert_reqs=CERT_NONE),
        lambda: _ssl.wrap_socket(sock, cert_reqs=CERT_NONE),
        lambda: _ssl.wrap_socket(sock, server_hostname=hostname),
        lambda: _ssl.wrap_socket(sock),
    ]:
        try:
            return strat()
        except (OSError, AttributeError, TypeError, ValueError):
            continue
    return sock


# ============================================================
# PROXMOX — chequeo HTTPS
# ============================================================

def proxmox_check():
    s = None
    try:
        addr = socket.getaddrinfo(PROXMOX_HOST, PROXMOX_PORT)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(REQUEST_TIMEOUT)
        s.connect(addr)
        s = _ssl_no_verify(s, PROXMOX_HOST)
        req = "GET / HTTP/1.1\r\nHost: {0}:{1}\r\nConnection: close\r\n\r\n".format(
            PROXMOX_HOST, PROXMOX_PORT)
        s.write(req.encode())
        data = s.read(256)
        return len(data) > 0
    except OSError as e:
        print("  [Proxmox] Error de red: {0}".format(e))
        return False
    except Exception as e:
        print("  [Proxmox] Error: {0}".format(e))
        return False
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
        gc.collect()


# ============================================================
# TELEGRAM — alertas
# ============================================================

def _format_uptime(seconds):
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    parts = []
    if h > 0:
        parts.append("{0}h".format(h))
    if m > 0:
        parts.append("{0}m".format(m))
    parts.append("{0}s".format(sec))
    return " ".join(parts)


def _url_encode(texto):
    seguros = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.~-"
    res = []
    for c in texto:
        if c in seguros:
            res.append(c)
        elif c == ' ':
            res.append('+')
        else:
            for b in c.encode('utf-8'):
                res.append('%{:02X}'.format(b))
    return ''.join(res)


def telegram_send(mensaje):
    host = "api.telegram.org"
    path = "/bot{0}/sendMessage".format(TELEGRAM_TOKEN)
    body = "chat_id={0}&text={1}&parse_mode=HTML".format(TELEGRAM_CHAT_ID, _url_encode(mensaje))

    s = None
    try:
        addr = socket.getaddrinfo(host, 443)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(REQUEST_TIMEOUT)
        s.connect(addr)
        s = _ssl_no_verify(s, host)
        req = (
            "POST {0} HTTP/1.1\r\n"
            "Host: {1}\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            "Content-Length: {2}\r\n"
            "Connection: close\r\n"
            "\r\n"
            "{3}"
        ).format(path, host, len(body), body)
        s.write(req.encode())
        resp = s.read(512)
        if b"200 OK" in resp:
            print("  [Telegram] Alerta enviada.")
            return True
        else:
            print("  [Telegram] Error: {0}".format(resp[:120]))
            return False
    except OSError as e:
        print("  [Telegram] Error de red: {0}".format(e))
        return False
    except Exception as e:
        print("  [Telegram] Error: {0}".format(e))
        return False
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
        gc.collect()


# ============================================================
# SERVIDOR WEB — dashboard no bloqueante
# ============================================================

def _web_render(state):
    host = "{0}:{1}".format(PROXMOX_HOST, PROXMOX_PORT)
    if state["proxmox_online"]:
        dot, txt, clr = "#22c55e", "ONLINE", "#22c55e"
    else:
        dot, txt, clr = "#ef4444", "OFFLINE", "#ef4444"

    if state["last_alert"] == 0:
        last = "Nunca"
    else:
        d = int(time.time() - state["last_alert"])
        if d < 60:
            last = "hace {0}s".format(d)
        elif d < 3600:
            last = "hace {0}min".format(d // 60)
        else:
            last = "hace {0}h {1}min".format(d // 3600, (d % 3600) // 60)

    CRLF = "\r\n"
    body = (
        "<!DOCTYPE html>"
        "<html lang=\"es\">"
        "<head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta http-equiv=\"refresh\" content=\"30\">"
        "<title>Proxmox Monitor</title>"
        "<style>"
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{font-family:system-ui,sans-serif;background:#1a1a1a;color:#f0f0f0;"
        "display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}"
        ".card{max-width:400px;width:100%;text-align:center}"
        "h1{font-size:1.2rem;font-weight:600;margin-bottom:20px;color:#999}"
        ".dot{display:inline-block;width:16px;height:16px;border-radius:50%;"
        "background:" + dot + ";margin-right:8px;vertical-align:middle}"
        ".status{font-size:2rem;font-weight:800;color:" + clr + ";margin:8px 0 20px}"
        ".info{margin-bottom:20px}"
        ".row{display:flex;justify-content:space-between;padding:6px 0;"
        "border-bottom:1px solid #333}"
        ".lbl{color:#888;font-size:.85rem}"
        ".val{color:#f0f0f0;font-size:.85rem;font-weight:500}"
        ".bar{margin-top:16px;font-size:.7rem;color:#666}"
        "</style>"
        "</head>"
        "<body>"
        "<div class=\"card\">"
        "<h1>Proxmox Monitor</h1>"
        "<div><span class=\"dot\"></span><span class=\"status\">" + txt + "</span></div>"
        "<div class=\"info\">"
        "<div class=\"row\"><span class=\"lbl\">Host</span>"
        "<span class=\"val\">" + host + "</span></div>"
        "<div class=\"row\"><span class=\"lbl\">Fallos</span>"
        "<span class=\"val\">" + str(state["fail_count"]) + "/" + str(FAIL_THRESHOLD) + "</span></div>"
        "<div class=\"row\"><span class=\"lbl\">Alerta</span>"
        "<span class=\"val\">" + last + "</span></div>"
        "<div class=\"row\"><span class=\"lbl\">WiFi</span>"
        "<span class=\"val\">" + state["wifi_ip"] + "</span></div>"
        "</div>"
        "<div class=\"bar\">uptime " + _format_uptime(int(state["uptime"])) +
        " &mdash; auto-refresh 30s</div>"
        "</div>"
        "</body>"
        "</html>"
    )

    return "HTTP/1.0 200 OK" + CRLF + \
           "Content-Type: text/html; charset=utf-8" + CRLF + \
           "Connection: close" + CRLF + CRLF + body


def _web_start():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", WEB_PORT))
        s.listen(2)
        s.settimeout(1)
        print("[Web] Dashboard en http://{0}:{1}/".format(wifi_ip(), WEB_PORT))
        return s
    except OSError as e:
        print("[Web] Error al iniciar: {0}".format(e))
        return None


def _web_serve(state, server_sock):
    if server_sock is None:
        return
    try:
        client, _ = server_sock.accept()
    except OSError:
        return
    try:
        # Leer con recv() en vez de read() — mas fiable en algunas builds
        client.settimeout(5)
        request = client.recv(512)
        if not request or len(request) == 0:
            # Si recv devuelve vacio, reintentar una vez
            request = client.recv(512)
        if request and b"GET /" in request:
            state["uptime"] = time.time()
            response = _web_render(state)
            client.sendall(response.encode())
    except Exception:
        pass
    finally:
        try:
            client.close()
        except Exception:
            pass


# ============================================================
# BUCLE PRINCIPAL
# ============================================================

def main():
    print("\n=== Proxmox Monitor v3 ===")
    print("Host: {0}:{1}  |  Intervalo: {2}s".format(
        PROXMOX_HOST, PROXMOX_PORT, CHECK_INTERVAL))
    print("Dashboard: http://<IP>:{0}/".format(WEB_PORT))
    print("=" * 40 + "\n")

    if not wifi_connect():
        print("[FATAL] Sin Wi-Fi.")
        return

    state = {
        "proxmox_online": True,
        "fail_count": 0,
        "last_alert": 0,
        "uptime": 0,
        "wifi_ip": wifi_ip(),
        "recovery_pending": False,
    }

    server_sock = _web_start()

    # Notificar arranque por Telegram
    uptime_str = _format_uptime(int(time.time()))
    boot_msg = (
        "\xf0\x9f\x9f\xa2 <b>ESP32 Monitor ONLINE</b>\n"
        "<i>Sistema iniciado correctamente</i>\n"
        "\n"
        "\xf0\x9f\x93\xa1 <b>WiFi:</b> {0}\n"
        "\xf0\x9f\x8c\x90 <b>Dashboard:</b> <code>http://{0}:{1}/</code>\n"
        "\xf0\x9f\x96\xa5 <b>Proxmox:</b> <code>{2}:{3}</code>\n"
        "\xe2\x8f\xb1 <b>Uptime:</b> {4}"
    ).format(state["wifi_ip"], WEB_PORT, PROXMOX_HOST, PROXMOX_PORT, uptime_str)
    print("[Boot] Enviando notificacion a Telegram ...")
    telegram_send(boot_msg)

    last_check = 0
    while True:
        try:
            if not wifi_ensure():
                _web_serve(state, server_sock)
                time.sleep(1)
                continue

            state["wifi_ip"] = wifi_ip()
            now = time.time()

            # Chequeo de Proxmox (respeta cooldown tras alerta)
            in_cooldown = (
                state["last_alert"] > 0 and
                now - state["last_alert"] < ALERT_COOLDOWN
            )

            if not in_cooldown and now - last_check >= CHECK_INTERVAL:
                last_check = now
                print("[{0:.0f}] Verificando Proxmox ...".format(now), end="")

                if proxmox_check():
                    print(" OK")
                    state["proxmox_online"] = True

                    # Alerta de recuperacion: Proxmox volvio tras una caida
                    if state["recovery_pending"]:
                        uptime_str = _format_uptime(int(now))
                        recover_msg = (
                            "\xf0\x9f\x9f\xa2 <b>Proxmox RECUPERADO</b>\n"
                            "<i>El servidor responde nuevamente</i>\n"
                            "\n"
                            "\xf0\x9f\x96\xa5 <b>Host:</b> <code>{0}:{1}</code>\n"
                            "\xe2\x8f\xb1 <b>Uptime:</b> {2}\n"
                            "\n"
                            "\xf0\x9f\x8c\x90 <b>Dashboard:</b> <code>http://{3}/</code>"
                        ).format(PROXMOX_HOST, PROXMOX_PORT, uptime_str, state["wifi_ip"])
                        print("  -> Enviando alerta de recuperacion ...")
                        telegram_send(recover_msg)
                        state["recovery_pending"] = False

                    if state["fail_count"] > 0:
                        print("  -> Contador reiniciado (era {0})".format(state["fail_count"]))
                    state["fail_count"] = 0
                else:
                    state["fail_count"] += 1
                    state["proxmox_online"] = False
                    print(" FALLO ({0}/{1})".format(state["fail_count"], FAIL_THRESHOLD))

                    if state["fail_count"] >= FAIL_THRESHOLD:
                        uptime_str = _format_uptime(int(now))
                        msg = (
                            "\xf0\x9f\x94\xb4 <b>ALERTA: Proxmox NO responde</b>\n"
                            "\n"
                            "\xf0\x9f\x96\xa5 <b>Host:</b> <code>{0}:{1}</code>\n"
                            "\xe2\x9d\x8c <b>Fallos consecutivos:</b> {2}\n"
                            "\xe2\x8f\xb1 <b>Uptime:</b> {3}\n"
                            "\n"
                            "\xf0\x9f\x8c\x90 <b>Dashboard:</b> <code>http://{4}/</code>"
                        ).format(PROXMOX_HOST, PROXMOX_PORT,
                                 state["fail_count"], uptime_str, state["wifi_ip"])
                        print("  -> Enviando alerta ...")
                        telegram_send(msg)
                        state["last_alert"] = now
                        state["recovery_pending"] = True
                        state["fail_count"] = 0
                        print("  -> Cooldown {0}s ({1} min)".format(
                            ALERT_COOLDOWN, ALERT_COOLDOWN // 60))

            # Servir HTTP (no bloqueante, timeout 1s)
            _web_serve(state, server_sock)

        except KeyboardInterrupt:
            print("\n[INFO] Monitor detenido.")
            break
        except Exception as e:
            print("[ERROR] {0}".format(e))
            deadline = time.time() + CHECK_INTERVAL
            while time.time() < deadline:
                _web_serve(state, server_sock)


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

# ── Arranque desde cold-boot ──
# Delay para asegurar que el hardware este listo
time.sleep(3)

# Ejecutar el monitor (captura errores para dejar REPL accesible)
try:
    main()
except Exception as e:
    import sys
    print("[FATAL] main() fallo:")
    sys.print_exception(e)
    # REPL queda libre para debug
