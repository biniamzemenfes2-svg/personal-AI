"""Background supervisor thread with graceful shutdown."""
import logging
import threading

import psutil

import config

log = logging.getLogger("aetheros.daemon")


class Daemon:
    def __init__(self, task_manager):
        self.tasks = task_manager
        self._alerts = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="aether-daemon")

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)

    def get_alerts(self):
        with self._lock:
            return list(self._alerts)

    def _check(self):
        alerts = []
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        if cpu > config.CPU_ALERT_PERCENT:
            alerts.append(f"⚠️ High CPU Load: {cpu}%")
        if ram > config.RAM_ALERT_PERCENT:
            alerts.append(f"⚠️ Memory Exhaustion Warning: {ram}% RAM in use")
        try:
            backlog = self.tasks.pending_count()
            if backlog > config.TASK_BACKLOG_ALERT:
                alerts.append(f"📋 Task Backlog heavy: {backlog} items waiting")
        except Exception as e:
            log.error("Backlog check failed: %s", e)
        return alerts

    def _loop(self):
        while not self._stop.is_set():
            alerts = self._check()
            with self._lock:
                self._alerts = alerts
            self._stop.wait(config.DAEMON_INTERVAL)
