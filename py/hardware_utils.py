#!/usr/bin/env python3
"""
Hardware utility functions for port detection and device identification.

Provides reusable functions for auto-detecting serial devices:
- FTDI RS485 adapters
- RP2040 microcontrollers
- Other USB serial devices
"""

import serial.tools.list_ports
from typing import Optional, List, Dict, Any


# Vendor/Product IDs for common devices
DEVICE_IDS = {
    'rp2040': [
        {'vid': 0x2E8A, 'pid': 0x0005, 'desc': 'Raspberry Pi RP2040'},
        {'vid': 0x2E8A, 'pid': 0x000A, 'desc': 'Seeed Studio XIAO RP2040'},
        {'vid': 0x2886, 'pid': 0x8027, 'desc': 'Seeed Studio XIAO RP2040'},
    ],
    'ftdi': [
        {'vid': 0x0403, 'pid': 0x6001, 'desc': 'FTDI FT232R'},
        {'vid': 0x0403, 'pid': 0x6014, 'desc': 'FTDI FT232H'},
        {'vid': 0x0403, 'pid': 0x6015, 'desc': 'FTDI FT-X'},
    ]
}


def detect_ftdi_port(prefer_serial_number: Optional[str] = None, debug: bool = False) -> Optional[str]:
    """
    Auto-detect FTDI RS485 adapter port.

    Args:
        prefer_serial_number: If specified, prefer FTDI device with this serial number
        debug: Print debug information

    Returns:
        Device path (e.g., '/dev/tty.usbserial-FTDI485') or None if not found
    """
    ports = serial.tools.list_ports.comports()
    ftdi_ports = []

    for port in ports:
        if port.vid and port.pid:
            # Check if this is an FTDI device
            for device in DEVICE_IDS['ftdi']:
                if port.vid == device['vid'] and port.pid == device['pid']:
                    ftdi_ports.append({
                        'device': port.device,
                        'description': port.description,
                        'serial_number': port.serial_number,
                        'vid': port.vid,
                        'pid': port.pid,
                        'device_type': device['desc']
                    })
                    break

    if debug:
        print(f"[DEBUG] Found {len(ftdi_ports)} FTDI device(s)")
        for p in ftdi_ports:
            print(f"[DEBUG]   {p['device']} - {p['device_type']} (SN: {p['serial_number']})")

    if not ftdi_ports:
        return None

    # If preferred serial number specified, try to find it
    if prefer_serial_number:
        for p in ftdi_ports:
            if p['serial_number'] == prefer_serial_number:
                if debug:
                    print(f"[DEBUG] Using preferred device: {p['device']}")
                return p['device']

    # Return first available FTDI device
    selected = ftdi_ports[0]['device']
    if debug:
        print(f"[DEBUG] Using first available FTDI: {selected}")
    return selected


def detect_rp2040_port(debug: bool = False) -> Optional[str]:
    """
    Auto-detect RP2040 microcontroller port.

    Args:
        debug: Print debug information

    Returns:
        Device path (e.g., '/dev/tty.usbmodem14201') or None if not found
    """
    ports = serial.tools.list_ports.comports()
    rp2040_ports = []

    for port in ports:
        if port.vid and port.pid:
            # Check if this is an RP2040 device
            for device in DEVICE_IDS['rp2040']:
                if port.vid == device['vid'] and port.pid == device['pid']:
                    rp2040_ports.append({
                        'device': port.device,
                        'description': port.description,
                        'serial_number': port.serial_number,
                        'device_type': device['desc']
                    })
                    break

    if debug:
        print(f"[DEBUG] Found {len(rp2040_ports)} RP2040 device(s)")
        for p in rp2040_ports:
            print(f"[DEBUG]   {p['device']} - {p['device_type']}")

    if not rp2040_ports:
        return None

    # Return first available RP2040
    selected = rp2040_ports[0]['device']
    if debug:
        print(f"[DEBUG] Using RP2040: {selected}")
    return selected


def list_all_serial_ports() -> List[Dict[str, Any]]:
    """
    List all available serial ports with detailed information.

    Returns:
        List of dictionaries with port information
    """
    ports = serial.tools.list_ports.comports()
    result = []

    for port in ports:
        port_info = {
            'device': port.device,
            'description': port.description,
            'hwid': port.hwid,
            'vid': port.vid,
            'pid': port.pid,
            'serial_number': port.serial_number,
            'manufacturer': port.manufacturer,
            'product': port.product,
        }

        # Identify device type if known
        device_type = 'unknown'
        if port.vid and port.pid:
            for category, devices in DEVICE_IDS.items():
                for device in devices:
                    if port.vid == device['vid'] and port.pid == device['pid']:
                        device_type = f"{category}:{device['desc']}"
                        break

        port_info['device_type'] = device_type
        result.append(port_info)

    return result


def resolve_port(port_spec: str, device_type: str = 'ftdi', debug: bool = False) -> Optional[str]:
    """
    Resolve port specification to actual device path.

    Args:
        port_spec: Port specification:
                   - "auto": Auto-detect based on device_type
                   - "/dev/tty.xxx": Use exact path
        device_type: Type of device to auto-detect ('ftdi' or 'rp2040')
        debug: Print debug information

    Returns:
        Resolved device path or None if not found
    """
    if port_spec.lower() == "auto":
        if debug:
            print(f"[DEBUG] Auto-detecting {device_type} port...")

        if device_type == 'ftdi':
            return detect_ftdi_port(debug=debug)
        elif device_type == 'rp2040':
            return detect_rp2040_port(debug=debug)
        else:
            if debug:
                print(f"[DEBUG] Unknown device type: {device_type}")
            return None
    else:
        # Use exact path
        if debug:
            print(f"[DEBUG] Using configured port: {port_spec}")
        return port_spec


if __name__ == "__main__":
    """Test port detection when run directly."""
    print("Hardware Port Detection Test")
    print("=" * 50)

    print("\nFTDI RS485 Adapters:")
    ftdi = detect_ftdi_port(debug=True)
    if ftdi:
        print(f"  → Selected: {ftdi}")
    else:
        print("  ⚠️  No FTDI device found")

    print("\nRP2040 Microcontrollers:")
    rp2040 = detect_rp2040_port(debug=True)
    if rp2040:
        print(f"  → Selected: {rp2040}")
    else:
        print("  ⚠️  No RP2040 device found")

    print("\nAll Serial Ports:")
    all_ports = list_all_serial_ports()
    for port in all_ports:
        print(f"  {port['device']}")
        print(f"    Type: {port['device_type']}")
        print(f"    Description: {port['description']}")
        if port['serial_number']:
            print(f"    Serial: {port['serial_number']}")
