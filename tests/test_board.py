import board
import pytest
from conftest import FakePin, FakeWDT


@pytest.fixture(autouse=True)
def no_wdt(ticks):
    board._wdt = None
    yield
    board._wdt = None


def test_safe_boot_not_requested():
    assert board.safe_boot_requested(1) is False


def test_safe_boot_requested_when_boot_pressed():
    FakePin.level = 0
    assert board.safe_boot_requested(1) is True


def test_wdt_disabled_with_zero():
    assert board.wdt_start(0) is False
    assert not board.wdt_active()
    board.feed()   # no falla sin watchdog
    assert FakeWDT.instances == []


def test_wdt_start_and_feed():
    assert board.wdt_start(60) is True
    assert board.wdt_active()
    wdt = FakeWDT.instances[0]
    assert wdt.timeout == 60000
    board.feed()
    board.feed()
    assert wdt.feeds == 2
