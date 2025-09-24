#!/usr/bin/env python3
"""
RS510 Frequency Converter Control (Modbus RTU via RS485)

RS PRO RS510 Series VFD control via Modbus RTU.
Supports motor speed control, start/stop, and monitoring.
Uses shared Modbus connection manager to avoid conflicts with other devices.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from shared_modbus_manager import get_shared_modbus_manager, ModbusConfig


class VFDCommand(Enum):
    STOP = 0
    RUN_FORWARD = 1
    RUN_REVERSE = 2
    EMERGENCY_STOP = 3


@dataclass
class VFDState:
    frequency_cmd_hz: float = 0.0  # Command frequency
    frequency_out_hz: float = 0.0  # Actual output frequency
    frequency_hz: float = 0.0      # Alias for output frequency (API compatibility)
    frequency_command_hz: float = 0.0  # Alias for command frequency (API compatibility)
    base_freq_hz: float = 0.0
    max_freq_hz: float = 0.0
    accel_time_s: float = 0.0
    decel_time_s: float = 0.0
    run_command: VFDCommand = VFDCommand.STOP
    status: VFDCommand = VFDCommand.STOP  # Alias for run_command (API compatibility)
    output_current_a: float = 0.0
    dc_bus_voltage_v: float = 0.0
    fault_code: int = 0
    temperature_c: float = 0.0
    is_running: bool = False
    is_fault: bool = False
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
        # Create shared Modbus configuration with improved timeout handling
        self.modbus_config = ModbusConfig(
            port=port,
            baudrate=baudrate,
            parity="N",
            bytesize=8,
            stopbits=1,
            timeout=timeout,
            debug=debug,
            max_retries=2,           # Fewer retries for faster failure detection
            retry_delay=0.3,         # Shorter delay between retries
            connection_timeout=3.0,  # Shorter connection timeout
            health_check_interval=5.0  # More frequent health checks
        )

        # Get shared manager instance
        self.manager = get_shared_modbus_manager(self.modbus_config)

        self.slave_id = slave_id
        self.debug = debug

        if self.debug:
            print(f"[DEBUG] RS510 VFD using shared Modbus manager for unit {slave_id}")

    def connect(self) -> bool:
        # Connection is managed by the shared manager
        return True

    def disconnect(self):
        # Don't close the shared connection - it will be managed by the manager
        pass

    def _read(self, address: int) -> Optional[int]:
        result = self.manager.read_holding_register(self.slave_id, address)
        if result is None and self.debug:
            print(f"Read error {hex(address)}: Failed to read from RS510 unit {self.slave_id}")
        return result

    def _write(self, address: int, value: int) -> bool:
        success = self.manager.write_holding_register(self.slave_id, address, value)
        if not success and self.debug:
            print(f"Write error {hex(address)}: Failed to write to RS510 unit {self.slave_id}")
        return success

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

    def start_reverse(self, hz: Optional[float] = None) -> bool:
        if hz is not None:
            self.set_frequency(hz)
        return self.set_run_command(VFDCommand.RUN_REVERSE)

    def emergency_stop(self) -> bool:
        return self.set_run_command(VFDCommand.EMERGENCY_STOP)
        
    def get_status(self) -> VFDState:
        st = VFDState(timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))

        # Read command frequency
        val = self._read(self.REG_FREQUENCY_CMD)
        if val is not None:
            st.frequency_cmd_hz = val / 100.0
            st.frequency_command_hz = st.frequency_cmd_hz  # API alias

        # For now, assume output frequency equals command frequency
        # TODO: Add actual output frequency register if available
        st.frequency_out_hz = st.frequency_cmd_hz
        st.frequency_hz = st.frequency_out_hz  # API alias

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
                st.status = st.run_command  # API alias
            except ValueError:
                pass

        val = self._read(self.REG_FAULT_CODE)
        if val is not None:
            st.fault_code = val

        # Set derived status flags
        st.is_running = st.run_command in (VFDCommand.RUN_FORWARD, VFDCommand.RUN_REVERSE)
        st.is_fault = st.fault_code != 0

        # TODO: Add registers for these values if available in the VFD manual
        st.output_current_a = 0.0  # Register address unknown
        st.dc_bus_voltage_v = 0.0  # Register address unknown
        st.temperature_c = 0.0     # Register address unknown

        return st

    def get_status_json(self) -> str:
        st = self.get_status()
        # Convert enums to strings for JSON serialization
        status_dict = st.__dict__.copy()
        status_dict['run_command'] = st.run_command.name if st.run_command else None
        status_dict['status'] = st.status.name if st.status else None
        return json.dumps(status_dict, indent=2)

    def get_health_status(self) -> dict:
        """Get connection health status."""
        return self.manager.get_health_status()


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
    g.add_argument("--health", action="store_true", help="Show connection health")
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
        elif args.health:
            health = vfd.get_health_status()
            print(json.dumps(health, indent=2))
        elif args.json:
            print(vfd.get_status_json())
        else:
            st = vfd.get_status()
            print_status_human(st)
    finally:
        vfd.disconnect()


if __name__ == "__main__":
    main()