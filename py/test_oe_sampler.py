#!/usr/bin/env python3
"""
Unit tests for OeSampler's BLE session handling (ticket 0026).

No sensor, no BLE, no bleak: `oe_sampler._ble` is replaced with a fake harness, so what is
under test is this file's own decisions — when it reuses a session, when it throws one away,
and when a failure is worth one immediate retry.

The behaviour that matters on a 13 h run is the one that is hardest to see: a held link that
has quietly died. The device sleeps when idle and a sleeping device does not advertise, so a
session dropped at 03:00 must cost seconds, not a capture, and must not cost the run.
"""
import asyncio
import queue
import unittest

import oe_sampler
from oe_sampler import OeSampler


class FakeBleDevice:
    def __init__(self, address="AA:BB:CC:DD:EE:FF", name="OE-TEST"):
        self.address, self.name = address, name


class FakeOeDevice:
    """Stands in for the vendor's OeDevice. `plan` drives per-call behaviour."""

    created = []

    def __init__(self, device, name):
        self.device, self.name = device, name
        self.connected = False
        self.sample_calls = 0
        self.disconnect_calls = 0
        self.plan = []                      # popped per sample(): None = ok, else raise it
        FakeOeDevice.created.append(self)

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False
        self.disconnect_calls += 1

    async def sample(self, mask):
        self.sample_calls += 1
        if self.plan:
            outcome = self.plan.pop(0)
            if outcome is not None:
                raise outcome

    def get_sample_data(self):
        return [{"sensor_id": 3, "sensor_name": "Ambient Microphone", "data": [1, 2, 3]}]


class FakeBle:
    """Replaces the `ble` adapter module."""

    OeUnavailable = RuntimeError
    MIC_SENSOR_IDS = (3, 4)

    def __init__(self):
        self.OeDevice = FakeOeDevice
        self.scan_calls = 0
        self.scan_returns_none = False

    def build_mask(self, sensors):
        m = 0
        for s in sensors:
            m |= 1 << int(s)
        return m

    async def find_device_by_address(self, address, timeout=0.0):
        self.scan_calls += 1
        return None if self.scan_returns_none else FakeBleDevice(address)


