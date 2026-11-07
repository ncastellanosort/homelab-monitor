import net
import proxmox
import pytest


@pytest.mark.parametrize("resp,code", [
    (b"HTTP/1.1 200 OK\r\nServer: pve\r\n", 200),
    (b"HTTP/1.0 501 Not Implemented\r\n", 501),
    (b"HTTP/1.1 301\r\n", 301),
    (b"", None),
    (b"\x15\x03\x03\x00\x02", None),          # alerta TLS, no HTTP
    (b"SSH-2.0-OpenSSH\r\n", None),
    (b"HTTP/1.1 abc\r\n", None),
])
def test_parse_status(resp, code):
    assert net.parse_status(resp) == code


@pytest.mark.parametrize("status,up", [
    (200, True), (401, True), (404, True), (499, True),
    (500, False), (503, False), (None, False),
])
def test_proxmox_is_up(status, up):   # B5
    assert proxmox.is_up(status) is up


class _Sock:
    pass


class _SSLWrap:
    """ssl estilo MicroPython antiguo: solo wrap_socket sin server_hostname."""
    CERT_NONE = 0

    def wrap_socket(self, sock, **kw):
        if kw:
            raise TypeError("unexpected keyword")
        return ("tls", sock)


class _SSLContextOK:
    """ssl estilo CPython / MicroPython >= 1.21."""
    CERT_NONE = 0
    PROTOCOL_TLS_CLIENT = 16

    class SSLContext:
        def __init__(self, proto):
            self.check_hostname = True
            self.verify_mode = 2

        def wrap_socket(self, sock, server_hostname=None):
            assert self.check_hostname is False and self.verify_mode == 0
            return ("ctx", sock, server_hostname)


class _SSLHandshakeFails(_SSLContextOK):
    class SSLContext(_SSLContextOK.SSLContext):
        def wrap_socket(self, sock, server_hostname=None):
            raise OSError(-29312)   # error de mbedTLS


def test_wrap_tls_prefers_context():
    sock = _Sock()
    assert net.wrap_tls(sock, "h", _SSLContextOK()) == ("ctx", sock, "h")


def test_wrap_tls_falls_back_on_api_errors():
    sock = _Sock()
    assert net.wrap_tls(sock, "h", _SSLWrap()) == ("tls", sock)


def test_wrap_tls_never_returns_plaintext():   # S1
    with pytest.raises(OSError):
        net.wrap_tls(_Sock(), "h", object())


def test_wrap_tls_does_not_retry_after_handshake_error():
    with pytest.raises(OSError):
        net.wrap_tls(_Sock(), "h", _SSLHandshakeFails())


class _Stream:
    def __init__(self, chunks, error_after=False, max_write=3):
        self.chunks = list(chunks)
        self.error_after = error_after
        self.written = b""
        self.max_write = max_write

    def read(self, n):
        if self.chunks:
            return self.chunks.pop(0)[:n]
        if self.error_after:
            raise OSError(-30848)   # close_notify abrupto
        return b""

    def write(self, data):
        part = bytes(data[: self.max_write])
        self.written += part
        return len(part)


def test_write_all_handles_partial_writes():
    s = _Stream([])
    net.write_all(s, b"hello world")
    assert s.written == b"hello world"


def test_read_upto_limits_and_eof():
    assert net.read_upto(_Stream([b"abc", b"def", b"ghi"]), 5) == b"abcde"
    assert net.read_upto(_Stream([b"ab"]), 10) == b"ab"


def test_read_upto_tolerates_abrupt_close_after_data():
    assert net.read_upto(_Stream([b"HTTP/1.1 200"], error_after=True), 64) == b"HTTP/1.1 200"
    with pytest.raises(OSError):
        net.read_upto(_Stream([], error_after=True), 64)


def test_proxmox_check(monkeypatch):
    replies = iter([b"HTTP/1.1 200 OK\r\n", b"HTTP/1.1 503 x\r\n", b"garbage"])
    monkeypatch.setattr(proxmox.net, "https_request", lambda *a: next(replies))
    assert proxmox.check("h", 8006) == (True, "HTTP 200")
    assert proxmox.check("h", 8006) == (False, "HTTP 503")
    assert proxmox.check("h", 8006) == (False, "respuesta no HTTP")

    def boom(*a):
        raise OSError("ETIMEDOUT")
    monkeypatch.setattr(proxmox.net, "https_request", boom)
    ok, detail = proxmox.check("h", 8006)
    assert ok is False and "ETIMEDOUT" in detail
