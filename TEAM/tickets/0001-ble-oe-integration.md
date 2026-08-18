---
id: 0001
title: Integrate BearingBrain OE ultrasound-mic sampling into test runs
area: ble
role: dev
status: backlog
assignee: unassigned
branch:
pr:
---

## Goal
Sample the BearingBrain "OE" sensor's ultrasound mic periodically **during rig test runs** and store it in the run's HDF5.

## Context
- The standalone OE BLE harness is already in-repo at `BearingBrain/PiSensorTest/` (commit `40dfaa51`): `run_sampler.py`, `gateway-service-ble/{oe_device,oe_protocol,utils}.py`, `test_configs/`.
- The OE UART-over-BLE protocol (bleak) works. Mic mask `0x18` = IDs 3+4 (`mic_amb` + `mic_mch`) — the primary signal of interest.

## Scope
- [ ] `py/ble/` package that reuses `oe_device`/`oe_protocol`/`utils` (relative imports; keep the harness copy as the source, don't fork the protocol).
- [ ] `py/oe_sampler.py`: async task, sample every N minutes (default 5), mic mask `0x18`; push each capture to a thread-safe queue.
- [ ] Hook into `acquire_scope_data.py`: start the OE task in `main()`; the acquire loop drains the queue into HDF5 `/oe_samples`.
- [ ] Config block: `{ "oe": { "enabled": false, "device_address": "<MAC>", "interval_min": 5, "sensors": [3,4] } }`.
- [ ] Add `bleak` to `py/requirements.txt`.

## Prerequisites / risks
- **Verify BLE on BlueZ first**: un-comment `start_notify` in `oe_device.connect()` (~line 110) and confirm a real connect on the Pi before wiring into runs.
- Needs the sensor **MAC address** (Linux/BlueZ uses the MAC, not the macOS UUID). Get it from `ble_debug_scan.py`.
- **Must not stall scope acquisition** — bounded timeouts; a slow/failed OE sample is skipped and logged, never blocks a sweep.
- A mic sample is ~2–3 MB and takes ~16–120 s over BLE → **per-run cadence (minutes), not per-sweep.**

## Acceptance
- A test run produces `/oe_samples` in the HDF5 with periodic mic captures.
- Scope sweep cadence/reliability unchanged (skip count vs a no-OE reference run).
- `enabled: false` by default → no behaviour change unless configured.

## Owner / test
- **Dev:** BLE. **Tester (Pi):** verify with a real OE sensor + rig run; confirm `/oe_samples` populated and sweep skips not increased.