async def _until(cond, timeout=5.0):
    """Wait for `cond`, but fail the test rather than hanging the suite."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not cond():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition never became true")
        await asyncio.sleep(0.005)


def make_sampler(keep_connected=True, **over):
    cfg = {"enabled": True, "device_address": "AA:BB:CC:DD:EE:FF", "sensors": [3, 4],
           "interval_min": 0.001, "keep_connected": keep_connected}
    cfg.update(over)
    return OeSampler(cfg, queue.Queue(), log=lambda m: None, tick_t0=0.0)


class SamplerSessionTests(unittest.TestCase):
    def setUp(self):
        self._real_ble = oe_sampler._ble
        self.ble = FakeBle()
        oe_sampler._ble = self.ble
        FakeOeDevice.created = []
        # The retry pause is real time; a test must not sit through it.
        self._pause = oe_sampler.SCAN_RETRY_PAUSE_S
        oe_sampler.SCAN_RETRY_PAUSE_S = 0.0

    def tearDown(self):
        oe_sampler._ble = self._real_ble
        oe_sampler.SCAN_RETRY_PAUSE_S = self._pause

    # -- the point of the ticket ------------------------------------------

    def test_held_link_is_reused_across_captures(self):
        s = make_sampler(keep_connected=True)
        for _ in range(3):
            self.assertIsNotNone(asyncio.run(s._sample_once()))
        self.assertEqual(len(FakeOeDevice.created), 1, "should connect once, not once per capture")
        self.assertEqual(self.ble.scan_calls, 1, "a held link must not re-scan")
        self.assertEqual(FakeOeDevice.created[0].sample_calls, 3)
        self.assertEqual(FakeOeDevice.created[0].disconnect_calls, 0)
        self.assertTrue(FakeOeDevice.created[0].connected)

    def test_disabling_the_knob_restores_a_session_per_capture(self):
        s = make_sampler(keep_connected=False)
        for _ in range(3):
            asyncio.run(s._sample_once())
        self.assertEqual(len(FakeOeDevice.created), 3)
        self.assertEqual(self.ble.scan_calls, 3)
        self.assertTrue(all(d.disconnect_calls == 1 for d in FakeOeDevice.created))

    # -- the failure that only shows up overnight --------------------------

    def test_a_dead_held_link_costs_a_reconnect_not_a_capture(self):
        s = make_sampler(keep_connected=True)
        asyncio.run(s._sample_once())                      # establishes the session
        held = FakeOeDevice.created[0]
        held.plan = [ConnectionError("link dropped")]      # next sample on it fails

        rec = asyncio.run(s._sample_once())

        self.assertIsNotNone(rec, "the retry must still produce the capture")
        self.assertEqual(s.reconnects, 1)
        self.assertEqual(len(FakeOeDevice.created), 2, "a failed session is replaced, not reused")
        self.assertEqual(held.disconnect_calls, 1, "the dead session is released")

    def test_a_brand_new_session_that_fails_is_not_retried(self):
        # Retrying a session established seconds ago just doubles the wait before the run's
        # own failure policy gets to log it.
        s = make_sampler(keep_connected=True)
        original = FakeOeDevice.__init__

        def failing_init(self_, device, name):
            original(self_, device, name)
            self_.plan = [RuntimeError("device returned no sample data")]

        FakeOeDevice.__init__ = failing_init
        try:
            with self.assertRaises(RuntimeError):
                asyncio.run(s._sample_once())
        finally:
            FakeOeDevice.__init__ = original
        self.assertEqual(len(FakeOeDevice.created), 1)
        self.assertEqual(s.reconnects, 0)

    def test_no_data_is_an_error_not_an_empty_capture(self):
        s = make_sampler(keep_connected=True)
        # Restore by assignment, not `del`: the lambda replaces the entry in the class dict,
        # so deleting it would remove the real method and quietly break every later test.
        original = FakeOeDevice.get_sample_data
        FakeOeDevice.get_sample_data = lambda self_: []
        try:
            with self.assertRaises(RuntimeError):
                asyncio.run(s._sample_once())
        finally:
            FakeOeDevice.get_sample_data = original

    def test_a_silent_sensor_is_reported_as_not_advertising(self):
        s = make_sampler(keep_connected=True)
        self.ble.scan_returns_none = True
        with self.assertRaises(ConnectionError):
            asyncio.run(s._sample_once())
        self.assertEqual(self.ble.scan_calls, oe_sampler.SCAN_ATTEMPTS,
                         "every scan attempt must be spent before giving up")

    # -- the run loop ------------------------------------------------------

    def test_the_link_is_released_when_the_run_stops(self):
        s = make_sampler(keep_connected=True)

        async def drive():
            stop = asyncio.Event()
            task = asyncio.create_task(s.run(stop))
            await _until(lambda: s.captures)
            stop.set()
            await task

        asyncio.run(drive())
        self.assertGreaterEqual(s.captures, 1)
        self.assertTrue(FakeOeDevice.created, "a capture should have opened a session")
        self.assertTrue(all(d.disconnect_calls >= 1 for d in FakeOeDevice.created),
                        "the sensor must not be left in a session nobody is on")
        self.assertIsNone(s._oe)

    def test_a_failing_capture_never_takes_the_run_with_it(self):
        s = make_sampler(keep_connected=True)
        self.ble.scan_returns_none = True

        async def drive():
            stop = asyncio.Event()
            task = asyncio.create_task(s.run(stop))
            await _until(lambda: s.failures)
            stop.set()
            await task

        asyncio.run(drive())
        self.assertGreaterEqual(s.failures, 1)
        self.assertEqual(s.captures, 0)
        self.assertIn("not advertising", s.last_error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
