#!/usr/bin/env python3
"""
Telemetry collector for test rig sensors.
Gathers data from:
- RP2040 (load cell + tachometer via util_tool.py)
- Omron E5CC (temperature via Modbus)
- RS510 VFD (motor speed/frequency via Modbus)

Returns unified telemetry dictionary for HDF5 metadata.
"""
import json
import subprocess
import sys
from typing import Optional, Dict, Any
from datetime import datetime, UTC

def read_rp2040_telemetry(port: str = None) -> Optional[Dict[str, Any]]:
    """
    Read load and speed from RP2040 via util_tool.py.
    Returns dict with: mass_g, rpm, raw_load, ts_load, ts_speed
    Returns None if device not available or errors occur.
    """
    if not port:
        return None

    try:
        # Read load cell
        result_load = subprocess.run(
            ["python3", "util_tool.py", "--port", port, "--json", "load"],
            capture_output=True,
            text=True,
            timeout=2.0
        )

        # Read tachometer
        result_speed = subprocess.run(
            ["python3", "util_tool.py", "--port", port, "--json", "speed"],
            capture_output=True,
            text=True,
            timeout=2.0
        )

        telemetry = {}

        if result_load.returncode == 0:
            load_data = json.loads(result_load.stdout.strip())
            if load_data.get("status") == "OK":
                telemetry["mass_g"] = load_data.get("mass_g")
                telemetry["raw_load"] = load_data.get("raw")
                telemetry["ts_load"] = load_data.get("ts")

        if result_speed.returncode == 0:
            speed_data = json.loads(result_speed.stdout.strip())
            if speed_data.get("status") == "OK":
                telemetry["rpm"] = speed_data.get("rpm")
                telemetry["period_ms"] = speed_data.get("period_ms")
                telemetry["pulses"] = speed_data.get("pulses")
                telemetry["ts_speed"] = speed_data.get("ts")

        return telemetry if telemetry else None

    except Exception as e:
        print(f"Warning: RP2040 telemetry failed: {e}", file=sys.stderr)
        return None


def read_temperature(modbus_config: Optional[str] = None) -> Optional[float]:
    """
    Read temperature from Omron E5CC via omron_temp_poll.py.
    Returns temperature in °C or None if unavailable.
    """
    if not modbus_config:
        return None

    try:
        cmd = ["python3", "omron_temp_poll.py", "--config", modbus_config, "--json", "pv"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0)

        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            if data.get("status") == "OK":
                return data.get("temperature_c")

    except Exception as e:
        print(f"Warning: Temperature read failed: {e}", file=sys.stderr)

    return None


def read_vfd_status(modbus_config: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Read VFD status via rs510_vfd_control.py.
    Returns dict with frequency_hz and any other available parameters.
    Returns None if unavailable.
    """
    if not modbus_config:
        return None

    try:
        # Note: rs510_vfd_control.py may need a 'status' command - check implementation
        # For now, return None until we verify the VFD command interface
        return None

    except Exception as e:
        print(f"Warning: VFD status read failed: {e}", file=sys.stderr)
        return None


def collect_all_telemetry(
    rp2040_port: Optional[str] = None,
    modbus_config: Optional[str] = None,
    include_timestamp: bool = True
) -> Dict[str, Any]:
    """
    Collect telemetry from all available sensors.

    Args:
        rp2040_port: Serial port for RP2040 (e.g., "/dev/tty.usbmodem123")
        modbus_config: Path to modbus_config.json
        include_timestamp: Add UTC timestamp to telemetry

    Returns:
        Dictionary with all available telemetry data
    """
    telemetry = {}

    if include_timestamp:
        telemetry["timestamp_utc"] = datetime.now(UTC).isoformat()

    # RP2040 sensors
    rp2040_data = read_rp2040_telemetry(rp2040_port)
    if rp2040_data:
        telemetry.update(rp2040_data)

    # Temperature
    temp = read_temperature(modbus_config)
    if temp is not None:
        telemetry["temperature_c"] = temp

    # VFD status
    vfd = read_vfd_status(modbus_config)
    if vfd:
        telemetry.update(vfd)

    return telemetry


def main():
    """CLI for testing telemetry collection."""
    import argparse

    parser = argparse.ArgumentParser(description="Collect telemetry from test rig sensors")
    parser.add_argument("--rp2040-port", help="RP2040 serial port")
    parser.add_argument("--modbus-config", help="Path to modbus_config.json")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    telemetry = collect_all_telemetry(
        rp2040_port=args.rp2040_port,
        modbus_config=args.modbus_config
    )

    if args.json:
        print(json.dumps(telemetry, indent=2))
    else:
        print("Telemetry Data:")
        for key, value in telemetry.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
