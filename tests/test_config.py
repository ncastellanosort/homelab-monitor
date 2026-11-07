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
