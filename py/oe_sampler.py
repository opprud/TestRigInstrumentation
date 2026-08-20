"""
Periodic BearingBrain OE ultrasound-mic sampling during a rig run (ticket 0001).

Runs as an asyncio task alongside test_runner and hands each capture to the
scope thread through a plain queue.Queue; the scope thread is the only writer
to the HDF5, so there is exactly one writer and no locking is needed.

Cadence is minutes, not sweeps: one mic capture is ~2-3 MB and takes 16-120 s
over BLE, so it cannot ride along with a ~12 s scope sweep.

The BLE link is held open between captures (ticket 0026). The sensor sleeps of
its own accord when idle and a sleeping device does not advertise, which cost
4 of 6 cycles on 2026-08-20 until 0024 widened the scan window to wait it out.
Staying connected removes the sleep window instead of waiting for it. It is
affordable because the unit runs on a fixed supply, not a battery, so the
connection count no longer buys anything.

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

# Bounds copied from the harness's own reference flow (run_sampler.sample_device), except the
# scan window. 20 s was the harness's figure and it cost us 4 of 6 cycles on 2026-08-20: the
# sensor sleeps of its own accord (its config carries sleep_time 30, and the vendor's sampler
# logs "Sending to sleep for 30 seconds"), and a sleeping device does not advertise. Scanning
# for 20 s and giving up means a cycle that lands in a sleep window is thrown away, so we wait
# the device out instead. See ticket 0024.
SCAN_TIMEOUT_S = 45.0
SCAN_ATTEMPTS = 3          # per cycle, so one unlucky window does not cost the whole interval
SCAN_RETRY_PAUSE_S = 10.0
CONNECT_TIMEOUT_S = 45.0
SAMPLE_TIMEOUT_S = 120.0
DISCONNECT_TIMEOUT_S = 15.0


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OeSampler:
    """One OE sensor, sampled every `interval_min` minutes into `out_queue`."""

    def __init__(self, oe_cfg: dict, out_queue: "queue.Queue", log: Optional[Callable[[str], None]] = None,
                 tick_t0: Optional[float] = None):
        cfg = oe_cfg or {}
        # Shared run origin, handed in by the caller so the OE captures and the scope sweeps
        # sit on ONE timeline. Falling back to our own monotonic() would give a second origin
        # and silently make the two streams un-alignable -- the exact failure 0025 exists to
        # prevent -- so a missing t0 is a caller bug worth being loud about in the log.
        if tick_t0 is None:
            tick_t0 = time.monotonic()
            (log or print)("[oe] WARNING: no shared run tick origin passed; OE ticks will not "
                           "align with scope sweeps")
        self.tick_t0 = float(tick_t0)
        self.enabled = bool(cfg.get("enabled", False))
        self.address = cfg.get("device_address") or ""
        self.interval_s = float(cfg.get("interval_min", 5)) * 60.0
        sensors = cfg.get("sensors") or list(_ble.MIC_SENSOR_IDS)
        self.sensors = [int(s) for s in sensors]
        self.mask = _ble.build_mask(self.sensors)
        self.queue = out_queue
        self._log = log or (lambda m: print(m, flush=True))

        # Ticket 0026. Set false to restore the old connect/sample/disconnect per cycle --
        # worth having as a config escape hatch rather than a code change, because whether a
        # held link stays healthy for 13 h is a property of the sensor, not of this file.
        self.keep_connected = bool(cfg.get("keep_connected", True))

        self.captures = 0
        self.failures = 0
        self.reconnects = 0
        self.last_error: Optional[str] = None
        self._oe = None            # the held session, when keep_connected
        self._name = ""

    # -- connection --------------------------------------------------------

    async def _connect(self):
        """Scan for the device and open a session. Returns (oe, name)."""
        if _ble.OeDevice is None:
            raise _ble.OeUnavailable("OE harness unavailable (is bleak installed?)")

        device = None
        waited = 0.0
        for attempt in range(1, SCAN_ATTEMPTS + 1):
            t_scan = time.monotonic()
            device = await _ble.find_device_by_address(self.address, timeout=SCAN_TIMEOUT_S)
            waited += time.monotonic() - t_scan
            if device is not None:
                if attempt > 1:
                    # Worth saying out loud: an unattended run should leave evidence of how long
                    # the sensor was unreachable, not just a count of failures.
                    self._log(f"[oe] device appeared on scan {attempt} after {waited:.0f}s")
                break
            if attempt < SCAN_ATTEMPTS:
                await asyncio.sleep(SCAN_RETRY_PAUSE_S)
                waited += SCAN_RETRY_PAUSE_S
        if device is None:
            raise ConnectionError(
                f"{self.address} not advertising after {SCAN_ATTEMPTS} scans over {waited:.0f}s")

        name = getattr(device, "name", None) or self.address
        oe = _ble.OeDevice(device, name)

        await asyncio.wait_for(oe.connect(), timeout=CONNECT_TIMEOUT_S)
        if not getattr(oe, "connected", False):
            # connect() swallows its own exception and just leaves connected False.
            raise ConnectionError(f"connect to {name} did not establish a session")
        return oe, name

    async def _ensure_connected(self):
        """Reuse the held session if it is still up, else open a new one.

        Returns (oe, name, fresh) -- `fresh` says whether this call established it, which
        decides whether a failure is worth retrying: a session that has just been proved dead
        is worth replacing, a brand-new one that failed immediately is not.
        """
        if self.keep_connected and self._oe is not None and getattr(self._oe, "connected", False):
            return self._oe, self._name, False
        # `connected` is not merely a stale flag: oe_device registers a disconnected_callback
        # that clears it, so an unexpected drop is visible here rather than at the next timeout.
        await self._teardown()
        oe, name = await self._connect()
        self._oe, self._name = oe, name
        return oe, name, True

    async def _teardown(self) -> None:
        oe, self._oe, self._name = self._oe, None, ""
        if oe is None:
            return
        try:
            await asyncio.wait_for(oe.disconnect(), timeout=DISCONNECT_TIMEOUT_S)
        except Exception as e:
            self._log(f"[oe] disconnect failed (continuing): {e!r}")

    # -- one capture -------------------------------------------------------

    async def _capture(self, oe, name: str) -> dict:
        t0 = _utc_iso()
        # Run-relative origin for this capture, taken as close to the device's record-start
        # as we can get: the sensor returns no timestamp of its own (see 0025), so this is
        # the anchor the whole time axis hangs from.
        tick_start = time.monotonic() - self.tick_t0
        await asyncio.wait_for(oe.sample(mask=self.mask), timeout=SAMPLE_TIMEOUT_S)
        t1 = _utc_iso()
        samples = oe.get_sample_data() or []
        if not samples:
            raise RuntimeError("device returned no sample data")
        return {
            "t_start": t0,
            "t_stop": t1,
            "tick_start": tick_start,
            "device_name": name,
            "device_address": self.address,
            "mask": self.mask,
            "sensors": list(self.sensors),
            "samples": samples,
        }

    async def _sample_once(self) -> Optional[dict]:
        """One capture, over a held link where possible."""
        for attempt in (1, 2):
            oe, name, fresh = await self._ensure_connected()
            try:
                rec = await self._capture(oe, name)
                if not self.keep_connected:
                    await self._teardown()
                return rec
            except asyncio.CancelledError:
                await self._teardown()
                raise
            except Exception as e:
                await self._teardown()
                if attempt == 1 and not fresh:
                    # The held link had died without saying so. Re-establishing here costs
                    # seconds; waiting for the next interval costs a whole capture.
                    self.reconnects += 1
                    self._log(f"[oe] held session failed ({e!r}) — reconnecting and retrying once")
                    continue
                raise
        return None

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
            f"sensors={self.sensors} mask=0x{self.mask:05X}, "
            f"link={'held open' if self.keep_connected else 'per capture'}"
        )

        try:
            await self._loop(stop_event)
        finally:
            # Release the sensor whichever way the run ends, including cancellation, so it is
            # not left in a session nobody is on the other end of.
            await self._teardown()

        tail = f", {self.reconnects} reconnect(s)" if self.reconnects else ""
        self._log(f"[oe] stopped — {self.captures} capture(s), {self.failures} failure(s){tail}")

    async def _loop(self, stop_event: asyncio.Event) -> None:
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
