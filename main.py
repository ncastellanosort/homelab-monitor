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
# CONFIGURACION — los valores sensibles se leen de .env
# (ver .env.example; subirlo con: mpremote cp .env :.env)
# ============================================================

def _load_env(path=".env"):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                env[key] = val
    except OSError:
        print("[Config] AVISO: no se encontro {0}, usando placeholders.".format(path))
    return env


_ENV = _load_env()

WIFI_SSID     = _ENV.get("WIFI_SSID", "TU_SSID")
WIFI_PASSWORD = _ENV.get("WIFI_PASSWORD", "TU_PASSWORD")

PROXMOX_HOST = _ENV.get("PROXMOX_HOST", "192.168.1.50")
PROXMOX_PORT = int(_ENV.get("PROXMOX_PORT", "8006"))

TELEGRAM_TOKEN   = _ENV.get("TELEGRAM_TOKEN", "TU_BOT_TOKEN")
TELEGRAM_CHAT_ID = _ENV.get("TELEGRAM_CHAT_ID", "TU_CHAT_ID")

del _ENV

CHECK_INTERVAL  = 30    # segundos entre chequeos
FAIL_THRESHOLD  = 3     # fallos consecutivos para alertar
ALERT_COOLDOWN  = 600   # segundos minimos entre alertas de caida repetidas
REQUEST_TIMEOUT = 10
WEB_PORT        = 80

VERSION = "1.2.0"


# ============================================================
# RELOJ — milisegundos desde el arranque, sin desbordes
# ============================================================

class Clock:
    """Acumula time.ticks_diff() para obtener ms monotonicos desde el arranque.

    ticks_ms() da la vuelta cada ~12 dias; acumulando diferencias cortas el
    contador nunca se desborda y no depende del RTC (ni de NTP).
    """

    def __init__(self):
        self._last = time.ticks_ms()
        self._ms = 0

    def now_ms(self):
        t = time.ticks_ms()
        self._ms += time.ticks_diff(t, self._last)
        self._last = t
        return self._ms


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
# NET — peticion HTTPS minima (sin verificar certificado)
# ============================================================

# Errores que indican "esta API no existe en este firmware" -> probar la
# siguiente estrategia. Un OSError (fallo de red/handshake) NO se reintenta:
# el socket queda en estado indefinido.
_API_ERRORS = (AttributeError, TypeError, NotImplementedError)


def _wrap_tls(sock, hostname, ssl_mod=None):
    """Envuelve sock en TLS sin verificar el certificado.

    Nunca devuelve el socket en texto plano: si ninguna API de TLS esta
    disponible lanza OSError (asi el token de Telegram nunca viaja sin cifrar).
    """
    if ssl_mod is None:
        try:
            import ssl as ssl_mod
        except ImportError:
            raise OSError("TLS no disponible (sin modulo ssl)")
    cert_none = getattr(ssl_mod, "CERT_NONE", 0)

    def via_context():
        ctx = ssl_mod.SSLContext(ssl_mod.PROTOCOL_TLS_CLIENT)
        if hasattr(ctx, "check_hostname"):
            ctx.check_hostname = False
        ctx.verify_mode = cert_none
        return ctx.wrap_socket(sock, server_hostname=hostname)

    strategies = (
        via_context,
        lambda: ssl_mod.wrap_socket(sock, server_hostname=hostname, cert_reqs=cert_none),
        lambda: ssl_mod.wrap_socket(sock, server_hostname=hostname),
        lambda: ssl_mod.wrap_socket(sock),
    )
    for strat in strategies:
        try:
            return strat()
        except _API_ERRORS:
            continue
    raise OSError("TLS no disponible en este firmware")


def _write_all(stream, data):
    mv = memoryview(data)
    while len(mv):
        n = stream.write(mv)
        if not n:
            raise OSError("escritura TLS fallida")
        mv = mv[n:]


