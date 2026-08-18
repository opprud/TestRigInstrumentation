"""
Thin adapter onto the BearingBrain OE BLE harness.

Ticket 0001 is explicit that the harness stays the single source of the OE
protocol — this package must not fork oe_device/oe_protocol/utils. It only puts
the harness on sys.path, re-exports what the sampler needs, and adds the two
helpers the harness itself does not provide: resolving a BLEDevice from a MAC
(Linux/BlueZ addresses devices by MAC, not by the macOS UUID) and building a
sensor mask.

Import failures are raised as OeUnavailable rather than ImportError so callers
can treat "bleak missing / harness moved" as a disabled feature instead of a
crash — a rig run must never die because the optional BLE sensor is absent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

__all__ = [
    "OeUnavailable",
    "OeDevice",
    "get_sensor_name",
    "build_mask",
    "find_device_by_address",
    "MIC_SENSOR_IDS",
    "MIC_MASK",
    "harness_path",
]

# mic_amb (3) + mic_mch (4) — the ultrasound channels, mask 0x18.
MIC_SENSOR_IDS = (3, 4)
MIC_MASK = 0x18


class OeUnavailable(RuntimeError):
    """The OE harness or its dependencies could not be loaded."""


def harness_path() -> Path:
    """Absolute path to the harness's protocol modules."""
    return (
        Path(__file__).resolve().parent.parent.parent
        / "BearingBrain"
        / "PiSensorTest"
        / "gateway-service-ble"
    )


def _load():
    """Import the harness modules, putting their directory on sys.path once."""
    p = harness_path()
    if not p.is_dir():
        raise OeUnavailable(f"OE harness not found at {p}")
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)
    try:
        from oe_device import OeDevice as _OeDevice  # type: ignore
        from utils import get_sensor_name as _get_sensor_name  # type: ignore
    except Exception as e:  # bleak missing, syntax error, moved file…
        raise OeUnavailable(f"could not import the OE harness from {p}: {e!r}") from e
    return _OeDevice, _get_sensor_name


try:
    OeDevice, get_sensor_name = _load()
except OeUnavailable:
    OeDevice = None  # type: ignore[assignment]

    def get_sensor_name(sensor_id: int) -> str:  # type: ignore[misc]
        return f"sensor_{sensor_id}"


def build_mask(sensor_ids) -> int:
    """Sensor ids -> bitmask, same convention as the harness's build_mask()."""
    mask = 0
    for sid in sensor_ids:
        mask |= 1 << int(sid)
    return mask


async def find_device_by_address(address: str, timeout: float = 20.0) -> Optional[object]:
    """
    Resolve a MAC address to a BLEDevice, which is what OeDevice() expects.

    Returns None if the device is not advertising within `timeout` — an absent
    sensor is a normal condition here, not an error.
    """
    try:
        from bleak import BleakScanner
    except Exception as e:
        raise OeUnavailable(f"bleak is not available: {e!r}") from e
    return await BleakScanner.find_device_by_address(address, timeout=timeout)
