"""monitor.py — maquina de estados del monitor (sin I/O). Tiempos en ms."""

DOWN = "down"
RECOVERY = "recovery"


class Monitor:
    """Decide cuando chequear y que alertas enviar.

    - Los chequeos siguen su cadencia aunque se haya enviado una alerta.
    - fail_count = fallos consecutivos reales; solo se reinicia con un OK.
    - La alerta de caida se repite como recordatorio cada alert_cooldown_ms
      mientras Proxmox siga caido.
    - Un envio fallido no se da por hecho: se reintenta en el siguiente chequeo.
    """

    def __init__(self, check_interval_ms, fail_threshold, alert_cooldown_ms):
        self.check_interval_ms = check_interval_ms
        self.fail_threshold = fail_threshold
        self.alert_cooldown_ms = alert_cooldown_ms
        self.online = None           # None = aun no se ha comprobado
        self.fail_count = 0
        self.detail = ""
        self.last_check_ms = None
        self.last_alert_ms = None    # ultima alerta de caida ENTREGADA
        self.outage_alerted = False  # se aviso esta caida -> falta la recuperacion
        self.last_send_ok = None     # resultado del ultimo envio a Telegram

    def due(self, now_ms):
        return (self.last_check_ms is None or
                now_ms - self.last_check_ms >= self.check_interval_ms)

    def on_check(self, ok, now_ms, detail=""):
        """Registra un chequeo y devuelve el evento a notificar (o None)."""
        self.last_check_ms = now_ms
        self.detail = detail
        if ok:
            self.online = True
            self.fail_count = 0
            return RECOVERY if self.outage_alerted else None
        self.online = False
        self.fail_count += 1
        if self.fail_count < self.fail_threshold:
            return None
        if not self.outage_alerted:
            return DOWN
        if now_ms - self.last_alert_ms >= self.alert_cooldown_ms:
            return DOWN
        return None

    def on_sent(self, event, delivered, now_ms):
        self.last_send_ok = delivered
        if not delivered:
            return
        if event == DOWN:
            self.outage_alerted = True
            self.last_alert_ms = now_ms
        elif event == RECOVERY:
            self.outage_alerted = False
