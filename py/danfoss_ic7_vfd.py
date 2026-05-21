#!/usr/bin/env python3
"""
Danfoss iC7 VFD control via Modbus TCP (TEST INTERFACE)

Supports:
- Connect test
- Read status
- Start/stop
- Set frequency

Run:
    python3 danfoss_ic7_vfd.py --ip 192.168.1.50 status
    python3 danfoss_ic7_vfd.py --ip 192.168.1.50 start --hz 10
    python3 danfoss_ic7_vfd.py --ip 192.168.1.50 stop
"""

import argparse
import time
from dataclasses import dataclass
from pymodbus.client import ModbusTcpClient


# =========================
# 🔧 CONFIG (EDIT THESE)
# =========================

REG_SPEED_SETPOINT = 20     # Hz * 100
REG_CONTROL_WORD  = 22
REG_STATUS_WORD   = 23

CONTROL_START = 1
CONTROL_STOP  = 0


# =========================
# 🧠 DATA STRUCTURE
# =========================

@dataclass
class VFDState:
    speed_setpoint_hz: float = 0.0
    status_word: int = 0
    is_running: bool = False


# =========================
# ⚙️ DRIVER
# =========================

class DanfossIC7VFD:

    def __init__(self, host, port=502, timeout=1.0, debug=True):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.debug = debug
        self.client = ModbusTcpClient(host, port=port, timeout=timeout)

    def connect(self):
        if self.debug:
            print(f"[IC7] Connecting to {self.host}:{self.port}...")
        ok = self.client.connect()
        if self.debug:
            print(f"[IC7] Connected: {ok}")
        return ok

    def close(self):
        self.client.close()

    # =========================
    # READ STATUS
    # =========================

    def get_status(self):
        rr = self.client.read_holding_registers(REG_SPEED_SETPOINT, 2)

        if rr.isError():
            raise Exception("Modbus read error")

        speed_raw = rr.registers[0]
        status = rr.registers[1]

        speed_hz = speed_raw / 100.0

        return VFDState(
            speed_setpoint_hz=speed_hz,
            status_word=status,
            is_running=(status != 0)
        )

    # =========================
    # CONTROL
    # =========================

    def set_frequency(self, hz):
        value = int(hz * 100)
        if self.debug:
            print(f"[IC7] Set frequency: {hz} Hz ({value})")

        rr = self.client.write_register(REG_SPEED_SETPOINT, value)

        if rr.isError():
            raise Exception("Write frequency failed")

    def start_forward(self, hz=None):
        if hz is not None:
            self.set_frequency(hz)

        if self.debug:
            print("[IC7] START")

        rr = self.client.write_register(REG_CONTROL_WORD, CONTROL_START)

        if rr.isError():
            raise Exception("Start failed")

    def stop(self):
        if self.debug:
            print("[IC7] STOP")

        rr = self.client.write_register(REG_CONTROL_WORD, CONTROL_STOP)

        if rr.isError():
            raise Exception("Stop failed")


# =========================
# 🧪 CLI TEST INTERFACE
# =========================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", required=True, help="IP address of iC7")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--hz", type=float, default=5.0)

    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status")
    sub.add_parser("stop")

    start_parser = sub.add_parser("start")
    start_parser.add_argument("--hz", type=float, required=False)

    args = parser.parse_args()

    vfd = DanfossIC7VFD(args.ip, args.port)

    if not vfd.connect():
        print("❌ Could not connect")
        return

    try:
        if args.cmd == "status":
            s = vfd.get_status()
            print("Status:")
            print(f"  Speed: {s.speed_setpoint_hz} Hz")
            print(f"  Running: {s.is_running}")
            print(f"  Raw status: {s.status_word}")

        elif args.cmd == "start":
            hz = args.hz if args.hz else 5.0
            vfd.start_forward(hz)
            print("✅ Started")

        elif args.cmd == "stop":
            vfd.stop()
            print("🛑 Stopped")

        else:
            print("Use: status | start | stop")

    finally:
        vfd.close()


if __name__ == "__main__":
    main()