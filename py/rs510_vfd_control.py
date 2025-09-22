#!/usr/bin/env python3
"""
RS510 Frequency Converter Control (Modbus RTU via RS485)

RS PRO RS510 Series VFD control via Modbus RTU.
Supports motor speed control, start/stop, and monitoring.
"""

import argparse
import inspect
import json
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pymodbus.client import ModbusSerialClient


class VFDCommand(Enum):
    STOP = 0
    RUN_FORWARD = 1
    RUN_REVERSE = 2
    EMERGENCY_STOP = 3


@dataclass
class VFDState:
    frequency_cmd_hz: float = 0.0
    frequency_out_hz: float = 0.0
    base_freq_hz: float = 0.0
    max_freq_hz: float = 0.0
    accel_time_s: float = 0.0
    decel_time_s: float = 0.0
    run_command: VFDCommand = VFDCommand.STOP
    fault_code: int = 0
    timestamp: str = ""


class RS510VFDController:
    REG_RUN_COMMAND = 0x2501    #7
    REG_FREQUENCY_CMD = 0x2502  #8
    REG_BASE_FREQ = 0x000B
    REG_MAX_FREQ = 0x000C
    REG_ACCEL = 0x000E
    REG_DECEL = 0x000F
    REG_FAULT_CODE = 0x0015  # guessed from manual, may differ

    def __init__(self, port: str, slave_id: int = 3, baudrate: int = 9600,
                 timeout: float = 1.0, debug: bool = True):
        self.port = port
        self.slave_id = slave_id
        self.baudrate = baudrate
        self.timeout = timeout
        self.debug = debug
        self.client = None
        self._unit_kwarg = None

    def connect(self) -> bool:
        self.client = ModbusSerialClient(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self.timeout
        )
        if not self.client.connect():
            return False
        self._unit_kwarg = self._detect_unit_kwarg()
        return True

    def disconnect(self):
        if self.client:
            self.client.close()

    def _detect_unit_kwarg(self) -> Optional[str]:
        sig = inspect.signature(self.client.read_holding_registers)
        for key in ("unit", "slave", "device_id"):
            if key in sig.parameters:
                return key
        return None

    def _read(self, address: int) -> Optional[int]:
        if not self.client or not self._unit_kwarg:
            return None
        try:
            kwargs = {self._unit_kwarg: self.slave_id}
            rr = self.client.read_holding_registers(address=address, count=1, **kwargs)
            if rr.isError():
                return None
            return rr.registers[0]
        except Exception as e:
            if self.debug:
                print(f"Read error {hex(address)}: {e}")
            return None

    def _write(self, address: int, value: int) -> bool:
        if not self.client or not self._unit_kwarg:
            return False
        try:
            kwargs = {self._unit_kwarg: self.slave_id}
            rr = self.client.write_register(address, value, **kwargs)
            return not rr.isError()
        except Exception as e:
            if self.debug:
                print(f"Write error {hex(address)}: {e}")
            return False

    def set_frequency(self, hz: float) -> bool:
        value = int(hz * 100)
        if self.debug:
            print(f"Set frequency {hz:.2f} Hz → {value}")
        return self._write(self.REG_FREQUENCY_CMD, value)

    def set_run_command(self, cmd: VFDCommand) -> bool:
        if self.debug:
            print(f"Run command {cmd.name}")
        return self._write(self.REG_RUN_COMMAND, cmd.value)

    def stop(self) -> bool:
        return self.set_run_command(VFDCommand.STOP)

    def start_forward(self, hz: Optional[float] = None) -> bool:
        if hz is not None:
            self.set_frequency(hz)
        return self.set_run_command(VFDCommand.RUN_FORWARD)
        
    def get_status(self) -> VFDState:
        st = VFDState(timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))

        val = self._read(self.REG_FREQUENCY_CMD)
        if val is not None:
            st.frequency_cmd_hz = val / 100.0

        val = self._read(self.REG_BASE_FREQ)
        if val is not None:
            st.base_freq_hz = val / 100.0

        val = self._read(self.REG_MAX_FREQ)
        if val is not None:
            st.max_freq_hz = val / 100.0

        val = self._read(self.REG_ACCEL)
        if val is not None:
            st.accel_time_s = val / 10.0  # tenths of a second

        val = self._read(self.REG_DECEL)
        if val is not None:
            st.decel_time_s = val / 10.0

        val = self._read(self.REG_RUN_COMMAND)
        if val is not None:
            try:
                st.run_command = VFDCommand(val)
            except ValueError:
                pass

        val = self._read(self.REG_FAULT_CODE)
        if val is not None:
            st.fault_code = val

        return st

    def get_status_json(self) -> str:
        st = self.get_status()
        return json.dumps(st.__dict__, indent=2)


def print_status_human(state: VFDState):
    print(f"RS510 Status @ {state.timestamp}")
    print(f"  Frequency Command : {state.frequency_cmd_hz:.2f} Hz")
    print(f"  Base Frequency    : {state.base_freq_hz:.2f} Hz")
    print(f"  Max Frequency     : {state.max_freq_hz:.2f} Hz")
    print(f"  Accel Time        : {state.accel_time_s:.1f} s")
    print(f"  Decel Time        : {state.decel_time_s:.1f} s")
    print(f"  Run Command       : {state.run_command.name}")
    if state.fault_code:
        print(f"  Fault Code        : {state.fault_code} ⚠️")
    else:
        print(f"  Fault Code        : None")


def main():
    p = argparse.ArgumentParser(description="RS510 VFD control over Modbus RTU")
    p.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyUSB0)")
    p.add_argument("--slave", type=int, default=3, help="Slave address (default 3)")
    p.add_argument("--baudrate", type=int, default=9600)
    p.add_argument("--debug", action="store_true")

    g = p.add_mutually_exclusive_group()
    g.add_argument("--status", action="store_true")
    g.add_argument("--json", action="store_true")
    g.add_argument("--start", type=float, help="Start forward at freq (Hz)")
    g.add_argument("--stop", action="store_true")

    args = p.parse_args()
    vfd = RS510VFDController(args.port, args.slave, args.baudrate, debug=args.debug)

    if not vfd.connect():
        print("❌ Could not connect")
        sys.exit(1)

    try:
        if args.start is not None:
            vfd.start_forward(args.start)
            print(f"Motor started at {args.start} Hz")
        elif args.stop:
            vfd.stop()
            print("Motor stop sent")
        elif args.json:
            print(vfd.get_status_json())
        else:
            st = vfd.get_status()
            print_status_human(st)
    finally:
        vfd.disconnect()


if __name__ == "__main__":
    main()