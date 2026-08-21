---
id: 0001
title: Integrate BearingBrain OE ultrasound-mic sampling into test runs
area: ble
role: dev
status: done
assignee: pi-claude
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

## Recon (2026-08-18, architect-verified)
- **Env ready:** BlueZ active, BLE adapter `88:A2:9E:37:39:46` powered. Only `.venv` + `bleak` missing (~5 min). Physical build + verify deferred to a session **at the rig** (sensor not mounted yet).
- **⚠️ Receive path is broken — platform-independent, NOT just a Linux caveat.** `oe_protocol.take_samples()` writes the command (`write_gatt_char`) then `await`s `self.tcs` (a future). That future is resolved **only** inside `push()`; `push()` is called **only** by `oe_device.notification_handler`, which fires **only** if `start_notify` is registered — and it is commented out in `oe_device.connect()` (~line 110). So sampling sends the command, receives nothing, and times out with empty `sampleData` on **every** platform. `connect_ota()` *does* register notify (on the firmware char), confirming the pattern is intentional and the UART path was disabled at some point.
- **Fix:** enable `start_notify(UART_CHAR_UUID, self.notification_handler)` in `connect()` — essential everywhere, not "probably on Linux" as the harness guide implied. Also sanity-check that `take_samples` writes to the correct **characteristic** UUID (it currently targets `UART_SERVICE_UUID`). HW-verify with a real OE sensor tomorrow.
- **Also:** reconcile `BearingBrain/PiSensorTest/CLAUDE.md` (harness doc) with this finding so the "un-comment on Linux" wording doesn't mislead.

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


## Recon follow-ups — resolved (Pi, 2026-08-18)

Answers to the two open points in the recon above, so review is not blocked on them:

- **`take_samples` writes to the right UUID.** `oe_protocol.UART_SERVICE_UUID` and
  `oe_device.UART_CHAR_UUID` are the *same string* (`00002760-…-0254`); only the name is
  misleading. Same for the firmware pair. Nothing to fix — worth renaming one day, but it
  is not a bug and not in this PR.
- **The harness doc needs no correction.** `BearingBrain/PiSensorTest/CLAUDE.md` never
  mentions `start_notify`; the misleading "un-comment on Linux" wording was in the **root**
  `CLAUDE.md`, and PR #2 already replaces it with the platform-independent explanation.

## Split of work (agreed 2026-08-18)

The implementation is **already done** — PR #2, authored from the Pi. There is no second
implementation to reconcile: the architect's commits on `AutoDetectScope_moj` are ticket
documents only (`git log --author` confirms no code). So the split from here is:

- **Architect / PM** — review and merge PR #2. No re-implementation needed.
- **Pi (tester)** — the hardware verification, which is the only part still outstanding:
  mount the sensor → `ble_debug_scan.py` for the MAC → set `device_address` +
  `enabled: true` → confirm a real connect and a populated `/oe_samples` → compare the
  sweep skip count against the no-OE reference run `20260818_083247`.

**The rig is not free until ~03:08** (13 h run `20260818_135505`, ticket 0005), and the
sensor is not mounted, so hw-test happens at the rig after that. Ticket moves to
`hw-test` on merge, and to `done` only when the sensor has actually been sampled.

## Data validation — OE delivers usable data (2026-08-21, architect)

Verified against the 15-min OE test `scope_20260820_112759.hdf5` (5 records) and confirmed at scale
by the 13 h run `20260820_125647` (249 records, tick-synced, 0 sweep skips). **Acceptance met; status → done.**

**The data is usable, not merely present:**
- Structured signal, not noise: the machine mic carries ~2x the energy of the ambient mic (rms 52
  vs 25), and mic energy tracks RPM on the ascending steps (490 -> 890 -> 1192 rpm gives mic_mch rms
  52 -> 81 -> 189). Correct sensor hierarchy plus a real speed response.
- Well-formed: each record carries `tick_start`, `near_sweep`, `sample_rate_hz` and the `telem_*`
  snapshot; the visualiser's cross-reference to the scope sweep works.

**80 kHz is definitive (Kim, 2026-08-21) — the "~5 % window coverage" is NOT a low rate.**
The visualiser flags that samples fill only ~5 % of the `t_start..t_stop` window and computes an
"implied ~4 kHz" (n / window). That is a red herring: the device records a short **~0.93 s burst**
(74 k samples / 80 kHz) then spends ~18 s transferring it over BLE, so the window is dominated by
transfer, not recording. The frequency axis is **80 kHz**. Do not re-open the 4 kHz question.

**Learning for the analysts (feedback):** in the 15-min test the mic energy showed a component
**beyond instantaneous RPM** — at 490 rpm the rms doubled from the start (52) to the end (114) of the
run, and the descending 691 rpm record (273) exceeded the ascending 1192 rpm record (189). A
time / hysteresis / thermal component — exactly the "grows over the run" signature an endurance test
is meant to surface. Preliminary only (5 records, fresh bearing, 15 min). **Action: run the same
analysis on the 13 h dataset** (249 records, full 40 -> 100 C profile), where a real run-in /
degradation trend would be visible.