def https_request(host, port, request, max_bytes=256, timeout=REQUEST_TIMEOUT):
    """Envia request (bytes) por HTTPS y devuelve hasta max_bytes de respuesta."""
    s = None
    try:
        addr = socket.getaddrinfo(host, port)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(addr)
        s = _wrap_tls(s, host)
        _write_all(s, request)
        resp = b""
        while len(resp) < max_bytes:
            try:
                chunk = s.read(max_bytes - len(resp))
            except OSError:
                if resp:
                    break   # cierre abrupto tras recibir datos: nos vale
                raise
            if not chunk:
                break
            resp += chunk
        return resp
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
        gc.collect()


def parse_status(resp):
    """Codigo HTTP de la linea de estado, o None si no es una respuesta HTTP."""
    if not resp or not resp.startswith(b"HTTP/1."):
        return None
    parts = resp.split(b"\r\n", 1)[0].split(b" ")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


# ============================================================
# PROXMOX — chequeo HTTPS
# ============================================================

def proxmox_check():
    """Devuelve (ok, detalle). OK solo con una respuesta HTTP valida < 500."""
    req = "GET / HTTP/1.1\r\nHost: {0}:{1}\r\nConnection: close\r\n\r\n".format(
        PROXMOX_HOST, PROXMOX_PORT).encode()
    try:
        status = parse_status(https_request(PROXMOX_HOST, PROXMOX_PORT, req, 64))
    except OSError as e:
        return False, "error de red: {0}".format(e)
    except Exception as e:
        return False, "error: {0}".format(e)
    if status is None:
        return False, "respuesta no HTTP"
    return status < 500, "HTTP {0}".format(status)


# ============================================================
# FORMATO
# ============================================================

def format_uptime(seconds):
    s = int(seconds)
    d = s // 86400
    h = (s % 86400) // 3600
    m = (s % 3600) // 60
    sec = s % 60
    parts = []
    if d > 0:
        parts.append("{0}d".format(d))
    if h > 0:
        parts.append("{0}h".format(h))
    if m > 0:
        parts.append("{0}m".format(m))
    parts.append("{0}s".format(sec))
    return " ".join(parts)


