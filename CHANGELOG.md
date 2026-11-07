# Changelog

## [2.0.0] — 2026-11-07

Tested on an ESP32 with MicroPython 1.23.0: Proxmox check, Telegram alerts (down, reminder, recovery), dashboard and API, static IP, watchdog, safe-boot and both deploy modes.

### Breaking

- Code moved to `src/` and split into modules. Deploy with `deploy.sh` / `deploy.ps1` instead of copying `main.py` by hand.
- Credentials and settings are read from a `.env` file on the board (template: `.env.example`) instead of being edited in `main.py`.

### Fixed

- Checks keep running during the alert cooldown, so a recovery is detected and reported within one check interval instead of up to 10 minutes later.
- The failure counter shows real consecutive failures and no longer resets to 0 after an alert.
- Uptime is measured from boot with a monotonic clock instead of the RTC.
- Emojis in Telegram messages are encoded correctly.
- Proxmox counts as up only with a valid HTTP response below 500, not with any received bytes.
- A failed Telegram send is no longer marked as delivered; it is retried on the next check.
- No 100% CPU busy loop when the web server fails to start.
- The dashboard shows "DESCONOCIDO" until the first check instead of "ONLINE".

### Security

- TLS never falls back to plaintext, so the bot token is never sent unencrypted.
- `.env` is ignored by git.

### Added

- Configuration validation: leftover placeholders and invalid values are reported on the console and the dashboard; Telegram is disabled until configured.
- Optional settings in `.env`: `CHECK_INTERVAL`, `FAIL_THRESHOLD`, `ALERT_COOLDOWN`, `REQUEST_TIMEOUT`, `WEB_PORT`, `WDT_TIMEOUT`.
- Hardware watchdog (`WDT_TIMEOUT`, default 60 s).
- Safe-boot: pressing BOOT during the 3 s startup window keeps the monitor from starting and leaves the REPL free.
- `/api/status` JSON endpoint; other paths return 404; responses include `Content-Length`.
- Dashboard rows for the last check result and Telegram delivery status.
- Reminder alert every `ALERT_COOLDOWN` seconds while Proxmox stays down.
- pytest suite, ruff and GitHub Actions CI (including an `mpy-cross` 1.23 compile check).
- `deploy.sh` and `deploy.ps1`, with an optional `.mpy` precompile.
- Optional static IP: `WIFI_IP`, `WIFI_NETMASK`, `WIFI_GATEWAY`, `WIFI_DNS` (empty `WIFI_IP` = DHCP).
- Telegram errors show the API's explanation (for example a wrong chat ID) on the console, and a failed send shows on the dashboard.

## [1.1.0] — 2026-06-07

- Telegram recovery alert when Proxmox comes back online.

## [1.0.1] — 2026-05-30

- Release badge in the README.

## [1.0.0] — 2026-05-30

- First release: single-file monitor with HTTPS check, Telegram alerts (HTML formatted) and HTTP dashboard.
