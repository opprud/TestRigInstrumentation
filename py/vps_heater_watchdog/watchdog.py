#!/usr/bin/env python3
"""
VPS heater-safety watchdog (ticket 0034).

Independent always-running daemon on the MQTT-broker VPS (185.81.165.190) that
guarantees the oil heater (Shelly Pro 4PM channel 0) is OFF whenever no live,
healthy run legitimately wants heat. It is deliberately independent of the rig
Pi: the broker is local (localhost:1883), so a frozen / dead / rebooting Pi
cannot stop the watchdog from cutting the relay.

Fail-safe by design
--------------------
The *absence* of a positive "a run is alive and heating" signal is what triggers
heater-off. A frozen Pi produces no heartbeat, so the heater is cut, not left on.
Clean test-end is the same rule: the heartbeat stops -> heater off.

Heartbeat contract (Pi -> VPS, published by the rig Pi)
-------------------------------------------------------
  topic:   testrig/run/heartbeat   (NOT retained)
  payload: {"run_id": "<id>", "heating": true, "ts": <unix_seconds>, "host": "pi"}
  cadence: every ~30 s while a heated run is active AND wants heat.

A heartbeat counts as "heat wanted" only when it is fresh (age < stale_sec) and
heating == true. Anything else -> heat not wanted -> ensure heater OFF.

Hardware note (2026-08-26 incident): this Shelly returns no retained channel
state ('???'). We therefore NEVER require a confirmed-ON reading. The rule is
"heat not wanted AND heater is ON or cannot be confirmed OFF -> send OFF". The
only true confirmation the relay opened is the bearing/oil temperature falling.

The VPS cannot reach the Omron (it is on the Pi's RS485), so driving the Omron
SV down stays a Pi-side responsibility on a clean end. The relay cut here is the
hard physical backstop and de-energises the heater regardless of the Omron SV.
"""

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed. Run: pip install paho-mqtt")
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
DEFAULT_CONFIG = {
    "mqtt": {
        "host": "localhost",
        "port": 1883,
        "username": "mqttuser",
        "password": "3711",
        "client_id": "heater_watchdog",
    },
    "device_id": "shellypro4pm-c8f09e84cdf8",
    "heater_channel": 0,
    "heartbeat_topic": "testrig/run/heartbeat",
    "status_topic": "testrig/watchdog/status",
    "stale_sec": 180,          # heartbeat older than this => heat not wanted (ticket: 3-5 min)
    "poll_sec": 10,            # decision + GetStatus cadence
    "startup_grace_sec": 200,  # after (re)start, listen this long before first actuation
    "armed": False,            # False = observe-only (log, never actuate). Flip to True once Pi heartbeats are live.
    "maintenance_file": "/home/claude-win/heater-watchdog/MAINTENANCE",
    "log_file": "/home/claude-win/heater-watchdog/logs/watchdog.log",
    "pi_cycle_enabled": False,  # optional ch3 Pi power-cycle (0033). Off: never auto-reboot the Pi here.
}


def load_config(path):
    cfg = dict(DEFAULT_CONFIG)
    if path and os.path.exists(path):
        with open(path) as fh:
            user = json.load(fh)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k] = {**cfg[k], **v}
            else:
                cfg[k] = v
    return cfg


