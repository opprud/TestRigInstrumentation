---
id: 0025
title: OE<->scope time sync via a run-relative tick (required for the 13 h run)
area: control
role: dev
status: backlog
assignee: pi-claude
depends_on: 0001, 0022
branch:
pr:
---

## Goal
Make every OE mic capture alignable to the scope sweeps on a shared run timeline, so mic data can
be correlated against the recorded scope data. **Required in place and validated before the next
13 h run** — that dataset is the reason this exists (Kim, 2026-08-20).

## Why this design (verified from the code, not assumed)
The sensor provides **no device-side time reference**. Each channel block the device returns carries
only `sensor_id`, `data_type`, `nr_of_samples` and raw values (`oe_protocol.parse_sensor_data_block`)
— no timestamp, no counter, no clock. The vendor's own `plot_samples.py` reconstructs the time axis
as `sample_index / sample_rate` anchored on a **host** timestamp. So a shared host-side tick is the
only reference available — and it is exactly what the vendor already does; we just make it monotonic
and stamp it on both streams.

`sample_rate_hz` is already stamped per OE dataset (ticket 0022 / PR #16). The missing piece is the
run-relative time origin on both OE captures and scope sweeps.

## Change
1. **One run origin:** capture `t0 = time.monotonic()` once at run start, shared by the scope loop
   and the OE sampler (pass it in; do not let each compute its own).
2. **OE side (`oe_sampler.py`):** record `tick_start = time.monotonic() - t0` **at the moment
   `oe.sample()` is called** (closest proxy to device record-start) and carry it on the capture
   record. NOTE: coordinate with ticket 0024, which also edits `oe_sampler.py`.
3. **HDF5 (`acquire_scope_data._drain_oe_queue`):** stamp `tick_start` (float seconds) as an
   attribute on each `oe_NNN` group, alongside the existing `t_start`/`t_stop`/`near_sweep`. With
   `sample_rate_hz`, each sample's time is then `tick_start + i / sample_rate_hz`.
4. **Scope side:** stamp the same run-relative tick on each sweep (per-sweep `tick` attribute or a
   sweeps-aligned `tick` dataset), from the **same** `t0`. If sweeps already carry a monotonic time,
   re-base it to `t0` so the two share one origin.

## Acceptance
- Each `/oe_samples/oe_NNN` has a float `tick_start` (run-relative seconds) + `sample_rate_hz` -> a
  reconstructable per-sample time axis.
- Each scope sweep carries a matching run-relative `tick` from the same origin.
- On a short run: a mic burst's `tick_start` lands within the run and lines up with the nearest
  sweep's tick to within the capture cadence; `tick` deltas between bursts ~= `interval_min`.
- **Documented limitation** (in the ticket AND stamped in the HDF5, not silently): `tick_start`
  marks the `sample()` call, not the device's internal record-start; a residual sub-second offset
  (BLE round-trip + firmware) cannot be closed without a device timestamp the firmware does not
  provide. Good to sub-second; NOT sample-level (10 us) waveform overlay.

## Owner / test
- **Dev (Pi):** implement in `oe_sampler.py` + `acquire_scope_data.py` + the scope sweep stamping;
  validate on a short OE-integration run (0021-style) before the 13 h run.
- **Blocks:** the 13 h run does not start until this is merged and validated.
