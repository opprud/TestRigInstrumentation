#!/usr/bin/env python3
"""
Standalone BLE sampler for macOS.
Scans for OE devices, connects, retrieves sensor samples, and saves to JSON.
Reuses the existing gateway BLE protocol code directly.

Usage:
    python run_sampler.py                            # Scan and pick device interactively
    python run_sampler.py --device OE99999999900032  # Connect by name
    python run_sampler.py --address AA:BB:CC:DD:EE   # Connect by MAC/UUID address
    python run_sampler.py --sensors 0 1 2            # Sample only battery, temp_amb, temp_mch
    python run_sampler.py --all-sensors              # Sample all 19 sensors
    python run_sampler.py --config sampling.json     # Use a sampling config file
    python run_sampler.py --read-configs             # Read device configs only

Note: After first connection, the device may advertise as "Packet" instead of "OE...".
      Use --address to connect by MAC address in that case.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

# Add the gateway-service-ble module to path so we can import its code directly
BLE_SERVICE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gateway-service-ble")
sys.path.insert(0, BLE_SERVICE_DIR)

from bleak import BleakScanner
from oe_device import OeDevice
from utils import get_sensor_name

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")

# All 19 sensor IDs
ALL_SENSOR_IDS = list(range(19))

# Default sensor set: battery + both temps
DEFAULT_SENSOR_IDS = [0, 1, 2]


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def build_mask(sensor_ids: list[int]) -> int:
    mask = 0
    for sid in sensor_ids:
        mask |= 1 << sid
    return mask


def read_device_serial(device_configs: dict) -> str | None:
    """Extract device serial from config group 0x00, sub_group 0x02.
    The device stores the serial without the 'OE' prefix that appears in BLE advertisements."""
    for cfg in device_configs.get("configs", []):
        if cfg["main_group"] == 0 and cfg["sub_group"] == 2:
            serial = cfg["config_value"]
            if serial and not serial.startswith("OE"):
                serial = f"OE{serial}"
            return serial
    return None


async def scan_devices(timeout: float = 10.0, show_all: bool = False) -> tuple[list, dict]:
    """Scan for BLE devices. Returns OE/Packet devices by default, all if show_all."""
    logger = logging.getLogger("sampler")
    logger.info(f"Scanning for BLE devices ({timeout}s)...")

    # Use return_adv=True to get RSSI and real advertised name from advertisement data
    results = await BleakScanner.discover(timeout=timeout, return_adv=True)
    # results is dict: {address: (BLEDevice, AdvertisementData)}
    all_devices = []
    rssi_map = {}
    adv_name_map = {}  # address -> real advertised name (not CoreBluetooth cache)
    for addr, (device, adv) in results.items():
        rssi_map[device.address] = adv.rssi
        # Prefer adv.local_name (actual broadcast) over device.name (CoreBluetooth cache)
        adv_name_map[device.address] = adv.local_name or device.name or None
        all_devices.append(device)

    def _is_oe(d):
        name = adv_name_map.get(d.address) or d.name or ""
        return name.startswith("OE") or name == "Packet"

    # Sort: OE/Packet devices first, then by RSSI (strongest first)
    all_devices.sort(key=lambda d: (not _is_oe(d), -(rssi_map.get(d.address, -999) or -999)))

    if show_all:
        candidates = all_devices
    else:
        candidates = [d for d in all_devices if _is_oe(d)]

    if not candidates:
        logger.warning("No OE devices found. Try --show-all to see all BLE devices.")
        candidates = all_devices

    if candidates:
        logger.info(f"Found {len(candidates)} device(s):")
        for i, d in enumerate(candidates):
            rssi = rssi_map.get(d.address, "?")
            real_name = adv_name_map.get(d.address) or d.name or "(no name)"
            cached = d.name or ""
            # Show cached name if it differs from the real advertised name
            cache_note = f"  (cached: {cached})" if cached and cached != real_name else ""
            marker = " <-- OE" if _is_oe(d) else ""
            logger.info(f"  [{i}] {real_name:<24} {d.address}  RSSI: {rssi}{marker}{cache_note}")
    else:
        logger.warning("No BLE devices found at all.")

    return all_devices, adv_name_map


async def pick_device(devices: list):
    """Let user pick a device from the scan results."""
    if len(devices) == 1:
        return devices[0]

    while True:
        try:
            choice = int(input(f"\nSelect device [0-{len(devices)-1}]: "))
            if 0 <= choice < len(devices):
                return devices[choice]
        except (ValueError, EOFError):
            pass
        print("Invalid choice, try again.")


async def sample_device(device, sensor_ids: list[int], sampling_masks: list[list[int]] | None = None,
                        display_name: str | None = None, sleep: bool = True):
    """Connect to device, sample sensors, return data."""
    logger = logging.getLogger("sampler")
    name = display_name or device.name or "unknown"

    oe = OeDevice(device, name)

    logger.info(f"Connecting to {name} ({device.address})...")
    await asyncio.wait_for(oe.connect(), timeout=45)

    if not oe.connected:
        raise ConnectionError(f"Failed to connect to {name}")

    try:
        # Use advertised name as serial (format: OE<serial>). Skip config read to avoid
        # the 45s overhead and to keep sampling viable when config read would time out.
        serial = name if name.startswith("OE") else None

        # Build sampling masks
        if sampling_masks:
            masks = []
            for group in sampling_masks:
                mask = 0
                for sid in group:
                    mask |= 1 << sid
                masks.append(mask)
        else:
            masks = [build_mask(sensor_ids)]

        # Sample each mask group
        all_samples = []
        for i, mask in enumerate(masks):
            enabled = [get_sensor_name(bit) for bit in range(19) if mask & (1 << bit)]
            logger.info(f"Sampling group {i+1}/{len(masks)}: {', '.join(enabled)} (mask=0x{mask:05X})")

            start_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%fZ")
            await asyncio.wait_for(oe.sample(mask=mask), timeout=120)
            stop_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%fZ")

            samples = oe.get_sample_data()
            all_samples.append({
                "start_timestamp": start_ts,
                "stop_timestamp": stop_ts,
                "samples": samples,
            })

            # Print summary
            if samples:
                for s in samples:
                    count = len(s.get("data", []))
                    logger.info(f"  {s['sensor_name']}: {count} samples")
            else:
                logger.warning("  No sample data received!")

        # Send device to sleep
        if sleep:
            logger.info("Sending device to sleep (30s)...")
            await asyncio.wait_for(oe.sleep(30, False), timeout=15)
        else:
            logger.info("Skipping device sleep (--no-sleep)")

        return {
            "device_name": name,
            "device_serial": serial,
            "device_address": device.address,
            "measurements": all_samples,
        }

    finally:
        logger.info("Disconnecting...")
        await oe.disconnect()


async def read_device_configs(device, display_name: str | None = None):
    """Connect and read configs only. Returns (configs, serial)."""
    logger = logging.getLogger("sampler")
    name = display_name or device.name or "unknown"

    oe = OeDevice(device, name)
    logger.info(f"Connecting to {name} ({device.address})...")
    await asyncio.wait_for(oe.connect(), timeout=45)

    if not oe.connected:
        raise ConnectionError(f"Failed to connect to {name}")

    try:
        logger.info("Reading device configs...")
        await asyncio.wait_for(oe.read_all_configs(), timeout=45)
        configs = oe.get_config_data()

        serial = read_device_serial(configs)
        if serial:
            logger.info(f"Device serial: {serial}")

        logger.info(f"Config hash ID: {configs.get('config_hash_id', 'N/A')}")
        for cfg in configs.get("configs", []):
            logger.info(f"  [{cfg['main_group']:3d}:{cfg['sub_group']:3d}] "
                        f"type=0x{cfg['data_type_id']:02X} value={cfg['config_value']}")

        await asyncio.wait_for(oe.sleep(30, False), timeout=15)
        return configs, serial

    finally:
        await oe.disconnect()


def save_results(data: dict, device_name: str):
    """Save sample data to JSON file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{device_name}_{timestamp}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    logging.getLogger("sampler").info(f"Saved results to {filepath}")
    return filepath