# --------------------------------------------------------------------------- #
# Watchdog
# --------------------------------------------------------------------------- #
class HeaterWatchdog:
    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self.dev = cfg["device_id"]
        self.ch = int(cfg["heater_channel"])

        # shared state (guarded by _lock)
        self._lock = threading.Lock()
        self.last_hb_ts = 0.0          # unix time of last heartbeat received
        self.last_hb_heating = False   # 'heating' field of last heartbeat
        self.last_hb_run = None
        self.heater_output = None      # True / False / None(unknown)
        self.heater_output_ts = 0.0    # when heater_output was last refreshed
        self.shelly_online = None      # True / False / None

        self.started = time.time()
        self._stop = threading.Event()
        self._last_off_sent = 0.0

        self.client = self._make_client()

    # -- MQTT plumbing ----------------------------------------------------- #
    def _make_client(self):
        cid = self.cfg["mqtt"].get("client_id", "heater_watchdog")
        try:
            c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
        except (AttributeError, TypeError):
            c = mqtt.Client(client_id=cid)
        c.username_pw_set(self.cfg["mqtt"]["username"], self.cfg["mqtt"]["password"])
        c.on_connect = self._on_connect
        c.on_message = self._on_message
        c.on_disconnect = self._on_disconnect
        # If the watchdog process dies, publish an alarm via LWT so a dashboard can tell.
        c.will_set(self.cfg["status_topic"],
                   json.dumps({"alive": False, "ts": int(time.time())}),
                   qos=1, retain=True)
        return c

    def _on_connect(self, c, u, flags, rc, *a):
        rc_val = rc if isinstance(rc, int) else getattr(rc, "value", rc)
        if rc_val != 0:
            self.log.error("MQTT connect failed rc=%s", rc)
            return
        self.log.info("MQTT connected to %s:%s", self.cfg["mqtt"]["host"], self.cfg["mqtt"]["port"])
        c.subscribe([(self.cfg["heartbeat_topic"], 1),
                     (f"{self.dev}/#", 0),
                     (f"{self.cfg['mqtt'].get('client_id', 'heater_watchdog')}/#", 0)])

    def _on_disconnect(self, c, u, *a):
        self.log.warning("MQTT disconnected; paho will auto-reconnect")

    def _on_message(self, c, u, msg, *a):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            # non-JSON (e.g. '<device>/online' -> 'true'/'false')
            raw = msg.payload.decode(errors="replace").strip().lower()
            if topic == f"{self.dev}/online":
                with self._lock:
                    self.shelly_online = (raw == "true")
            return

        if topic == self.cfg["heartbeat_topic"]:
            self._handle_heartbeat(payload)
            return
        if topic == f"{self.dev}/online":
            with self._lock:
                self.shelly_online = bool(payload)
            return
        # Any Shelly status / event / rpc-reply that carries switch:0 output.
        self._scan_for_heater_output(topic, payload)

    def _handle_heartbeat(self, payload):
        with self._lock:
            # Guard against a stale/duplicate: trust the message ts if present.
            ts = payload.get("ts")
            self.last_hb_ts = float(ts) if isinstance(ts, (int, float)) else time.time()
            self.last_hb_heating = bool(payload.get("heating", False))
            self.last_hb_run = payload.get("run_id")
        self.log.debug("heartbeat run=%s heating=%s", payload.get("run_id"), payload.get("heating"))

    def _scan_for_heater_output(self, topic, payload):
        out = None
        try:
            if topic.endswith(f"/status/switch:{self.ch}"):
                out = payload.get("output")
            elif topic.endswith("/events/rpc"):
                sw = payload.get("params", {}).get(f"switch:{self.ch}", {})
                if "output" in sw:
                    out = sw["output"]
            elif topic.endswith("/rpc"):
                res = payload.get("result", {})
                if isinstance(res, dict) and res.get("id") == self.ch and "output" in res:
                    out = res["output"]
        except Exception:
            return
        if out is not None:
            with self._lock:
                self.heater_output = bool(out)
                self.heater_output_ts = time.time()

    # -- actions ----------------------------------------------------------- #
    def _request_status(self):
        payload = json.dumps({
            "id": 100 + self.ch,
            "src": self.cfg["mqtt"].get("client_id", "heater_watchdog"),
            "method": "Switch.GetStatus",
            "params": {"id": self.ch},
        })
        self.client.publish(f"{self.dev}/rpc", payload, qos=1)

    def _send_heater_off(self):
        payload = json.dumps({
            "id": 42,
            "src": self.cfg["mqtt"].get("client_id", "heater_watchdog"),
            "method": "Switch.Set",
            "params": {"id": self.ch, "on": False},
        })
        self.client.publish(f"{self.dev}/rpc", payload, qos=1)
        self._last_off_sent = time.time()

    def _publish_status(self, heat_wanted, hb_age, reason):
        with self._lock:
            st = {
                "alive": True,
                "ts": int(time.time()),
                "armed": bool(self.cfg["armed"]),
                "maintenance": self._maintenance(),
                "heat_wanted": heat_wanted,
                "heater_output": self.heater_output,
                "shelly_online": self.shelly_online,
                "hb_age_sec": None if hb_age == float("inf") else round(hb_age, 1),
                "hb_run": self.last_hb_run,
                "reason": reason,
            }
        self.client.publish(self.cfg["status_topic"], json.dumps(st), qos=1, retain=True)

    def _maintenance(self):
        return os.path.exists(self.cfg["maintenance_file"])

    # -- main decision loop ------------------------------------------------ #
    def _decide_once(self):
        now = time.time()
        self._request_status()  # refresh heater state each cycle

        with self._lock:
            hb_age = (now - self.last_hb_ts) if self.last_hb_ts else float("inf")
            heating = self.last_hb_heating
            heater_output = self.heater_output
            heater_age = (now - self.heater_output_ts) if self.heater_output_ts else float("inf")

        # Heater state is "unknown" if we have never seen it or it is stale.
        if heater_age > max(3 * self.cfg["poll_sec"], 60):
            heater_output = None

        heat_wanted = (hb_age < self.cfg["stale_sec"]) and heating
        armed = bool(self.cfg["armed"])

        # Maintenance override: a human deliberately wants the heater on outside a run.
        if self._maintenance():
            self._publish_status(heat_wanted, hb_age, "maintenance-override")
            self.log.info("MAINTENANCE active -> standing down (heater left under manual control)")
            return

        # Startup grace: give a live run time to resume heartbeats after a (re)start.
        if (now - self.started) < self.cfg["startup_grace_sec"] and hb_age == float("inf"):
            self._publish_status(heat_wanted, hb_age, "startup-grace")
            self.log.info("startup grace (%.0fs left), no heartbeat yet -> no actuation",
                          self.cfg["startup_grace_sec"] - (now - self.started))
            return

        if heat_wanted:
            self._publish_status(heat_wanted, hb_age, "run-alive")
            self.log.debug("run %s alive, heating wanted (hb_age=%.0fs) -> heater stays under run control",
                           self.last_hb_run, hb_age)
            return

        # Heat NOT wanted.
        if heater_output is False:
            self._publish_status(heat_wanted, hb_age, "off-confirmed")
            self.log.debug("heat not wanted; heater confirmed OFF (hb_age=%.0fs)", hb_age)
            return

        # heater is ON or cannot be confirmed OFF -> act (fail-safe).
        reason = "heater-ON" if heater_output is True else "heater-state-unknown"
        if self.shelly_online is False:
            self.log.error("ALARM: heat not wanted and Shelly reports OFFLINE — cannot guarantee relay cut")
        if armed:
            self._send_heater_off()
            self.log.warning("INTERVENTION: heat not wanted (%s, hb_age=%.0fs) -> sent Switch.Set ch%d OFF",
                             reason, hb_age, self.ch)
            self._publish_status(heat_wanted, hb_age, f"cut-sent:{reason}")
        else:
            self.log.warning("OBSERVE-ONLY: heat not wanted (%s, hb_age=%.0fs) -> WOULD send ch%d OFF (not armed)",
                             reason, hb_age, self.ch)
            self._publish_status(heat_wanted, hb_age, f"would-cut:{reason}")

    def run(self):
        self.log.info("heater-watchdog starting: armed=%s stale=%ss poll=%ss grace=%ss device=%s ch%d",
                      self.cfg["armed"], self.cfg["stale_sec"], self.cfg["poll_sec"],
                      self.cfg["startup_grace_sec"], self.dev, self.ch)
        self.client.connect(self.cfg["mqtt"]["host"], self.cfg["mqtt"]["port"], keepalive=30)
        self.client.loop_start()
        try:
            while not self._stop.is_set():
                try:
                    self._decide_once()
                except Exception:
                    self.log.exception("decision loop error (continuing)")
                self._stop.wait(self.cfg["poll_sec"])
        finally:
            self.client.loop_stop()
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.log.info("heater-watchdog stopped")

    def stop(self, *a):
        self.log.info("stop requested")
        self._stop.set()


