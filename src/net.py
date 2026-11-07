"""net.py — peticion HTTPS minima, compartida por Proxmox y Telegram.

El certificado del servidor NO se verifica: Proxmox usa uno auto-firmado y
el firmware no trae un almacen de CAs. El trafico va cifrado igualmente,
pero un atacante en la red local podria suplantar al servidor (ver README).
"""
import socket
import gc

# Errores que indican "esta API no existe en este firmware" -> probar la
# siguiente estrategia. Un OSError (fallo de red/handshake) NO se reintenta:
# el socket queda en estado indefinido.
_API_ERRORS = (AttributeError, TypeError, NotImplementedError)


def wrap_tls(sock, hostname, ssl_mod=None):
    """Envuelve sock en TLS sin verificar el certificado.

    Nunca devuelve el socket en texto plano: si ninguna API de TLS esta
    disponible lanza OSError (asi el token de Telegram nunca viaja sin cifrar).
    """
    if ssl_mod is None:
        try:
            import ssl as ssl_mod
        except ImportError:
            raise OSError("TLS no disponible (sin modulo ssl)") from None
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


def write_all(stream, data):
    mv = memoryview(data)
    while len(mv):
        n = stream.write(mv)
        if not n:
            raise OSError("escritura fallida")
        mv = mv[n:]


def read_upto(stream, max_bytes):
    """Lee hasta max_bytes o EOF. Un cierre abrupto tras recibir datos vale."""
    resp = b""
    while len(resp) < max_bytes:
        try:
            chunk = stream.read(max_bytes - len(resp))
        except OSError:
            if resp:
                break
            raise
        if not chunk:
            break
        resp += chunk
    return resp


def https_request(host, port, request, max_bytes=256, timeout=10):
    """Envia request (bytes) por HTTPS y devuelve hasta max_bytes de respuesta."""
    s = None
    try:
        addr = socket.getaddrinfo(host, port)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(addr)
        s = wrap_tls(s, host)
        write_all(s, request)
        return read_upto(s, max_bytes)
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
