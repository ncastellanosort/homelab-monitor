"""web.py — dashboard HTTP no bloqueante."""
import socket
import time
from fmt import format_ago, format_uptime, html_escape


def render_html(st):
    """HTML del dashboard a partir del dict de estado de app.status()."""
    if st["online"] is None:
        clr, txt = "#9ca3af", "DESCONOCIDO"
    elif st["online"]:
        clr, txt = "#22c55e", "ONLINE"
    else:
        clr, txt = "#ef4444", "OFFLINE"

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
        "<span class=\"val\">" + html_escape(st["host"]) + "</span></div>"
        "<div class=\"row\"><span class=\"lbl\">Fallos</span>"
        "<span class=\"val\">" + str(st["fail_count"]) + "/" +
        str(st["fail_threshold"]) + "</span></div>"
        "<div class=\"row\"><span class=\"lbl\">Alerta</span>"
        "<span class=\"val\">" + format_ago(st["last_alert_ago_s"]) + "</span></div>"
        "<div class=\"row\"><span class=\"lbl\">WiFi</span>"
        "<span class=\"val\">" + html_escape(st["wifi_ip"]) + "</span></div>"
        "</div>" + warnings +
        "<div class=\"bar\">v" + st["version"] + " &mdash; uptime " +
        format_uptime(st["uptime_s"]) + " &mdash; auto-refresh 30s</div>"
        "</div>"
        "</body>"
        "</html>"
    )


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
        if request and b"GET /" in request:
            response = ("HTTP/1.0 200 OK\r\n"
                        "Content-Type: text/html; charset=utf-8\r\n"
                        "Connection: close\r\n\r\n" + render_html(get_status()))
            client.sendall(response.encode())
    except Exception:
        pass
    finally:
        try:
            client.close()
        except Exception:
            pass
