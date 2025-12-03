#!/usr/bin/env python3
"""
Telemetry data collection module for test rig instrumentation
Handles RP2040 load cell/tachometer and Modbus temperature sensors
"""

import json
import subprocess
import os
from typing import Dict, Optional, Any
from shared_modbus_manager import get_shared_modbus_manager, ModbusConfig


class TelemetryReader:
    """
    Unified interface for reading telemetry data from various sensors
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize telemetry readers based on config

        Args:
            config: Telemetry configuration dict with:
                - enabled: bool
                - rp2040_port: str (optional)
                - modbus_config: str (optional path to modbus config)
        """
        self.enabled = config.get("enabled", False)
        self.rp2040_port = config.get("rp2040_port")
        self.modbus_config_path = config.get("modbus_config")

        # Modbus manager and device config
        self.modbus_manager = None
        self.omron_unit_id = None
        self.omron_pv_address = None
        self.omron_scale = 1.0

        if self.enabled:
            self._validate_config()
            self._init_modbus()

    def _validate_config(self):
        """Validate telemetry configuration"""
        if self.rp2040_port and "XXXX" in self.rp2040_port:
            print(f"⚠️  Warning: RP2040 port contains placeholder: {self.rp2040_port}")
            print("   Telemetry will be disabled until port is configured")
            self.enabled = False

    def _init_modbus(self):
        """Initialize Modbus connection for temperature sensor"""
        if not self.modbus_config_path:
            return

        try:
            # Load Modbus configuration
            if not os.path.exists(self.modbus_config_path):
                print(f"⚠️  Warning: Modbus config not found: {self.modbus_config_path}")
                return

            with open(self.modbus_config_path, 'r') as f:
                modbus_cfg = json.load(f)

            # Get connection settings
            conn = modbus_cfg.get("connection", {})

            # Get Omron E5CC device settings
            omron = modbus_cfg.get("devices", {}).get("omron_e5cc", {})
            self.omron_unit_id = omron.get("unit_id", 2)

            # Parse register addresses (handle hex strings)
            pv_addr_str = omron.get("registers", {}).get("pv_address", "0x2000")
            self.omron_pv_address = int(pv_addr_str, 0)  # Auto-detect base (0x for hex)
            self.omron_scale = omron.get("scale", 1.0)

            # Create Modbus manager
            modbus_config = ModbusConfig(
                port=conn.get("port", "auto"),
                baudrate=conn.get("baudrate", 9600),
                parity=conn.get("parity", "N"),
                bytesize=conn.get("bytesize", 8),
                stopbits=conn.get("stopbits", 1),
                timeout=conn.get("timeout", 2.0),
                debug=False
            )

            self.modbus_manager = get_shared_modbus_manager(modbus_config)

        except Exception as e:
            print(f"⚠️  Warning: Failed to initialize Modbus: {e}")
            self.modbus_manager = None

    def read_rp2040(self) -> Optional[Dict[str, Any]]:
        """
        Read load cell and tachometer data from RP2040

        Returns:
            Dict with load_g, rpm, timestamps, or None if failed
        """
        if not self.enabled or not self.rp2040_port:
            return None

        try:
            # Call util_tool.py with --json flag
            result = subprocess.run(
                ["python", "util_tool.py", "--port", self.rp2040_port, "--json", "load"],
                capture_output=True,
                text=True,
                timeout=2.0
            )

            if result.returncode != 0:
                print(f"⚠️  RP2040 read failed: {result.stderr}")
                return None

            # Parse JSON output
            data = json.loads(result.stdout)

            # Extract relevant fields
            telemetry = {
                "load_g": data.get("mass_g", 0.0),
                "load_timestamp_ms": data.get("ts", 0),
                "load_raw": data.get("raw", 0),
            }

            # Try to get RPM data
            rpm_result = subprocess.run(
                ["python", "util_tool.py", "--port", self.rp2040_port, "--json", "speed"],
                capture_output=True,
                text=True,
                timeout=2.0
            )

            if rpm_result.returncode == 0:
                rpm_data = json.loads(rpm_result.stdout)
                telemetry["rpm"] = rpm_data.get("rpm", 0.0)
                telemetry["rpm_timestamp_ms"] = rpm_data.get("ts", 0)
                telemetry["rpm_pulses"] = rpm_data.get("pulses", 0)
                telemetry["rpm_period_ms"] = rpm_data.get("period_ms", 0)

            return telemetry

        except subprocess.TimeoutExpired:
            print("⚠️  RP2040 read timeout")
            return None
        except json.JSONDecodeError as e:
            print(f"⚠️  Failed to parse RP2040 JSON: {e}")
            return None
        except Exception as e:
            print(f"⚠️  RP2040 error: {e}")
            return None

    def read_modbus_temperature(self) -> Optional[Dict[str, Any]]:
        """
        Read temperature from Modbus device (e.g., Omron E5CC)

        Returns:
            Dict with temperature_c, or None if not configured/failed
        """
        if not self.enabled or not self.modbus_manager:
            return None

        try:
            # Read PV (Process Value) register from Omron E5CC
            raw_value = self.modbus_manager.read_holding_register(
                self.omron_unit_id,
                self.omron_pv_address
            )

            if raw_value is None:
                print("⚠️  Modbus temperature read failed")
                return None

            # Apply scale factor to get temperature in °C
            temperature_c = raw_value * self.omron_scale

            return {
                "temperature_c": temperature_c,
                "temperature_raw": raw_value
            }

        except Exception as e:
            print(f"⚠️  Modbus temperature error: {e}")
            return None

    def read_all(self) -> Dict[str, Any]:
        """
        Read all available telemetry data

        Returns:
            Combined telemetry dict with all available sensor data
        """
        if not self.enabled:
            return {}

        telemetry = {}

        # Read RP2040 sensors
        rp2040_data = self.read_rp2040()
        if rp2040_data:
            telemetry.update(rp2040_data)

        # Read Modbus temperature
        temp_data = self.read_modbus_temperature()
        if temp_data:
            telemetry.update(temp_data)

        return telemetry

    def get_metadata(self) -> Dict[str, Any]:
        """
        Get telemetry configuration metadata for HDF5 file

        Returns:
            Dict with telemetry configuration info
        """
        metadata = {
            "telemetry_enabled": self.enabled,
            "rp2040_port": self.rp2040_port if self.enabled else None,
            "modbus_config": self.modbus_config_path if self.enabled else None,
        }

        # Add Modbus device info if configured
        if self.modbus_manager:
            metadata["omron_unit_id"] = self.omron_unit_id
            metadata["omron_pv_address"] = f"0x{self.omron_pv_address:04X}"

        return metadata


def add_telemetry_to_sweep(sweep_group, telemetry_data: Dict[str, Any]):
    """
    Add telemetry data as attributes to an HDF5 sweep group

    Args:
        sweep_group: h5py Group object for the sweep
        telemetry_data: Dict with telemetry readings
    """
    if not telemetry_data:
        return

    # Add each telemetry value as an attribute
    for key, value in telemetry_data.items():
        if value is not None:
            sweep_group.attrs[key] = value


# Example usage
if __name__ == "__main__":
    # Test with config
    test_config = {
        "enabled": True,
        "rp2040_port": "/dev/tty.usbmodem123456",
        "modbus_config": "modbus_config.json"
    }

    reader = TelemetryReader(test_config)
    print("Telemetry configuration:")
    print(json.dumps(reader.get_metadata(), indent=2))

    print("\nReading telemetry data...")
    data = reader.read_all()
    print(json.dumps(data, indent=2))
