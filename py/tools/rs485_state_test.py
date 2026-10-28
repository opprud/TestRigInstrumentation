#!/usr/bin/env python3
"""Stationary test: which RS485 state puts common-mode noise on the scope channels? (2026-10-28)

Motor stopped, heater off. The scope captures sweeps continuously (manual-mode acquire_loop, the SAME
capture path as a run) while the RS485 side is stepped through states, each logged with timestamps:

    idle   port closed, cable on the VFD, no traffic
    poll   runner-style polling every 5 s: Omron PV+SV and VFD status (the traffic of run B)
    off    the dongle's USB port disabled through sysfs (device vanishes -> transceiver unpowered)

UL and AE are switched to a FINE vertical range for the test (UL 0.04 V, AE 0.4 V) so the noise floor is not
the scope's quantisation step; the original ranges are read first and restored (and verified) at the end.

    sudo is needed for the sysfs port switch (passwordless on the Pi).
    py/.venv/bin/python tools/rs485_state_test.py --sequence idle,poll,idle,off,idle,poll --state-sec 240
"""
import argparse, json, os, subprocess, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path

PY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PY))
import acquire_scope_data as asd                       # noqa: E402

PORT_DEV = "/dev/ttyUSB0"
SYSFS_DISABLE = "/sys/bus/usb/devices/usb3/3-0:1.0/usb3-port2/disable"     # the FTDI RS485 cable (0403:6001)
FINE = {"UL": 0.04, "AE": 0.4}


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sysfs_disable(v: int):
    subprocess.run(["sudo", "-n", "sh", "-c", f"echo {v} > {SYSFS_DISABLE}"], check=True)


def ftdi_present() -> bool:
    return "0403:6001" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout


class Poller:
    """Same traffic pattern as test_runner: Omron PV+SV, VFD status, every tick_sec."""
    def __init__(self, tick_sec=5.0):
        self.tick = tick_sec; self.ok = 0; self.err = 0; self._ev = threading.Event(); self._t = None

    def start(self):
        self.ok = self.err = 0; self._ev.clear()
        self._t = threading.Thread(target=self._run, daemon=True); self._t.start()

    def _run(self):
        from omron_temp_poll import E5CCTool
        from rs510_vfd_control import RS510VFDController
        om = E5CCTool(port=PORT_DEV, baudrate=9600, parity="N", bytesize=8, stopbits=1, timeout=2.0, unit_id=2,
                      pv_address=0x2000, sv_address=0x2103, scale=1.0, debug=False)
        vfd = RS510VFDController(port=PORT_DEV, slave_id=3, baudrate=9600, timeout=2.0, debug=False)
        try:
            vfd.connect()
        except Exception:
            pass
        while not self._ev.is_set():
            for fn in (om.read_pv_c, om.read_sv_c, vfd.get_status):
                try:
                    fn(); self.ok += 1
                except Exception:
                    self.err += 1
            self._ev.wait(self.tick)
        for fn in (getattr(om, "close", None), getattr(vfd, "disconnect", None)):
            try:
                fn and fn()
            except Exception:
                pass

    def stop(self):
        self._ev.set()
        if self._t: self._t.join(timeout=15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sequence", default="idle,poll,idle,off,idle,poll")
    ap.add_argument("--state-sec", type=float, default=240)
    ap.add_argument("--lead-sec", type=float, default=60)
    ap.add_argument("--interval-sec", type=float, default=12)
    a = ap.parse_args()
    seq = a.sequence.split(",")

    cfg = json.load(open(PY / "config.json"))
    ip, port = cfg["scope_ip"], int((cfg.get("scope") or {}).get("preferred_port", 5025))
    channels = [c for c in cfg["channels"] if c.get("enabled", True)]
    run_id = asd.make_run_id() + "_rs485state"
    run_dir = PY / "data" / "runs" / run_id; run_dir.mkdir(parents=True, exist_ok=True)

    total = a.lead_sec + a.state_sec * len(seq)
    ev = threading.Event()
    cfg["store"].update(output_file=str(run_dir / f"scope_{run_id}.h5"), timestamped=False, time_axis=False)
    cfg["acquisition"] = {"points": "MAX", "points_mode": "RAW", "waveform_format": "WORD", "trigger_sweep": "AUTO",
                          "acq_type": "NORM", "interval_sec": a.interval_sec,
                          "samples": int(total / a.interval_sec) + 4, "stop_event": ev}
    cfg["_profile_cfg"] = {"scope_channels": {k: {"volt_range": v} for k, v in FINE.items()}}
    cfg["scope_fft"] = {}                                      # leave the scope's FFT as it is
    before = {}
    for ch, src in (("UL", "CHAN1"), ("AE", "CHAN2")):
        before[ch] = float(asd.socket_query_line(ip, port, f":{src}:RANG?"))
    print(f"[test] run {run_id}; restoring ranges afterwards: {before}", flush=True)

    states, poller = [], Poller()
    cap = threading.Thread(target=lambda: asd.acquire_loop(cfg), daemon=False); cap.start()
    t0 = time.time()
    try:
        time.sleep(a.lead_sec)
        for s in seq:
            rec = {"state": s, "start_utc": utc()}
            print(f"[test] {rec['start_utc']}  STATE {s} for {a.state_sec:.0f}s", flush=True)
            if s == "poll":
                poller.start()
            elif s == "off":
                sysfs_disable(1); time.sleep(2); rec["ftdi_present_after_off"] = ftdi_present()
            elif s == "idle":
                if not os.path.exists(PORT_DEV) or not ftdi_present():
                    sysfs_disable(0)
                    for _ in range(30):
                        if os.path.exists(PORT_DEV): break
                        time.sleep(1)
            time.sleep(a.state_sec)
            if s == "poll":
                poller.stop(); rec["poll_ok"], rec["poll_err"] = poller.ok, poller.err
            rec["end_utc"] = utc(); states.append(rec)
    finally:
        try: poller.stop()
        except Exception: pass
        try: sysfs_disable(0)
        except Exception as e: print("[test] !! could not re-enable the port:", e, flush=True)
        ev.set(); cap.join(timeout=60)
        asd._apply_scope_channel_settings(ip, port, channels, {"scope_channels": {k: {"volt_range": v} for k, v in before.items()}}, strict=False)
        after = {ch: float(asd.socket_query_line(ip, port, f":{src}:RANG?")) for ch, src in (("UL", "CHAN1"), ("AE", "CHAN2"))}
        json.dump({"run_id": run_id, "states": states, "ranges_before": before, "ranges_after": after,
                   "fine_ranges": FINE, "elapsed_s": time.time() - t0}, open(run_dir / "states.json", "w"), indent=1)
        print(f"[test] done. ranges before {before} after {after}; port present: {os.path.exists(PORT_DEV)}", flush=True)


if __name__ == "__main__":
    main()
