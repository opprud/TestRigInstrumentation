---
id: 0001
title: Integrate BearingBrain OE ultrasound-mic sampling into test runs
area: ble
role: dev
status: review
assignee: dev-ble (Pi session)
branch: ticket/0001-ble-oe-integration
pr: 2
---

## Goal
Sample the BearingBrain "OE" sensor's ultrasound mic periodically **during rig test runs** and store it in the run's HDF5.

## Context
- The standalone OE BLE harness is already in-repo at `BearingBrain/PiSensorTest/` (commit `40dfaa51`): `run_sampler.py`, `gateway-service-ble/{oe_device,oe_protocol,utils}.py`, `test_configs/`.
- The OE UART-over-BLE protocol (bleak) works. Mic mask `0x18` = IDs 3+4 (`mic_amb` + `mic_mch`) — the primary signal of interest.

## Scope
- [x] `py/ble/` package that reuses `oe_device`/`oe_protocol`/`utils` (relative imports; keep the harness copy as the source, don't fork the protocol).
- [x] `py/oe_sampler.py`: async task, sample every N minutes (default 5), mic mask `0x18`; push each capture to a thread-safe queue.
- [x] Hook into `acquire_scope_data.py`: start the OE task in `main()`; the acquire loop drains the queue into HDF5 `/oe_samples`.
- [x] Config block: `{ "oe": { "enabled": false, "device_address": "<MAC>", "interval_min": 5, "sensors": [3,4] } }`.
- [x] Add `bleak` to `py/requirements.txt`.

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

## Progress (Pi dev session, 2026-08-18)

Implemented on `ticket/0001-ble-oe-integration`. All scope items done; **acceptance is only
partly verified** because no OE sensor was present on the bench.

**Verified**
- BlueZ + bleak 3.0.2 work on the Pi: `ble_debug_scan.py` saw 25 devices. No OE among them.
- `/oe_samples` write path unit-tested against a real HDF5 file: captures stored as
  `oe_000…`, one dataset per channel, with `near_sweep`, `mask`, `sensors` and `telem_*`
  attributes; a malformed record is logged and skipped rather than raising.
- `enabled: false` leaves the file layout untouched — a motor-free manual-mode run produced
  only `metadata` + `sweeps`, 3/3 sweeps, 0 skipped.
- `py/ble` degrades to `OeUnavailable` when `bleak` is missing instead of breaking the run.

**Not verified — needs the sensor (hw-test)**
- A real connect, `start_notify` actually delivering data, and a populated `/oe_samples`.
- Sweep skip count against a no-OE reference run (reference: `20260818_083247`, 71 sweeps,
  2 retries, 0 skips, 12.00 s cadence).

**Note for the reviewer:** `oe_device.connect()` needed more than un-commenting. The protocol
only ever writes — there is no `read_gatt_char` anywhere — so with `start_notify` disabled no
device reply could reach `OeProtocol.push()` on *any* platform, not just Linux. It is now
enabled after service discovery (the code's own comment requires that order), and the
duplicate `connect()` and 3 s "Windows BLE stack" sleep are removed.
