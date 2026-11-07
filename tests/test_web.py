import web


def status(**over):
    st = {
        "version": "9.9.9", "online": True, "detail": "HTTP 200", "fail_count": 0,
        "fail_threshold": 3, "last_check_ago_s": 5, "last_alert_ago_s": None,
        "telegram_enabled": True, "telegram_last_ok": None, "host": "10.0.0.5:8006",
        "wifi_ip": "10.0.0.8", "uptime_s": 61, "warnings": [],
    }
    st.update(over)
    return st


def test_render_states():
    assert "DESCONOCIDO" in web.render_html(status(online=None))   # B8
    assert "ONLINE" in web.render_html(status(online=True))
    assert "OFFLINE" in web.render_html(status(online=False))


def test_render_values_and_escaping():
    html = web.render_html(status(fail_count=2, host="<x>:1", warnings=["falta <token>"]))
    assert "2/3" in html
    assert "&lt;x&gt;:1" in html and "<x>" not in html
    assert "falta &lt;token&gt;" in html
    assert "v9.9.9" in html and "1m 1s" in html


def get(path, method=b"GET"):
    req = method + b" " + path + b" HTTP/1.1\r\nHost: esp32\r\n\r\n"
    return web.route(req, status)


def test_route_dashboard():
    code, ctype, body = get(b"/")
    assert code == 200 and ctype.startswith("text/html") and "<!DOCTYPE html>" in body


def test_route_dashboard_ignores_query():
    assert get(b"/?x=1")[0] == 200


def test_route_api_status_is_json():
    import json
    code, ctype, body = get(b"/api/status")
    assert code == 200 and ctype == "application/json"
    data = json.loads(body)
    assert data["online"] is True and data["fail_threshold"] == 3


def test_route_not_found_and_method_and_bad_request():   # M4
    assert get(b"/favicon.ico")[0] == 404
    assert get(b"/", b"POST")[0] == 405
    assert web.route(b"garbage", status)[0] == 400
    assert web.route(b"", status)[0] == 400


def test_build_response_content_length_counts_bytes():
    resp = web.build_response(200, web.HTML, "\u00f1and\u00fa")
    head, body = resp.split(b"\r\n\r\n", 1)
    assert head.startswith(b"HTTP/1.0 200 OK\r\n")
    assert b"Content-Length: 7\r\n" in head and len(body) == 7


def test_build_response_405_has_allow():
    assert b"Allow: GET" in web.build_response(405, web.TEXT, "x")


def test_render_check_and_telegram_rows():
    html = web.render_html(status(last_check_ago_s=None))
    assert "pendiente" in html and "sin envios" in html
    html = web.render_html(status(telegram_enabled=False))
    assert "sin configurar" in html
    html = web.render_html(status(telegram_last_ok=False, detail="error de red"))
    assert "ERROR en el ultimo envio" in html and "error de red" in html


def test_render_static_ip_marker():
    assert "10.0.0.8 (fija)" in web.render_html(status(wifi_static=True))
    assert "(fija)" not in web.render_html(status())
