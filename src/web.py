"""web.py — dashboard HTTP no bloqueante.

Rutas:  GET /             dashboard HTML
        GET /api/status   estado en JSON
        resto             404 (405 si no es GET, 400 si la peticion es invalida)
"""
import json
import socket
import time
from fmt import format_ago, format_uptime, html_escape

REASONS = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}
HTML = "text/html; charset=utf-8"
JSON = "application/json"
TEXT = "text/plain; charset=utf-8"


def _row(label, value):
    return ("<div class=\"row\"><span class=\"lbl\">" + label + "</span>"
            "<span class=\"val\">" + value + "</span></div>")


def _telegram_text(st):
    if not st["telegram_enabled"]:
        return "sin configurar"
    if st["telegram_last_ok"] is None:
        return "sin envios"
    return "OK" if st["telegram_last_ok"] else "ERROR en el ultimo envio"


def render_html(st):
    """HTML del dashboard a partir del dict de estado de App.status()."""
    if st["online"] is None:
        clr, txt = "#9ca3af", "DESCONOCIDO"
    elif st["online"]:
        clr, txt = "#22c55e", "ONLINE"
    else:
        clr, txt = "#ef4444", "OFFLINE"

    if st["last_check_ago_s"] is None:
        check = "pendiente"
    else:
        check = html_escape(st["detail"]) + " &middot; " + format_ago(st["last_check_ago_s"])

    warnings = ""
    for p in st["warnings"]:
        warnings += ("<div style=\"color:#f59e0b;font-size:.8rem;margin:4px 0\">"
                     "&#9888; " + html_escape(p) + "</div>")

    return (
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
        ".row{display:flex;justify-content:space-between;gap:12px;padding:6px 0;"
        "border-bottom:1px solid #333}"
        ".lbl{color:#888;font-size:.85rem}"
        ".val{color:#f0f0f0;font-size:.85rem;font-weight:500;text-align:right}"
        ".bar{margin-top:16px;font-size:.7rem;color:#666}"
        "</style>"
        "</head>"
        "<body>"
        "<div class=\"card\">"
        "<h1>Proxmox Monitor</h1>"
        "<div><span class=\"dot\"></span><span class=\"status\">" + txt + "</span></div>"
        "<div class=\"info\">" +
        _row("Host", html_escape(st["host"])) +
        _row("Fallos", str(st["fail_count"]) + "/" + str(st["fail_threshold"])) +
        _row("Chequeo", check) +
        _row("Alerta", format_ago(st["last_alert_ago_s"])) +
        _row("Telegram", _telegram_text(st)) +
        _row("WiFi", html_escape(st["wifi_ip"]) + (" (fija)" if st.get("wifi_static") else "")) +
        "</div>" + warnings +
        "<div class=\"bar\">v" + html_escape(st["version"]) + " &mdash; uptime " +
        format_uptime(st["uptime_s"]) + " &mdash; auto-refresh 30s"
        " &mdash; <a href=\"/api/status\" style=\"color:#666\">JSON</a></div>"
        "</div>"
        "</body>"
        "</html>"
    )


def route(request, get_status):
    """Devuelve (codigo, content_type, cuerpo) para una peticion HTTP en bytes."""
    parts = request.split(b"\r\n", 1)[0].split(b" ")
    if len(parts) != 3 or not parts[2].startswith(b"HTTP/"):
        return 400, TEXT, "Bad Request\n"
    method = parts[0]
    path = parts[1].split(b"?", 1)[0]
    if method != b"GET":
        return 405, TEXT, "Method Not Allowed\n"
    if path == b"/":
        return 200, HTML, render_html(get_status())
    if path == b"/api/status":
        return 200, JSON, json.dumps(get_status())
    return 404, TEXT, "Not Found\n"


def build_response(code, ctype, body):
    data = body.encode()
    head = ("HTTP/1.0 {0} {1}\r\n"
            "Content-Type: {2}\r\n"
            "Content-Length: {3}\r\n"
            "{4}"
            "Connection: close\r\n\r\n").format(
        code, REASONS.get(code, ""), ctype, len(data),
        "Allow: GET\r\n" if code == 405 else "")
    return head.encode() + data


def start(port, ip=""):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        s.listen(2)
        s.settimeout(1)
        print("[Web] Dashboard en http://{0}:{1}/".format(ip, port))
        return s
    except OSError as e:
        print("[Web] Error al iniciar: {0}".format(e))
        return None


def serve(server_sock, get_status):
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
        if request:
            client.sendall(build_response(*route(request, get_status)))
    except Exception:
        pass
    finally:
        try:
            client.close()
        except Exception:
            pass
