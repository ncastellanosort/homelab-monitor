from monitor import DOWN, RECOVERY, Monitor

S = 1000   # ms
INTERVAL = 30 * S
COOLDOWN = 600 * S


def make():
    return Monitor(INTERVAL, 3, COOLDOWN)


def fail_until_alert(m, start=0):
    events = [m.on_check(False, start + i * INTERVAL) for i in range(3)]
    assert events == [None, None, DOWN]
    return start + 2 * INTERVAL


def test_initial_state_is_unknown_and_check_is_due():
    m = make()
    assert m.online is None
    assert m.due(0)


def test_cadence():
    m = make()
    m.on_check(True, 0)
    assert not m.due(INTERVAL - 1)
    assert m.due(INTERVAL)


def test_alert_after_threshold():
    m = make()
    fail_until_alert(m)
    assert m.fail_count == 3
    assert m.online is False


def test_success_resets_counter_without_recovery_if_no_alert():
    m = make()
    m.on_check(False, 0)
    m.on_check(False, INTERVAL)
    assert m.on_check(True, 2 * INTERVAL) is None
    assert m.fail_count == 0


def test_fail_count_keeps_growing_after_alert():   # B2
    m = make()
    t = fail_until_alert(m)
    m.on_sent(DOWN, True, t)
    assert m.on_check(False, t + INTERVAL) is None
    assert m.fail_count == 4


def test_checks_continue_during_cooldown_and_recovery_is_immediate():   # B1
    m = make()
    t = fail_until_alert(m)
    m.on_sent(DOWN, True, t)
    assert m.due(t + INTERVAL)            # no espera los 10 min del cooldown
    assert m.on_check(True, t + INTERVAL) == RECOVERY
    m.on_sent(RECOVERY, True, t + INTERVAL)
    assert m.on_check(True, t + 2 * INTERVAL) is None


def test_reminder_only_after_cooldown():
    m = make()
    t = fail_until_alert(m)
    m.on_sent(DOWN, True, t)
    assert m.on_check(False, t + COOLDOWN - 1) is None
    assert m.on_check(False, t + COOLDOWN) == DOWN


def test_failed_down_alert_is_retried():   # B7
    m = make()
    t = fail_until_alert(m)
    m.on_sent(DOWN, False, t)
    assert m.last_send_ok is False
    assert m.on_check(False, t + INTERVAL) == DOWN
    # Sin alerta entregada no hay recuperacion que avisar
    assert m.on_check(True, t + 2 * INTERVAL) is None


def test_failed_recovery_is_retried():   # B7
    m = make()
    t = fail_until_alert(m)
    m.on_sent(DOWN, True, t)
    assert m.on_check(True, t + INTERVAL) == RECOVERY
    m.on_sent(RECOVERY, False, t + INTERVAL)
    assert m.on_check(True, t + 2 * INTERVAL) == RECOVERY


def test_last_alert_only_set_on_delivery():
    m = make()
    t = fail_until_alert(m)
    m.on_sent(DOWN, False, t)
    assert m.last_alert_ms is None
    m.on_sent(DOWN, True, t + 5)
    assert m.last_alert_ms == t + 5
