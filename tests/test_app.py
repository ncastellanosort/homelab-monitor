"""Simula el bucle principal con red falsa y reloj controlado."""
import app
import config
import pytest
from conftest import FakeWLAN

INTERVAL_MS = 30 * 1000


@pytest.fixture
def harness(ticks, monkeypatch):
    results = []
    sent = []
    monkeypatch.setattr(app.proxmox, "check",
                        lambda *a: (results.pop(0), "fake") if results else (True, "fake"))
    monkeypatch.setattr(app.notifier, "send",
                        lambda tok, chat, text, timeout: sent.append(text) or True)
    monkeypatch.setattr(app.web, "start", lambda *a: object())
    monkeypatch.setattr(app.web, "serve", lambda *a: None)
    cfg = config.from_env({"WIFI_SSID": "casa", "TELEGRAM_TOKEN": "t",
                           "TELEGRAM_CHAT_ID": "1"})
    a = app.App(cfg)

    def step(*oks):
        results.extend(oks)
        for _ in oks:
            a.tick()
            ticks.ms += INTERVAL_MS
    return a, step, sent


def test_outage_alert_and_recovery(harness):
    a, step, sent = harness
    step(True, False, False, False)
    assert len(sent) == 1 and "NO responde" in sent[0]
    assert a.status()["fail_count"] == 3
    step(False)
    assert len(sent) == 1                      # sin spam dentro del cooldown
    assert a.status()["fail_count"] == 4
    step(True)
    assert len(sent) == 2 and "RECUPERADO" in sent[1]
    assert a.status()["online"] is True


def test_status_before_first_check(harness):
    a, _, _ = harness
    st = a.status()
    assert st["online"] is None and st["last_check_ago_s"] is None
    assert st["wifi_ip"] == "10.0.0.8"


def test_uptime_from_ticks(harness, ticks):
    a, _, _ = harness
    ticks.ms = 90 * 1000
    assert a.status()["uptime_s"] == 90


def test_telegram_disabled_does_not_send(ticks, monkeypatch):
    called = []
    monkeypatch.setattr(app.notifier, "send", lambda *a: called.append(a) or True)
    a = app.App(config.from_env({"WIFI_SSID": "casa"}))
    assert a.send("hola") is False
    assert called == []


def test_reconnects_wifi(harness):
    a, step, _ = harness
    FakeWLAN.connected = False
    step(True)
    assert FakeWLAN.connect_calls >= 1


def test_tick_feeds_watchdog(harness):
    import board
    from conftest import FakeWDT
    a, step, _ = harness
    board.wdt_start(60)
    try:
        step(True)
        assert FakeWDT.instances[0].feeds >= 2
    finally:
        board._wdt = None


def test_run_survives_initial_wifi_failure(ticks, monkeypatch):
    """Sin Wi-Fi al arrancar ya no se aborta: el bucle sigue reintentando."""
    FakeWLAN.connected = False
    calls = []

    def fake_tick(self):
        calls.append(1)
        if len(calls) == 3:
            raise KeyboardInterrupt
    monkeypatch.setattr(app.App, "tick", fake_tick)
    cfg = config.from_env({"WIFI_SSID": "casa", "WDT_TIMEOUT": "0"})
    app.App(cfg).run()
    assert len(calls) == 3


def test_boot_message_failure_shows_on_dashboard(ticks, monkeypatch):
    monkeypatch.setattr(app.notifier, "send", lambda *a: False)
    a = app.App(config.from_env({"WIFI_SSID": "casa", "TELEGRAM_TOKEN": "t",
                                 "TELEGRAM_CHAT_ID": "1"}))
    assert a.status()["telegram_last_ok"] is None
    a.send("arranque")
    assert a.status()["telegram_last_ok"] is False
