"""Stubs de los modulos de MicroPython para ejecutar src/ en CPython."""
import sys
import time
import types

import pytest


class FakeWLAN:
    connected = True
    address = "10.0.0.8"
    connect_calls = 0

    def __init__(self, *_):
        pass

    def active(self, *_):
        return True

    def isconnected(self):
        return FakeWLAN.connected

    def connect(self, ssid, password):
        FakeWLAN.connect_calls += 1

    def ifconfig(self):
        return (FakeWLAN.address, "255.255.255.0", "10.0.0.1", "10.0.0.1")


network = types.ModuleType("network")
network.STA_IF = 0
network.WLAN = FakeWLAN
sys.modules["network"] = network


class FakePin:
    IN = 1
    PULL_UP = 2
    level = 1   # 1 = boton suelto (GPIO0 tiene pull-up)

    def __init__(self, *_args, **_kw):
        pass

    def value(self):
        return FakePin.level


class FakeWDT:
    instances = []

    def __init__(self, timeout=5000):
        self.timeout = timeout
        self.feeds = 0
        FakeWDT.instances.append(self)

    def feed(self):
        self.feeds += 1


machine = types.ModuleType("machine")
machine.Pin = FakePin
machine.WDT = FakeWDT
sys.modules["machine"] = machine


class FakeTicks:
    """Reemplaza time.ticks_ms / ticks_diff (no existen en CPython)."""

    def __init__(self):
        self.ms = 0

    def ticks_ms(self):
        return self.ms

    @staticmethod
    def ticks_diff(a, b):
        return a - b


@pytest.fixture
def ticks(monkeypatch):
    t = FakeTicks()
    monkeypatch.setattr(time, "ticks_ms", t.ticks_ms, raising=False)
    monkeypatch.setattr(time, "ticks_diff", t.ticks_diff, raising=False)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return t


@pytest.fixture(autouse=True)
def reset_fakes():
    FakeWLAN.connected = True
    FakeWLAN.connect_calls = 0
    FakePin.level = 1
    FakeWDT.instances.clear()
    yield