async def main():
    parser = argparse.ArgumentParser(description="BLE Sampler for OE Bearing Brain devices (macOS)")
    parser.add_argument("--device", "-d", type=str, help="Device name to connect to (e.g. OE99999999900032 or Packet)")
    parser.add_argument("--address", "-a", type=str, help="Device MAC/UUID address to connect to directly")
    parser.add_argument("--sensors", "-s", type=int, nargs="+", help="Sensor IDs to sample (0-18)")
    parser.add_argument("--all-sensors", action="store_true", help="Sample all 19 sensors")
    parser.add_argument("--config", "-c", type=str, help="Path to sampling config JSON file")
    parser.add_argument("--read-configs", action="store_true", help="Read device configs only (no sampling)")
    parser.add_argument("--scan-timeout", type=float, default=10.0, help="BLE scan timeout in seconds")
    parser.add_argument("--show-all", action="store_true", help="Show all BLE devices during scan, not just OE/Packet")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-save", action="store_true", help="Don't save results to file")
    parser.add_argument("--no-sleep", action="store_true", help="Don't send device to sleep after sampling")
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("sampler")

    # Determine sensor IDs and masks
    sensor_ids = DEFAULT_SENSOR_IDS
    sampling_masks = None
    config_address = None  # address extracted from config/sample file
    config_serial = None   # serial extracted from config/sample file

    if args.config:
        with open(args.config) as f:
            config = json.load(f)
        sampling_masks = config.get("sampling_masks")
        config_address = config.get("device_address")
        config_serial = config.get("device_serial")
        info_parts = []
        if config_serial:
            info_parts.append(f"serial: {config_serial}")
        if config_address:
            info_parts.append(f"address: {config_address}")
        info = f" ({', '.join(info_parts)})" if info_parts else ""
        logger.info(f"Loaded config from {args.config}{info}")
    elif args.all_sensors:
        sensor_ids = ALL_SENSOR_IDS
    elif args.sensors:
        sensor_ids = args.sensors

    # Find device
    adv_name_map = {}
    if args.address or config_address:
        # Connect by address — need a quick scan first so CoreBluetooth discovers the device
        address = args.address or config_address
        logger.info(f"Scanning for device {address}...")
        devices, adv_name_map = await scan_devices(timeout=args.scan_timeout, show_all=True)
        target = [d for d in devices if d.address.upper() == address.upper()]
        if target:
            device = target[0]
            real_name = adv_name_map.get(device.address, device.name)
            logger.info(f"Found {real_name} at {device.address}")
        else:
            logger.warning(f"Device {address} not seen in scan — is it awake/advertising?")
            sys.exit(1)
    elif args.device or config_serial:
        # Scan and match by advertised name, serial, or address
        match_name = args.device or config_serial
        devices, adv_name_map = await scan_devices(timeout=args.scan_timeout, show_all=args.show_all)
        target = [d for d in devices
                  if (adv_name_map.get(d.address) or "") == match_name
                  or (d.name and d.name == match_name)
                  or d.address.upper() == match_name.upper()]
        if not target:
            logger.error(f"Device '{match_name}' not found. Try --address with the MAC address, or --show-all.")
            sys.exit(1)
        device = target[0]
    else:
        devices, adv_name_map = await scan_devices(timeout=args.scan_timeout, show_all=args.show_all)
        if not devices:
            sys.exit(1)
        device = await pick_device(devices)

    # Use the real advertised name (not CoreBluetooth cached name)
    real_name = adv_name_map.get(device.address, device.name)

    # Execute
    if args.read_configs:
        configs, serial = await read_device_configs(device, display_name=real_name)
        safe_name = serial or (real_name or device.address).replace(":", "").replace(" ", "_")
        if not args.no_save:
            save_results({"device_configs": configs, "device_name": serial or real_name}, safe_name)
    else:
        data = await sample_device(device, sensor_ids, sampling_masks, display_name=real_name,
                                   sleep=not args.no_sleep)
        # Use device serial (from configs) for file naming, fall back to advertised name/address
        safe_name = data.get("device_serial") or data.get("device_name") or device.address
        safe_name = safe_name.replace(":", "").replace(" ", "_")
        if not args.no_save:
            save_results(data, safe_name)

    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
