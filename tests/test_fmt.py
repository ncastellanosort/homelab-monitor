from fmt import format_ago, format_uptime, html_escape


def test_format_uptime():
    assert format_uptime(0) == "0s"
    assert format_uptime(59) == "59s"
    assert format_uptime(61) == "1m 1s"
    assert format_uptime(3600) == "1h 0s"
    assert format_uptime(90061) == "1d 1h 1m 1s"


def test_format_ago():
    assert format_ago(None) == "Nunca"
    assert format_ago(5) == "hace 5s"
    assert format_ago(125) == "hace 2min"
    assert format_ago(3 * 3600 + 120) == "hace 3h 2min"


def test_html_escape():
    assert html_escape('<a href="x">&</a>') == "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;"
    assert html_escape(8006) == "8006"
