import notifier
import pytest


def test_url_encode_ascii_and_space():
    assert notifier.url_encode("abc XYZ_.~-") == "abc+XYZ_.~-"
    assert notifier.url_encode("a&b=c\n") == "a%26b%3Dc%0A"


def test_url_encode_emoji_is_utf8():   # B4
    assert notifier.url_encode(notifier.E_GREEN) == "%F0%9F%9F%A2"
    assert notifier.url_encode("ñ") == "%C3%B1"


@pytest.mark.parametrize("msg", [
    notifier.msg_boot("10.0.0.8", 80, "pve", 8006, 5),
    notifier.msg_down("pve", 8006, 3, 65, "10.0.0.8"),
    notifier.msg_recovery("pve", 8006, 65, "10.0.0.8"),
])
def test_messages_use_real_emojis(msg):   # B4
    # Un emoji mal escrito como bytes UTF-8 dentro de un str deja "\xf0" sueltos
    assert "\xf0" not in msg and "\xe2" not in msg
    assert any(ord(c) > 0xFFFF for c in msg)


def test_down_message_content_and_escaping():
    msg = notifier.msg_down("<pve>", 8006, 4, 3661, "10.0.0.8")
    assert notifier.E_RED in msg
    assert "&lt;pve&gt;:8006" in msg
    assert "Fallos consecutivos:</b> 4" in msg
    assert "1h 1m 1s" in msg


def test_build_request():
    req = notifier.build_request("123:ABC", "-100", "hola mundo").decode()
    head, body = req.split("\r\n\r\n", 1)
    assert head.startswith("POST /bot123:ABC/sendMessage HTTP/1.1\r\n")
    assert "Host: api.telegram.org" in head
    assert "Content-Length: {0}".format(len(body)) in head
    assert body == "chat_id=-100&text=hola+mundo&parse_mode=HTML"


def test_send_success_and_failure(monkeypatch):
    replies = iter([b"HTTP/1.1 200 OK\r\n", b"HTTP/1.1 401 Unauthorized\r\n"])
    monkeypatch.setattr(notifier.net, "https_request", lambda *a: next(replies))
    assert notifier.send("t", "1", "x") is True
    assert notifier.send("t", "1", "x") is False


def test_send_network_error(monkeypatch):
    def boom(*a):
        raise OSError("timeout")
    monkeypatch.setattr(notifier.net, "https_request", boom)
    assert notifier.send("t", "1", "x") is False


def test_error_description():
    resp = (b'HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\n\r\n'
            b'{"ok":false,"error_code":403,"description":"Forbidden: bot was blocked by the user"}')
    assert notifier.error_description(resp) == "Forbidden: bot was blocked by the user"
    assert notifier.error_description(b"HTTP/1.1 502 Bad Gateway\r\n\r\n<html>") == ""
    assert notifier.error_description(b'..."description":"cortado') == "cortado"
