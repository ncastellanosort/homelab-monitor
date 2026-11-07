"""config.py — lee y valida la configuracion desde .env (sin efectos al importar)."""

PLACEHOLDERS = ("", "TU_SSID", "TU_PASSWORD", "TU_BOT_TOKEN", "TU_CHAT_ID")
WDT_MIN = 30


def load_env(path=".env"):
    """Parsea un archivo CLAVE=valor. Devuelve {} si no existe."""
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                env[key] = val
    except OSError:
        return None
    return env


def env_int(env, key, default, problems, minimum=1):
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        val = int(raw)
    except ValueError:
        val = None
    if val is None or val < minimum:
        problems.append("{0} invalido ('{1}'), usando {2}".format(key, raw, default))
        return default
    return val


def valid_ipv4(text):
    parts = text.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or len(p) > 3 or int(p) > 255:
            return False
    return True


def static_ip(env, problems):
    """(ip, mascara, gateway, dns) si WIFI_IP esta definida, o None para DHCP.

    Por defecto: mascara /24, gateway x.y.z.1 y DNS = gateway.
    """
    ip = env.get("WIFI_IP", "")
    if not ip:
        return None
    gw_default = ".".join(ip.split(".")[:3] + ["1"])
    cfg = (ip,
           env.get("WIFI_NETMASK") or "255.255.255.0",
           env.get("WIFI_GATEWAY") or gw_default,
           "")
    cfg = cfg[:3] + (env.get("WIFI_DNS") or cfg[2],)
    names = ("WIFI_IP", "WIFI_NETMASK", "WIFI_GATEWAY", "WIFI_DNS")
    for name, val in zip(names, cfg):
        if not valid_ipv4(val):
            problems.append("{0} invalida ('{1}'), usando DHCP".format(name, val))
            return None
    return cfg


class Config:
    pass


def from_env(env):
    """Construye un Config a partir de un dict (o None si no habia .env)."""
    c = Config()
    c.problems = []   # avisos para consola y dashboard
    if env is None:
        c.problems.append("No se encontro .env en la placa: usando placeholders")
        env = {}

    c.WIFI_SSID = env.get("WIFI_SSID", "TU_SSID")
    c.WIFI_PASSWORD = env.get("WIFI_PASSWORD", "TU_PASSWORD")
    c.WIFI_STATIC = static_ip(env, c.problems)   # None = DHCP

    c.PROXMOX_HOST = env.get("PROXMOX_HOST", "192.168.1.50")
    c.PROXMOX_PORT = env_int(env, "PROXMOX_PORT", 8006, c.problems)

    c.TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN", "TU_BOT_TOKEN")
    c.TELEGRAM_CHAT_ID = env.get("TELEGRAM_CHAT_ID", "TU_CHAT_ID")

    # Ajustes opcionales
    c.CHECK_INTERVAL = env_int(env, "CHECK_INTERVAL", 30, c.problems)    # s entre chequeos
    c.FAIL_THRESHOLD = env_int(env, "FAIL_THRESHOLD", 3, c.problems)     # fallos para alertar
    c.ALERT_COOLDOWN = env_int(env, "ALERT_COOLDOWN", 600, c.problems)   # s entre recordatorios
    c.REQUEST_TIMEOUT = env_int(env, "REQUEST_TIMEOUT", 10, c.problems)
    c.WEB_PORT = env_int(env, "WEB_PORT", 80, c.problems)
    # Watchdog: 0 lo desactiva. Menos de WDT_MIN reiniciaria la placa
    # durante un handshake TLS lento o la conexion Wi-Fi.
    c.WDT_TIMEOUT = env_int(env, "WDT_TIMEOUT", 60, c.problems, minimum=0)
    if 0 < c.WDT_TIMEOUT < WDT_MIN:
        c.problems.append("WDT_TIMEOUT minimo {0} s (era {1})".format(WDT_MIN, c.WDT_TIMEOUT))
        c.WDT_TIMEOUT = WDT_MIN

    c.WIFI_CONFIGURED = c.WIFI_SSID not in PLACEHOLDERS
    c.TELEGRAM_ENABLED = (c.TELEGRAM_TOKEN not in PLACEHOLDERS and
                          c.TELEGRAM_CHAT_ID not in PLACEHOLDERS)
    if not c.WIFI_CONFIGURED:
        c.problems.append("WIFI_SSID sin configurar en .env")
    if not c.TELEGRAM_ENABLED:
        c.problems.append("Telegram sin configurar en .env: alertas desactivadas")
    return c


def load(path=".env"):
    return from_env(load_env(path))
