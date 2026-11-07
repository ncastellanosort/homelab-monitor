import config


def write_env(tmp_path, text):
    p = tmp_path / ".env"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_load_env_parsing(tmp_path):
    path = write_env(tmp_path, (
        "# comentario\n"
        "\n"
        "WIFI_SSID=\"Mi Red\"\n"
        "WIFI_PASSWORD='a=b#c'\n"
        "  PROXMOX_HOST = 192.168.40.50  \n"
        "linea sin igual\n"
    ))
    env = config.load_env(path)
    assert env == {"WIFI_SSID": "Mi Red", "WIFI_PASSWORD": "a=b#c",
                   "PROXMOX_HOST": "192.168.40.50"}


def test_missing_env_file(tmp_path):
    assert config.load_env(str(tmp_path / "nope")) is None
    c = config.load(str(tmp_path / "nope"))
    assert not c.WIFI_CONFIGURED and not c.TELEGRAM_ENABLED
    assert any(".env" in p for p in c.problems)


def test_full_config(tmp_path):
    c = config.load(write_env(tmp_path, (
        "WIFI_SSID=casa\nWIFI_PASSWORD=pw\nPROXMOX_HOST=10.0.0.5\nPROXMOX_PORT=8007\n"
        "TELEGRAM_TOKEN=123:abc\nTELEGRAM_CHAT_ID=-100\nCHECK_INTERVAL=15\n"
    )))
    assert c.problems == []
    assert c.WIFI_CONFIGURED and c.TELEGRAM_ENABLED
    assert (c.PROXMOX_HOST, c.PROXMOX_PORT, c.CHECK_INTERVAL) == ("10.0.0.5", 8007, 15)
    assert (c.FAIL_THRESHOLD, c.ALERT_COOLDOWN, c.WEB_PORT) == (3, 600, 80)


def test_placeholders_are_reported():
    c = config.from_env({"WIFI_SSID": "TU_SSID", "TELEGRAM_TOKEN": "TU_BOT_TOKEN",
                         "TELEGRAM_CHAT_ID": "1"})
    assert not c.WIFI_CONFIGURED
    assert not c.TELEGRAM_ENABLED
    assert len(c.problems) == 2


def test_invalid_numbers_fall_back_to_defaults():
    c = config.from_env({"WIFI_SSID": "x", "TELEGRAM_TOKEN": "t", "TELEGRAM_CHAT_ID": "1",
                         "PROXMOX_PORT": "abc", "CHECK_INTERVAL": "0", "WEB_PORT": ""})
    assert (c.PROXMOX_PORT, c.CHECK_INTERVAL, c.WEB_PORT) == (8006, 30, 80)
    assert len(c.problems) == 2


def test_wdt_timeout():
    base = {"WIFI_SSID": "x", "TELEGRAM_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}
    assert config.from_env(base).WDT_TIMEOUT == 60
    assert config.from_env(dict(base, WDT_TIMEOUT="0")).WDT_TIMEOUT == 0
    c = config.from_env(dict(base, WDT_TIMEOUT="5"))
    assert c.WDT_TIMEOUT == config.WDT_MIN and len(c.problems) == 1
    assert config.from_env(dict(base, WDT_TIMEOUT="-1")).WDT_TIMEOUT == 60


def test_static_ip_defaults_from_ip():
    c = config.from_env({"WIFI_SSID": "x", "TELEGRAM_TOKEN": "t", "TELEGRAM_CHAT_ID": "1",
                         "WIFI_IP": "192.168.40.7"})
    assert c.WIFI_STATIC == ("192.168.40.7", "255.255.255.0", "192.168.40.1", "192.168.40.1")
    assert c.problems == []


def test_static_ip_explicit_and_dhcp():
    env = {"WIFI_IP": "10.1.2.3", "WIFI_NETMASK": "255.255.0.0",
           "WIFI_GATEWAY": "10.1.0.254", "WIFI_DNS": "1.1.1.1"}
    assert config.static_ip(env, []) == ("10.1.2.3", "255.255.0.0", "10.1.0.254", "1.1.1.1")
    assert config.static_ip({}, []) is None
    assert config.static_ip({"WIFI_IP": ""}, []) is None


def test_static_ip_invalid_falls_back_to_dhcp():
    for bad in ("192.168.40", "192.168.40.300", "a.b.c.d", "1.2.3.4.5", " 1.2.3.4"):
        problems = []
        assert config.static_ip({"WIFI_IP": bad}, problems) is None, bad
        assert len(problems) == 1
    problems = []
    assert config.static_ip({"WIFI_IP": "10.0.0.5", "WIFI_GATEWAY": "x"}, problems) is None
    assert "WIFI_GATEWAY" in problems[0]
