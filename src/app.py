"""app.py — orquestador: Wi-Fi -> chequeo de Proxmox -> alertas -> HTTP."""
import time

import board
import config
import notifier
import proxmox
import web
import wifi
from fmt import format_uptime
from monitor import DOWN, Monitor

VERSION = "2.0.0"


class Clock:
    """Acumula time.ticks_diff() para obtener ms monotonicos desde el arranque.

    ticks_ms() da la vuelta cada ~12 dias; acumulando diferencias cortas el
    contador nunca se desborda y no depende del RTC (ni de NTP).
    """

    def __init__(self):
        self._last = time.ticks_ms()
        self._ms = 0

    def now_ms(self):
        t = time.ticks_ms()
        self._ms += time.ticks_diff(t, self._last)
        self._last = t
        return self._ms


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.clock = Clock()
        self.mon = Monitor(cfg.CHECK_INTERVAL * 1000, cfg.FAIL_THRESHOLD,
                           cfg.ALERT_COOLDOWN * 1000)
        self.server = None

    def status(self):
        now = self.clock.now_ms()
        mon = self.mon
        return {
            "version": VERSION,
            "online": mon.online,
            "detail": mon.detail,
            "fail_count": mon.fail_count,
            "fail_threshold": mon.fail_threshold,
            "last_check_ago_s": (None if mon.last_check_ms is None
                                 else (now - mon.last_check_ms) // 1000),
            "last_alert_ago_s": (None if mon.last_alert_ms is None
                                 else (now - mon.last_alert_ms) // 1000),
            "telegram_enabled": self.cfg.TELEGRAM_ENABLED,
            "telegram_last_ok": mon.last_send_ok,
            "host": "{0}:{1}".format(self.cfg.PROXMOX_HOST, self.cfg.PROXMOX_PORT),
            "wifi_ip": wifi.ip(),
            "uptime_s": now // 1000,
            "warnings": self.cfg.problems,
        }

    def send(self, text):
        c = self.cfg
        if not c.TELEGRAM_ENABLED:
            print("  [Telegram] Sin configurar, mensaje no enviado.")
            return False
        ok = notifier.send(c.TELEGRAM_TOKEN, c.TELEGRAM_CHAT_ID, text, c.REQUEST_TIMEOUT)
        self.mon.last_send_ok = ok   # tambien para el mensaje de arranque
        return ok

    def notify(self, event, uptime_s):
        c, mon, ip = self.cfg, self.mon, wifi.ip()
        if event == DOWN:
            print("  -> Enviando alerta de caida ...")
            text = notifier.msg_down(c.PROXMOX_HOST, c.PROXMOX_PORT, mon.fail_count,
                                     uptime_s, ip)
        else:
            print("  -> Enviando alerta de recuperacion ...")
            text = notifier.msg_recovery(c.PROXMOX_HOST, c.PROXMOX_PORT, uptime_s, ip)
        delivered = self.send(text)
        mon.on_sent(event, delivered, self.clock.now_ms())
        if not delivered:
            print("  -> No entregada; se reintentara en el proximo chequeo.")

    def tick(self):
        """Una vuelta del bucle principal (~1 s)."""
        c, mon = self.cfg, self.mon
        board.feed()
        if not wifi.is_connected():
            print("[WiFi] Conexion perdida, reintentando ...")
            if not wifi.connect(c.WIFI_SSID, c.WIFI_PASSWORD, on_wait=board.feed):
                web.serve(self.server, self.status)
                return
        if self.server is None:
            self.server = web.start(c.WEB_PORT, wifi.ip())

        now = self.clock.now_ms()
        if mon.due(now):
            print("[{0}] Verificando Proxmox ...".format(format_uptime(now // 1000)), end="")
            ok, detail = proxmox.check(c.PROXMOX_HOST, c.PROXMOX_PORT, c.REQUEST_TIMEOUT)
            event = mon.on_check(ok, now, detail)
            if ok:
                print(" OK ({0})".format(detail))
            else:
                print(" FALLO {0}/{1} ({2})".format(mon.fail_count, mon.fail_threshold, detail))
            if event is not None:
                board.feed()   # cada operacion de red tiene su propio margen
                self.notify(event, now // 1000)

        # Servir HTTP (no bloqueante, timeout 1s)
        board.feed()
        web.serve(self.server, self.status)

    def run(self):
        c = self.cfg
        print("\n=== Proxmox Monitor v{0} ===".format(VERSION))
        print("Host: {0}:{1}  |  Intervalo: {2}s".format(
            c.PROXMOX_HOST, c.PROXMOX_PORT, c.CHECK_INTERVAL))
        print("Dashboard: http://<IP>:{0}/".format(c.WEB_PORT))
        print("=" * 40 + "\n")
        for p in c.problems:
            print("[Config] AVISO: " + p)

        if not c.WIFI_CONFIGURED:
            print("[FATAL] Configura WIFI_SSID y WIFI_PASSWORD en .env y subelo a la placa.")
            return

        board.wdt_start(c.WDT_TIMEOUT)
        # Si el primer intento falla, tick() sigue reintentando (con el WDT vivo)
        wifi.connect(c.WIFI_SSID, c.WIFI_PASSWORD, on_wait=board.feed)

        if wifi.is_connected():
            ip = wifi.ip()
            self.server = web.start(c.WEB_PORT, ip)
            board.feed()
            print("[Boot] Enviando notificacion a Telegram ...")
            self.send(notifier.msg_boot(ip, c.WEB_PORT, c.PROXMOX_HOST, c.PROXMOX_PORT,
                                        self.clock.now_ms() // 1000))

        while True:
            try:
                self.tick()
            except KeyboardInterrupt:
                print("\n[INFO] Monitor detenido.")
                if board.wdt_active():
                    print("[WDT] Sigue activo: la placa se reiniciara en <= {0} s. "
                          "Para usar el REPL: reset y pulsa BOOT.".format(c.WDT_TIMEOUT))
                break
            except Exception as e:
                print("[ERROR] {0}".format(e))
                time.sleep(1)


def run(env_path=".env"):
    App(config.load(env_path)).run()
