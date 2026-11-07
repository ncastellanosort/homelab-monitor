"""proxmox.py — chequeo de disponibilidad por HTTPS."""
import net


def is_up(status):
    """Proxmox responde si devuelve una respuesta HTTP valida por debajo de 500."""
    return status is not None and status < 500


def check(host, port, timeout=10):
    """Devuelve (ok, detalle)."""
    req = "GET / HTTP/1.1\r\nHost: {0}:{1}\r\nConnection: close\r\n\r\n".format(
        host, port).encode()
    try:
        status = net.parse_status(net.https_request(host, port, req, 64, timeout))
    except OSError as e:
        return False, "error de red: {0}".format(e)
    except Exception as e:
        return False, "error: {0}".format(e)
    if status is None:
        return False, "respuesta no HTTP"
    return is_up(status), "HTTP {0}".format(status)
