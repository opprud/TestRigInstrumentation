"""
Run heartbeat for the VPS heater-safety watchdog (ticket 0034).

While a run is alive AND wants heat, publish every ~30 s to the broker:

    topic    testrig/run/heartbeat            (not retained)
    payload  {"run_id": "<id>", "heating": true, "ts": <unix_s>, "host": "pi"}

The watchdog on the broker VPS cuts the heater relay when no fresh `heating: true`
heartbeat has been seen for stale_sec (180 s). So a frozen Pi, a killed run or a clean
run-end all end the same way: the heartbeat stops. A clean stop() first sends one
`heating: false` so the watchdog does not have to wait for staleness.

Never takes the run down: every failure is swallowed and counted. A failed publish is the
safe direction - the watchdog then cuts the heater, it never leaves it on.
"""
import json
import threading
import time

TOPIC = "testrig/run/heartbeat"
PERIOD_S = 30.0


def profile_wants_heat(profile_cfg) -> bool:
    """A run wants heat when its profile carries a temperature schedule."""
    sp = (profile_cfg or {}).get("setpoints") or {}
    return bool(sp.get("temperature"))


class HeaterHeartbeat:
    def __init__(self, run_id: str, wants_heat: bool, log=print, period_s: float = PERIOD_S):
        self.run_id, self.wants_heat, self.log, self.period = run_id, bool(wants_heat), log, period_s
        self.sent = 0
        self.failed = 0
        self._ev = threading.Event()
        self._t = None

    def _publish(self, heating: bool) -> bool:
        try:
            import paho.mqtt.client as mqtt
            from shelly_control import MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASSWORD
            try:
                c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"rig_heartbeat_{self.run_id}")
            except AttributeError:
                c = mqtt.Client(client_id=f"rig_heartbeat_{self.run_id}")
            c.username_pw_set(MQTT_USER, MQTT_PASSWORD)
            c.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
            c.loop_start()
            try:
                msg = {"run_id": self.run_id, "heating": bool(heating), "ts": int(time.time()), "host": "pi"}
                info = c.publish(TOPIC, json.dumps(msg), qos=0, retain=False)
                info.wait_for_publish(timeout=5)
                ok = info.is_published()
            finally:
                c.loop_stop()
                c.disconnect()
            self.sent += ok
            self.failed += (not ok)
            return ok
        except Exception as e:
            self.failed += 1
            if self.failed in (1, 10, 100):
                self.log(f"[heartbeat] publish failed ({e!r}); failures so far: {self.failed}")
            return False

    def _run(self):
        while not self._ev.is_set():
            self._publish(True)
            self._ev.wait(self.period)

    def start(self):
        if not self.wants_heat:
            self.log("[heartbeat] profile has no temperature schedule - not publishing (watchdog sees no heat wanted)")
            return
        self._t = threading.Thread(target=self._run, name="heater-heartbeat", daemon=True)
        self._t.start()
        self.log(f"[heartbeat] publishing {TOPIC} every {self.period:.0f}s for run {self.run_id}")

    def stop(self):
        if not self._t:
            return
        self._ev.set()
        self._t.join(timeout=10)
        self._publish(False)
        self.log(f"[heartbeat] stopped (heating:false sent); published {self.sent}, failed {self.failed}")
