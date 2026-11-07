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
