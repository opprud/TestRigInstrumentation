"""
Periodic BearingBrain OE ultrasound-mic sampling during a rig run (ticket 0001).

Runs as an asyncio task alongside test_runner and hands each capture to the
scope thread through a plain queue.Queue; the scope thread is the only writer
to the HDF5, so there is exactly one writer and no locking is needed.

Cadence is minutes, not sweeps: one mic capture is ~2-3 MB and takes 16-120 s
over BLE, so it cannot ride along with a ~12 s scope sweep.

Failure policy — deliberately loud. Every failed cycle is logged with its
reason and counted, and the counts are reported when the task stops. A BLE
sensor that quietly stops answering must not leave a thinner /oe_samples with
nothing to explain it; that is exactly the failure mode that let a stationary
motor go unnoticed for ten minutes on 2026-08-18.
"""

from __future__ import annotations

import asyncio
import queue
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import ble as _ble

# Bounds copied from the harness's own reference flow (run_sampler.sample_device).
SCAN_TIMEOUT_S = 20.0
CONNECT_TIMEOUT_S = 45.0
SAMPLE_TIMEOUT_S = 120.0
DISCONNECT_TIMEOUT_S = 15.0


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OeSampler:
    """One OE sensor, sampled every `interval_min` minutes into `out_queue`."""

    def __init__(self, oe_cfg: dict, out_queue: "queue.Queue", log: Optional[Callable[[str], None]] = None):
        cfg = oe_cfg or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.address = cfg.get("device_address") or ""
        self.interval_s = float(cfg.get("interval_min", 5)) * 60.0
        sensors = cfg.get("sensors") or list(_ble.MIC_SENSOR_IDS)
        self.sensors = [int(s) for s in sensors]
        self.mask = _ble.build_mask(self.sensors)
        self.queue = out_queue
        self._log = log or (lambda m: print(m, flush=True))

        self.captures = 0
        self.failures = 0
        self.last_error: Optional[str] = None

    # -- one connect/sample/disconnect cycle -------------------------------

    async def _sample_once(self) -> Optional[dict]:
        if _ble.OeDevice is None:
            raise _ble.OeUnavailable("OE harness unavailable (is bleak installed?)")

        device = await _ble.find_device_by_address(self.address, timeout=SCAN_TIMEOUT_S)
        if device is None:
            raise ConnectionError(f"{self.address} not advertising within {SCAN_TIMEOUT_S:.0f}s")

        name = getattr(device, "name", None) or self.address
        oe = _ble.OeDevice(device, name)

        await asyncio.wait_for(oe.connect(), timeout=CONNECT_TIMEOUT_S)
        if not getattr(oe, "connected", False):
            # connect() swallows its own exception and just leaves connected False.
            raise ConnectionError(f"connect to {name} did not establish a session")

        try:
            t0 = _utc_iso()
            await asyncio.wait_for(oe.sample(mask=self.mask), timeout=SAMPLE_TIMEOUT_S)
            t1 = _utc_iso()
            samples = oe.get_sample_data() or []
            if not samples:
                raise RuntimeError("device returned no sample data")
            return {
                "t_start": t0,
                "t_stop": t1,
                "device_name": name,
                "device_address": self.address,
                "mask": self.mask,
                "sensors": list(self.sensors),
                "samples": samples,
            }
        finally:
            try:
                await asyncio.wait_for(oe.disconnect(), timeout=DISCONNECT_TIMEOUT_S)
            except Exception as e:
                self._log(f"[oe] disconnect failed (continuing): {e!r}")

    # -- the periodic task -------------------------------------------------

    async def run(self, stop_event: asyncio.Event) -> None:
        """Sample until stop_event is set. Never raises into the caller."""
        if not self.enabled:
            return
        if not self.address:
            self._log("[oe] enabled but no device_address configured — OE sampling disabled")
            return

        self._log(
            f"[oe] sampling {self.address} every {self.interval_s/60:.1f} min, "
            f"sensors={self.sensors} mask=0x{self.mask:05X}"
        )

        next_due = time.monotonic()  # first capture immediately
        while not stop_event.is_set():
            now = time.monotonic()
            if now < next_due:
                # Wake early when the run ends instead of sleeping the full interval.
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=min(5.0, next_due - now))
                except asyncio.TimeoutError:
                    pass
                continue

            next_due = time.monotonic() + self.interval_s
            try:
                rec = await self._sample_once()
                if rec is not None:
                    self.queue.put(rec)
                    self.captures += 1
                    n = sum(len(s.get("data", []) or []) for s in rec["samples"])
                    self._log(f"[oe] capture {self.captures}: {len(rec['samples'])} channel(s), {n} points")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.failures += 1
                self.last_error = repr(e)
                # Skipped, not fatal: the rig run continues regardless.
                self._log(f"[oe] capture FAILED ({self.failures} so far), skipping: {e!r}")

        self._log(f"[oe] stopped — {self.captures} capture(s), {self.failures} failure(s)")