def format_ago(seconds):
    if seconds is None:
        return "Nunca"
    d = int(seconds)
    if d < 60:
        return "hace {0}s".format(d)
    if d < 3600:
        return "hace {0}min".format(d // 60)
    return "hace {0}h {1}min".format(d // 3600, (d % 3600) // 60)


def html_escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ============================================================
# TELEGRAM — alertas
# ============================================================

# Emojis como code points reales (no bytes UTF-8 sueltos dentro de un str)
E_GREEN = "\U0001F7E2"
E_RED = "\U0001F534"
E_ANTENNA = "\U0001F4E1"
E_GLOBE = "\U0001F310"
E_PC = "\U0001F5A5"
E_TIMER = "⏱"
E_CROSS = "❌"


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


def msg_boot(ip, web_port, host, port, uptime_s):
    return (
        E_GREEN + " <b>ESP32 Monitor ONLINE</b>\n"
        "<i>Sistema iniciado correctamente</i>\n"
        "\n" +
        E_ANTENNA + " <b>WiFi:</b> {0}\n" +
        E_GLOBE + " <b>Dashboard:</b> <code>http://{0}:{1}/</code>\n" +
        E_PC + " <b>Proxmox:</b> <code>{2}:{3}</code>\n" +
        E_TIMER + " <b>Uptime:</b> {4}"
    ).format(ip, web_port, html_escape(host), port, format_uptime(uptime_s))


def msg_down(host, port, fails, uptime_s, ip):
    return (
        E_RED + " <b>ALERTA: Proxmox NO responde</b>\n"
        "\n" +
        E_PC + " <b>Host:</b> <code>{0}:{1}</code>\n" +
        E_CROSS + " <b>Fallos consecutivos:</b> {2}\n" +
        E_TIMER + " <b>Uptime:</b> {3}\n"
        "\n" +
        E_GLOBE + " <b>Dashboard:</b> <code>http://{4}/</code>"
    ).format(html_escape(host), port, fails, format_uptime(uptime_s), ip)


def msg_recovery(host, port, uptime_s, ip):
    return (
        E_GREEN + " <b>Proxmox RECUPERADO</b>\n"
        "<i>El servidor responde nuevamente</i>\n"
        "\n" +
        E_PC + " <b>Host:</b> <code>{0}:{1}</code>\n" +
        E_TIMER + " <b>Uptime:</b> {2}\n"
        "\n" +
        E_GLOBE + " <b>Dashboard:</b> <code>http://{3}/</code>"
    ).format(html_escape(host), port, format_uptime(uptime_s), ip)


def telegram_send(mensaje):
    host = "api.telegram.org"
    path = "/bot{0}/sendMessage".format(TELEGRAM_TOKEN)
    body = "chat_id={0}&text={1}&parse_mode=HTML".format(
        _url_encode(TELEGRAM_CHAT_ID), _url_encode(mensaje))
    req = (
        "POST {0} HTTP/1.1\r\n"
        "Host: {1}\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        "Content-Length: {2}\r\n"
        "Connection: close\r\n"
        "\r\n"
        "{3}"
    ).format(path, host, len(body), body).encode()
    try:
        resp = https_request(host, 443, req, 128)
    except Exception as e:
        print("  [Telegram] Error de red: {0}".format(e))
        return False
    if parse_status(resp) == 200:
        print("  [Telegram] Mensaje enviado.")
        return True
    print("  [Telegram] Error: {0}".format(resp[:120]))
    return False


# ============================================================
# MONITOR — maquina de estados (sin I/O)
# ============================================================

DOWN = "down"
RECOVERY = "recovery"


class Monitor:
    """Decide cuando chequear y que alertas enviar. Tiempos en ms.

    - Los chequeos siguen su cadencia aunque se haya enviado una alerta.
    - fail_count = fallos consecutivos reales; solo se reinicia con un OK.
    - La alerta de caida se repite como recordatorio cada alert_cooldown
      mientras Proxmox siga caido.
    - Un envio fallido no se da por hecho: se reintenta en el siguiente chequeo.
    """

    def __init__(self, check_interval_ms, fail_threshold, alert_cooldown_ms):
        self.check_interval_ms = check_interval_ms
        self.fail_threshold = fail_threshold
        self.alert_cooldown_ms = alert_cooldown_ms
        self.online = None          # None = aun no se ha comprobado
        self.fail_count = 0
        self.detail = ""
        self.last_check_ms = None
        self.last_alert_ms = None   # ultima alerta de caida ENTREGADA
        self.outage_alerted = False  # se aviso esta caida -> falta la recuperacion

    def due(self, now_ms):
        return (self.last_check_ms is None or
                now_ms - self.last_check_ms >= self.check_interval_ms)

    def on_check(self, ok, now_ms, detail=""):
        """Registra un chequeo y devuelve el evento a notificar (o None)."""
        self.last_check_ms = now_ms
        self.detail = detail
        if ok:
            self.online = True
            self.fail_count = 0
            return RECOVERY if self.outage_alerted else None
        self.online = False
        self.fail_count += 1
        if self.fail_count < self.fail_threshold:
            return None
        if not self.outage_alerted:
            return DOWN
        if now_ms - self.last_alert_ms >= self.alert_cooldown_ms:
            return DOWN
        return None

    def on_sent(self, event, delivered, now_ms):
        if not delivered:
            return
        if event == DOWN:
            self.outage_alerted = True
            self.last_alert_ms = now_ms
        elif event == RECOVERY:
            self.outage_alerted = False


# ============================================================
# SERVIDOR WEB — dashboard no bloqueante
# ============================================================

def _web_render(st):
    host = html_escape("{0}:{1}".format(PROXMOX_HOST, PROXMOX_PORT))
    if st["online"] is None:
        clr, txt = "#9ca3af", "DESCONOCIDO"
    elif st["online"]:
        clr, txt = "#22c55e", "ONLINE"
    else:
        clr, txt = "#ef4444", "OFFLINE"

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
        "background:" + clr + ";margin-right:8px;vertical-align:middle}"
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
        "<span class=\"val\">" + str(st["fail_count"]) + "/" + str(FAIL_THRESHOLD) + "</span></div>"
        "<div class=\"row\"><span class=\"lbl\">Alerta</span>"
        "<span class=\"val\">" + format_ago(st["last_alert_ago_s"]) + "</span></div>"
        "<div class=\"row\"><span class=\"lbl\">WiFi</span>"
        "<span class=\"val\">" + st["wifi_ip"] + "</span></div>"
        "</div>"
        "<div class=\"bar\">v" + VERSION + " &mdash; uptime " + format_uptime(st["uptime_s"]) +
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


def _web_serve(get_status, server_sock):
    """Atiende como mucho una peticion. Bloquea ~1s (o duerme 1s sin socket)."""
    if server_sock is None:
        time.sleep(1)   # evita un bucle al 100% de CPU si el servidor no arranco
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
            response = _web_render(get_status())
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

def _notify(mon, event, now_ms, uptime_s, ip):
    if event == DOWN:
        print("  -> Enviando alerta de caida ...")
        text = msg_down(PROXMOX_HOST, PROXMOX_PORT, mon.fail_count, uptime_s, ip)
    else:
        print("  -> Enviando alerta de recuperacion ...")
        text = msg_recovery(PROXMOX_HOST, PROXMOX_PORT, uptime_s, ip)
    delivered = telegram_send(text)
    mon.on_sent(event, delivered, now_ms)
    if not delivered:
        print("  -> No entregada; se reintentara en el proximo chequeo.")


def main():
    print("\n=== Proxmox Monitor v{0} ===".format(VERSION))
    print("Host: {0}:{1}  |  Intervalo: {2}s".format(
        PROXMOX_HOST, PROXMOX_PORT, CHECK_INTERVAL))
    print("Dashboard: http://<IP>:{0}/".format(WEB_PORT))
    print("=" * 40 + "\n")

    clock = Clock()

    if not wifi_connect():
        print("[FATAL] Sin Wi-Fi.")
        return

    mon = Monitor(CHECK_INTERVAL * 1000, FAIL_THRESHOLD, ALERT_COOLDOWN * 1000)
    ip = wifi_ip()

    def get_status():
        now = clock.now_ms()
        return {
            "online": mon.online,
            "fail_count": mon.fail_count,
            "last_alert_ago_s": (None if mon.last_alert_ms is None
                                 else (now - mon.last_alert_ms) // 1000),
            "wifi_ip": wifi_ip(),
            "uptime_s": now // 1000,
        }

    server_sock = _web_start()

    print("[Boot] Enviando notificacion a Telegram ...")
    telegram_send(msg_boot(ip, WEB_PORT, PROXMOX_HOST, PROXMOX_PORT,
                           clock.now_ms() // 1000))

    while True:
        try:
            if not wifi_ensure():
                _web_serve(get_status, server_sock)
                continue

            ip = wifi_ip()
            now = clock.now_ms()

            if mon.due(now):
                print("[{0}] Verificando Proxmox ...".format(format_uptime(now // 1000)), end="")
                ok, detail = proxmox_check()
                event = mon.on_check(ok, now, detail)
                if ok:
                    print(" OK ({0})".format(detail))
                else:
                    print(" FALLO {0}/{1} ({2})".format(
                        mon.fail_count, FAIL_THRESHOLD, detail))
                if event is not None:
                    _notify(mon, event, clock.now_ms(), now // 1000, ip)

            # Servir HTTP (no bloqueante, timeout 1s)
            _web_serve(get_status, server_sock)

        except KeyboardInterrupt:
            print("\n[INFO] Monitor detenido.")
            break
        except Exception as e:
            print("[ERROR] {0}".format(e))
            time.sleep(1)


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