def build_logger(cfg):
    log = logging.getLogger("heater_watchdog")
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s")
    logging.Formatter.converter = time.gmtime

    sh = logging.StreamHandler(sys.stdout)   # -> journald
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    log.addHandler(sh)

    lf = cfg.get("log_file")
    if lf:
        os.makedirs(os.path.dirname(lf), exist_ok=True)
        fh = RotatingFileHandler(lf, maxBytes=5_000_000, backupCount=10)
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        log.addHandler(fh)
    return log


def main():
    ap = argparse.ArgumentParser(description="VPS heater-safety watchdog (ticket 0034)")
    ap.add_argument("--config", default="/home/claude-win/heater-watchdog/config.json")
    ap.add_argument("--once", action="store_true", help="run one decision cycle and exit (test)")
    ap.add_argument("--armed", choices=["true", "false"], help="override config armed flag")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.armed:
        cfg["armed"] = (args.armed == "true")

    log = build_logger(cfg)
    wd = HeaterWatchdog(cfg, log)

    if args.once:
        wd.client.connect(cfg["mqtt"]["host"], cfg["mqtt"]["port"], keepalive=30)
        wd.client.loop_start()
        time.sleep(1.0)
        wd._request_status()       # pre-fetch heater state so the single cycle sees it
        time.sleep(2.5)            # let retained state + the GetStatus reply arrive
        wd._decide_once()
        time.sleep(1.0)
        wd.client.loop_stop()
        wd.client.disconnect()
        return

    signal.signal(signal.SIGTERM, wd.stop)
    signal.signal(signal.SIGINT, wd.stop)
    wd.run()


if __name__ == "__main__":
    main()
