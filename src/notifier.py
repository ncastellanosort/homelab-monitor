"""notifier.py — mensajes y envio por Telegram."""
import net
from fmt import format_uptime, html_escape

# Emojis como code points reales (no bytes UTF-8 sueltos dentro de un str)
E_GREEN = "\U0001F7E2"
E_RED = "\U0001F534"
E_ANTENNA = "\U0001F4E1"
E_GLOBE = "\U0001F310"
E_PC = "\U0001F5A5"
E_TIMER = "⏱"
E_CROSS = "❌"

TELEGRAM_HOST = "api.telegram.org"


def url_encode(texto):
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


def build_request(token, chat_id, text):
    path = "/bot{0}/sendMessage".format(token)
    body = "chat_id={0}&text={1}&parse_mode=HTML".format(
        url_encode(chat_id), url_encode(text))
    return (
        "POST {0} HTTP/1.1\r\n"
        "Host: {1}\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        "Content-Length: {2}\r\n"
        "Connection: close\r\n"
        "\r\n"
        "{3}"
    ).format(path, TELEGRAM_HOST, len(body), body).encode()


def send(token, chat_id, text, timeout=10):
    """Envia text al chat. Devuelve True solo si Telegram responde 200."""
    try:
        resp = net.https_request(TELEGRAM_HOST, 443,
                                 build_request(token, chat_id, text), 128, timeout)
    except Exception as e:
        print("  [Telegram] Error de red: {0}".format(e))
        return False
    if net.parse_status(resp) == 200:
        print("  [Telegram] Mensaje enviado.")
        return True
    print("  [Telegram] Error: {0}".format(resp[:120]))
    return False
