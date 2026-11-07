"""fmt.py — utilidades de formato de texto."""


def format_uptime(seconds):
    s = int(seconds)
    d = s // 86400
    h = (s % 86400) // 3600
    m = (s % 3600) // 60
    sec = s % 60
    parts = []
    if d > 0:
        parts.append("{0}d".format(d))
    if h > 0:
        parts.append("{0}h".format(h))
    if m > 0:
        parts.append("{0}m".format(m))
    parts.append("{0}s".format(sec))
    return " ".join(parts)


def format_ago(seconds):
    if seconds is None:
        return "Nunca"
    d = int(seconds)
    if d < 60:
        return "hace {0}s".format(d)
    if d < 3600:
        return "hace {0}min".format(d // 60)
    return "hace {0}h {1}min".format(d // 3600, (d % 3600) // 60)


def html_escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
