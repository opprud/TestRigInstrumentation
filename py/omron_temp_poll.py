#!/usr/bin/env python3
"""
Omron E5CC temperature tool (Modbus RTU, pymodbus)

- Read PV (process value) from 0x2000 (default)
- Read/Write SV (setpoint) at 0x2103 (default)
- Default scale = 1.0 (whole-degree). Use --scale 0.1 if your E5CC is in 0.1°C mode.
- Uses shared Modbus connection manager to avoid conflicts with other devices
"""

import argparse
import json
import sys
import time
from typing import Optional, Tuple

from shared_modbus_manager import get_shared_modbus_manager, ModbusConfig


class E5CCTool:
    def __init__(
        self,
        port: str,
        baudrate: int,
        parity: str,
        bytesize: int,
        stopbits: int,
        timeout: float,
        unit_id: int,
        pv_address: int,
        sv_address: int,
        scale: float,
        debug: bool = False,
    ):
        # Create shared Modbus configuration
        self.modbus_config = ModbusConfig(
            port=port,
            baudrate=baudrate,
            parity=parity,
            bytesize=bytesize,
            stopbits=stopbits,
            timeout=timeout,
            debug=debug
        )

        # Get shared manager instance
        self.manager = get_shared_modbus_manager(self.modbus_config)

        self.unit_id = unit_id
        self.pv_address = pv_address
        self.sv_address = sv_address
        self.scale = scale
        self.debug = debug

        if self.debug:
            print(f"[DEBUG] E5CC using shared Modbus manager for unit {unit_id}", file=sys.stderr)

    def close(self):
        # Don't close the shared connection - it will be managed by the manager
        pass

    # ---------- low-level helpers ----------
    def _read_u16(self, address: int) -> int:
        result = self.manager.read_holding_register(self.unit_id, address)
        if result is None:
            raise RuntimeError(f"Failed to read register 0x{address:04X} from E5CC unit {self.unit_id}")
        return result

    def _write_u16(self, address: int, value: int):
        success = self.manager.write_holding_register(self.unit_id, address, value)
        if not success:
            raise RuntimeError(f"Failed to write register 0x{address:04X} to E5CC unit {self.unit_id}")

    # ---------- high-level ----------
    def read_pv_c(self) -> float:
        raw = self._read_u16(self.pv_address)
        return raw * self.scale

    def read_sv_c(self) -> float:
        raw = self._read_u16(self.sv_address)
        return raw * self.scale

    def write_sv_c(self, value_c: float):
        raw = int(round(value_c / self.scale))
        if not (0 <= raw <= 0xFFFF):
            raise ValueError("SV out of 16-bit range after scaling")
        self._write_u16(self.sv_address, raw)


def main():
    ap = argparse.ArgumentParser(description="Omron E5CC temperature tool (PV/SV) over Modbus RTU")
    # Serial
    ap.add_argument("--port", default="/dev/tty.usbserial-FT07QKDX", help="Serial port (e.g. /dev/ttyUSB0, COM3)")
    ap.add_argument("--baudrate", type=int, default=9600, help="Baudrate (default: 9600, was 57600)")
    ap.add_argument("--parity", choices=["N", "E", "O"], default="N", help="Parity (default: N, was E)")
    ap.add_argument("--bytesize", type=int, choices=[7, 8], default=8, help="Data bits (default: 8)")
    ap.add_argument("--stopbits", type=int, choices=[1, 2], default=1, help="Stop bits (default: 1)")
    ap.add_argument("--timeout", type=float, default=1.5, help="Timeout seconds (default: 1.5)")
    ap.add_argument("--unit", type=int, default=2, help="Modbus unit/slave/device_id (default: 2)")

    # Registers & scale
    ap.add_argument("--pv-address", type=lambda x: int(x, 0), default=0x2000, help="PV holding register (default: 0x2000)")
    ap.add_argument("--sv-address", type=lambda x: int(x, 0), default=0x2103, help="SV holding register (default: 0x2103)")
    ap.add_argument("--scale", type=float, default=1.0, help="Scale (raw * scale = °C). Use 0.1 for 0.1°C mode (default: 1.0)")

    # Actions
    ap.add_argument("--get-pv", action="store_true", help="Read current temperature (PV)")
    ap.add_argument("--get-sv", action="store_true", help="Read setpoint (SV)")
    ap.add_argument("--set-sv", type=float, help="Write setpoint (°C)")
    ap.add_argument("--interval", type=float, default=1.0, help="Polling interval for --get-pv loop")
    ap.add_argument("--once", action="store_true", help="Read once (with --get-pv or --get-sv)")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--debug", action="store_true", help="Debug prints")

    args = ap.parse_args()

    tool = E5CCTool(
        port=args.port,
        baudrate=args.baudrate,
        parity=args.parity,
        bytesize=args.bytesize,
        stopbits=args.stopbits,
        timeout=args.timeout,
        unit_id=args.unit,
        pv_address=args.pv_address,
        sv_address=args.sv_address,
        scale=args.scale,
        debug=args.debug,
    )

    def out(obj):
        if args.json:
            print(json.dumps(obj))
        else:
            if isinstance(obj, dict):
                # human friendly
                if "temp_C" in obj:
                    print(f"{obj['temp_C']:.1f} °C")
                else:
                    print(obj)
            else:
                print(obj)

    try:
        # Write SV
        if args.set_sv is not None:
            tool.write_sv_c(args.set_sv)
            out({"ok": True, "set_sv_C": args.set_sv})
            # fall through: user might also want to confirm reading after write

        # Single reads
        if args.once:
            if args.get_pv:
                pv = tool.read_pv_c()
                out({"temp_C": pv, "kind": "PV", "addr": args.pv_address, "unit": args.unit})
            if args.get_sv:
                sv = tool.read_sv_c()
                out({"temp_C": sv, "kind": "SV", "addr": args.sv_address, "unit": args.unit})
            if not (args.get_pv or args.get_sv or args.set_sv is not None):
                out({"note": "Nothing to do. Use --get-pv, --get-sv, or --set-sv."})
            return

        # Continuous PV polling
        if args.get_pv and not args.get_sv:
            while True:
                try:
                    pv = tool.read_pv_c()
                    out({"ts_ms": int(time.time()*1000), "temp_C": pv, "kind": "PV"})
                except Exception as e:
                    out({"error": str(e)})
                time.sleep(args.interval)
            # no return (Ctrl+C to stop)

        # If neither mode selected, do a friendly hint
        if not (args.get_pv or args.get_sv or args.set_sv is not None):
            out({"note": "Nothing to do. Try --get-pv --once, --get-sv --once, or --set-sv 65."})
        else:
            # If user asked to read SV continuously, just read once by default (unless they specify --once)
            if args.get_sv and not args.once:
                sv = tool.read_sv_c()
                out({"temp_C": sv, "kind": "SV", "addr": args.sv_address, "unit": args.unit})

    finally:
        tool.close()


if __name__ == "__main__":
    main()