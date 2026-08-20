#!/usr/bin/env python3
"""
Unit tests for the OE -> HDF5 path in acquire_scope_data._drain_oe_queue.

Written because CLAUDE.md described this path as unit-tested and no test existed in the repo.
It runs without a scope, without a sensor and without BLE: the queue is fed by hand and the
result is read straight back out of a temporary HDF5 file.

The point of the tests is the layout an analyst will meet six months from now — the dataset keys,
the attributes that tie a capture to its operating point, and the promise that a failing capture
never takes the run with it.
"""
import queue
import sys
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acquire_scope_data import _drain_oe_queue, _oe_dataset_name  # noqa: E402


def capture(n_samples=8, sensors=(3, 4)):
    names = {3: "Ambient Microphone", 4: "Machine Microphone", 0: "Battery Level"}
    return {
        "t_start": "2026-08-20T09:00:00+02:00",
        "t_stop": "2026-08-20T09:00:42+02:00",
        "device_name": "OE00031204100074",
        "device_address": "03:24:71:01:04:54",
        "mask": 0x18,
        "sensors": list(sensors),
        "samples": [
            {"sensor_id": sid,
             "sensor_name": names.get(sid, f"Sensor {sid}"),
             "data": [float(i) for i in range(n_samples)]}
            for sid in sensors
        ],
    }


class TestAliasMapping(unittest.TestCase):
    def test_known_sensors_use_the_vendor_alias(self):
        self.assertEqual(_oe_dataset_name(3, "Ambient Microphone"), "mic_amb")
        self.assertEqual(_oe_dataset_name(4, "Machine Microphone"), "mic_mch")
        self.assertEqual(_oe_dataset_name(0, "Battery Level"), "battery")
        self.assertEqual(_oe_dataset_name(18, "DRV425"), "drv425")

    def test_unknown_sensor_falls_back_to_a_slug(self):
        # A firmware that adds a channel must not produce a group full of "unknown".
        self.assertEqual(_oe_dataset_name(99, "Some New Sensor"), "some_new_sensor")
        self.assertEqual(_oe_dataset_name(None, "Weird  Name!!"), "weird_name")

    def test_no_alias_contains_a_space(self):
        # The whole reason for aliasing: f["oe_samples/oe_000/Ambient Microphone"] is awkward.
        from acquire_scope_data import OE_SENSOR_ALIASES
        for sid, alias in OE_SENSOR_ALIASES.items():
            self.assertNotIn(" ", alias, f"sensor {sid} alias {alias!r} contains a space")
            self.assertEqual(alias, alias.lower())


class TestDrainOeQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "t.h5"

    def tearDown(self):
        self.tmp.cleanup()

    def drain(self, records, telemetry=None, sweep_idx=7):
        q = queue.Queue()
        for r in records:
            q.put(r)
        state = {}
        logs = []
        with h5py.File(self.path, "w") as f:
            _drain_oe_queue(f, q, state, telemetry or {}, sweep_idx, {}, logs.append)
        return logs

    def test_datasets_use_aliases_and_keep_the_display_name(self):
        self.drain([capture()])
        with h5py.File(self.path, "r") as f:
            g = f["oe_samples/oe_000"]
            self.assertEqual(sorted(g.keys()), ["mic_amb", "mic_mch"])
            self.assertEqual(g["mic_amb"].attrs["sensor_name"], "Ambient Microphone")
            self.assertEqual(int(g["mic_amb"].attrs["sensor_id"]), 3)
            np.testing.assert_allclose(g["mic_mch"][:], np.arange(8, dtype=float))

    def test_sample_rate_is_stamped_with_its_source(self):
        # A mic capture with no sample rate is an array with no time axis, and the device does
        # not send the rate with the data -- so it has to come from config and be traceable.
        q = queue.Queue()
        q.put(capture())
        state = {"grp": None, "n": 0,
                 "rates": {"3": 100000, "4": 100000, "_source": "pdm_mic_config.json"}}
        with h5py.File(self.path, "w") as f:
            _drain_oe_queue(f, q, state, {}, 0, {}, lambda m: None)
        with h5py.File(self.path, "r") as f:
            g = f["oe_samples/oe_000"]
            self.assertAlmostEqual(float(g["mic_amb"].attrs["sample_rate_hz"]), 100000.0)
            self.assertAlmostEqual(float(g["mic_mch"].attrs["sample_rate_hz"]), 100000.0)
            self.assertEqual(g["mic_amb"].attrs["sample_rate_source"], "pdm_mic_config.json")

    def test_missing_rate_is_left_off_rather_than_guessed(self):
        # Better a dataset with no rate than one carrying an invented number.
        self.drain([capture()])
        with h5py.File(self.path, "r") as f:
            self.assertNotIn("sample_rate_hz", f["oe_samples/oe_000/mic_amb"].attrs)

    def test_capture_carries_its_operating_point(self):
        telem = {"rpm_meas": 1188.0, "vfd_cmd_hz": 20.0, "omron_pv_c": 61.5, "step": 4}
        self.drain([capture()], telemetry=telem, sweep_idx=42)
        with h5py.File(self.path, "r") as f:
            a = f["oe_samples/oe_000"].attrs
            self.assertEqual(int(a["near_sweep"]), 42)
            self.assertAlmostEqual(float(a["telem_rpm_meas"]), 1188.0)
            self.assertAlmostEqual(float(a["telem_vfd_cmd_hz"]), 20.0)
            self.assertEqual(a["device_address"], "03:24:71:01:04:54")
            self.assertEqual(int(a["mask"]), 0x18)
            self.assertEqual(list(a["sensors"]), [3, 4])

    def test_captures_number_sequentially(self):
        q = queue.Queue()
        state = {}
        with h5py.File(self.path, "w") as f:
            for i in range(3):
                q.put(capture())
                _drain_oe_queue(f, q, state, {}, i, {}, lambda m: None)
        with h5py.File(self.path, "r") as f:
            self.assertEqual(sorted(f["oe_samples"].keys()),
                             ["oe_000", "oe_001", "oe_002"])

    def test_group_is_not_created_when_nothing_arrives(self):
        # A run with OE disabled must keep its exact previous layout.
        self.drain([])
        with h5py.File(self.path, "r") as f:
            self.assertNotIn("oe_samples", f)

    def test_a_bad_capture_is_logged_and_the_run_survives(self):
        bad = capture()
        bad["samples"] = [{"sensor_id": 3, "sensor_name": "Ambient Microphone",
                           "data": object()}]          # not writable to HDF5
        logs = self.drain([bad, capture()])
        self.assertTrue(any("FAILED" in m for m in logs), logs)
        with h5py.File(self.path, "r") as f:
            # The good capture that followed it still landed.
            self.assertIn("oe_samples", f)
            self.assertTrue(any("mic_amb" in f[f"oe_samples/{k}"] for k in f["oe_samples"]))

    def test_none_queue_is_a_no_op(self):
        with h5py.File(self.path, "w") as f:
            _drain_oe_queue(f, None, {}, {}, 0, {}, lambda m: None)
        with h5py.File(self.path, "r") as f:
            self.assertNotIn("oe_samples", f)


if __name__ == "__main__":
    unittest.main(verbosity=2)
