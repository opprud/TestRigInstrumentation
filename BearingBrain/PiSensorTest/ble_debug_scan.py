#!/usr/bin/env python3
"""
BLE debug scanner — dumps full advertisement data for all nearby devices.
Helps diagnose why device names change (e.g. "OE..." -> "Packet").

On macOS, CoreBluetooth caches device names aggressively. This script shows
the raw advertisement data to see what the device is actually broadcasting.

Usage:
    python ble_debug_scan.py                    # scan all devices for 15s
    python ble_debug_scan.py -a 7BD14146-...    # watch a specific address
    python ble_debug_scan.py --live             # continuous scan (ctrl-c to stop)
"""

import argparse
import asyncio
import sys
from datetime import datetime

from bleak import BleakScanner
from bleak.backends.scanner import AdvertisementData


def format_adv_data(device, adv: AdvertisementData, verbose: bool = False) -> str:
    """Format full advertisement data for display."""
    lines = []
    name_from_device = device.name or "(none)"
    name_from_adv = adv.local_name or "(none)"

    lines.append(f"  Address:          {device.address}")
    lines.append(f"  Name (cached):    {name_from_device}")
    lines.append(f"  Name (adv):       {name_from_adv}")
    lines.append(f"  RSSI:             {adv.rssi} dBm")

    if name_from_device != name_from_adv:
        lines.append(f"  *** NAME MISMATCH: cached='{name_from_device}' vs adv='{name_from_adv}' ***")

    if adv.service_uuids:
        lines.append(f"  Service UUIDs:    {', '.join(adv.service_uuids)}")

    if adv.manufacturer_data:
        for company_id, data in adv.manufacturer_data.items():
            hex_data = data.hex()
            ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
            lines.append(f"  Manufacturer:     0x{company_id:04X} -> {hex_data}")
            lines.append(f"                    ASCII: {ascii_repr}")

    if adv.service_data:
        for uuid, data in adv.service_data.items():
            lines.append(f"  Service data:     {uuid} -> {data.hex()}")

    if verbose:
        if adv.tx_power is not None:
            lines.append(f"  TX Power:         {adv.tx_power} dBm")
        # Platform-specific data (CoreBluetooth)
        if hasattr(adv, 'platform_data') and adv.platform_data:
            lines.append(f"  Platform data:    {adv.platform_data}")

    return '\n'.join(lines)


async def scan_once(timeout: float, target_address: str | None, verbose: bool):
    """Single scan pass."""
    print(f"\n{'='*70}")
    print(f"Scanning for {timeout}s... ({datetime.now().strftime('%H:%M:%S')})")
    print(f"{'='*70}")

    results = await BleakScanner.discover(timeout=timeout, return_adv=True)

    # Sort by RSSI
    sorted_results = sorted(results.items(), key=lambda x: x[1][1].rssi or -999, reverse=True)

    count = 0
    for addr, (device, adv) in sorted_results:
        # Filter to target if specified
        if target_address:
            if device.address.upper() != target_address.upper():
                continue

        name = device.name or adv.local_name or ""

        # If no target specified, highlight OE/Packet devices
        is_interesting = name.startswith("OE") or name == "Packet" or target_address
        marker = " <<<" if is_interesting and not target_address else ""

        print(f"\n[{device.name or '(no name)'}]{marker}")
        print(format_adv_data(device, adv, verbose))
        count += 1

    if target_address and count == 0:
        print(f"\nDevice {target_address} not seen in this scan.")

    print(f"\nTotal: {len(results)} devices scanned, {count} shown.")


async def scan_live(target_address: str | None, verbose: bool):
    """Continuous scan using callback — shows every advertisement in real time."""
    print(f"Live scanning (Ctrl-C to stop)...")
    print(f"{'='*70}")

    seen_names = {}  # address -> set of names seen

    def callback(device, adv: AdvertisementData):
        name = device.name or adv.local_name or "(none)"

        # Filter to target if specified
        if target_address and device.address.upper() != target_address.upper():
            return

        # Track name changes
        addr = device.address
        if addr not in seen_names:
            seen_names[addr] = set()

        is_new_name = name not in seen_names[addr]
        seen_names[addr].add(name)

        # Only print if interesting or target
        is_interesting = name.startswith("OE") or name == "Packet" or target_address
        if not is_interesting and not is_new_name:
            return

        ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        name_change = ""
        if len(seen_names[addr]) > 1:
            name_change = f"  ** NAMES SEEN: {seen_names[addr]} **"

        print(f"[{ts}] {name:<24} {addr}  RSSI: {adv.rssi}{name_change}")

        if is_new_name and (is_interesting or verbose):
            print(format_adv_data(device, adv, verbose))

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await scanner.stop()


async def main():
    parser = argparse.ArgumentParser(description="BLE debug scanner — dump advertisement data")
    parser.add_argument("-a", "--address", type=str, help="Watch a specific device address")
    parser.add_argument("--live", action="store_true", help="Continuous scan (real-time advertisements)")
    parser.add_argument("--timeout", "-t", type=float, default=15.0, help="Scan timeout in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show extra platform data")
    args = parser.parse_args()

    if args.live:
        await scan_live(args.address, args.verbose)
    else:
        await scan_once(args.timeout, args.address, args.verbose)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
