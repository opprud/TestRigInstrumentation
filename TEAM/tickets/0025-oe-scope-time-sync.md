---
id: 0025
title: OE<->scope time sync via a run-relative tick (required for the 13 h run)
area: control
role: dev
status: done
assignee: pi-claude
depends_on: 0001, 0022
branch: ticket/0025-oe-scope-time-sync
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

---

## Implemented — commit `9fd3f58b` (pi)

Built as specified. `main()` takes `t0 = time.monotonic()` once and hands the same value to both
consumers, so neither side can compute its own: every sweep carries `tick`, every capture carries
`tick_start` taken at the `sample()` call. A missing `t0` logs a warning instead of falling back
silently — two independently derived origins would look fine and quietly fail to align, which is
the failure this ticket exists to prevent. A missing tick is left off rather than written as `0.0`,
which would read as a capture at run start.

The documented limitation is stamped **into the file**, as `/oe_samples` attributes
`tick_definition` and `tick_accuracy`, not only here — whoever opens the HDF5 in a year may not
have this repo. 14 tests in `test_oe_hdf5.py`.

0024 went in first and 0025 on top, as you suggested; no conflict in `oe_sampler.py`.

## Hardware verification (tester, Pi, 2026-08-20)

**First attempt lost to a mains power cut.** Run `20260820_100348` died 837 s into 900 s — 93 % of
the way. The HDF5 was not merely truncated but unrecoverable: nothing ever flushes, so the
superblock still read EOF = 2048 with the "file open for write" flag set, and patching both fields
on a copy did not open it. Recorded as a known issue in `CLAUDE.md`; Kim has deliberately deferred
the flush fix.

**Retest passed — run `20260820_103317`.**

| Acceptance criterion | Result |
|---|---|
| Every `oe_NNN` has float `tick_start` + `sample_rate_hz` | **4 / 4** |
| Every sweep carries a matching `tick` from the same origin | **70 / 70**, 28.34 → 898.24 s |
| `tick` deltas between bursts ~= `interval_min` | 181.6 / 178.8 / 182.0 s against a 180 s cadence |
| Documented limitation stamped in the HDF5 | `tick_definition` + `tick_accuracy` present |
| Sweeps skipped | **0**, contiguous `sweep_000`…`sweep_069` |

The scope wedged once at sweep 49 and the retry path recovered it, so zero-skip was earned under
this rig's real failure mode rather than on a quiet run.

## What the shared axis immediately revealed — read this before using `near_sweep`

```
capture  tick_start  near_sweep  sweep_tick   difference
oe_000        5.80           0       28.34      -22.5 s
oe_001      187.44          15      208.34      -20.9 s
oe_002      366.27          30      388.34      -22.1 s
oe_003      548.29          45      568.35      -20.1 s
```

**Every capture begins ~21 s before the sweep it is labelled with.** By design — a capture takes
~16 s and is drained by the sweep loop afterwards, so it lands on the next sweep to complete — but
it makes `near_sweep` a coarse label rather than a time. It matters for the 13 h dataset:
`KaretTest_Oil1` holds each rpm plateau for only **59 s**, so a 21 s lead can put the start of a
recording in the previous step. `oe_001` here is stamped 1101 rpm and begins before that step did.
**Analysis must use `tick`/`tick_start`, not `near_sweep`.** Written into `CLAUDE.md`.

## Caveat on this run's operating points

Captures are stamped 700, 1101, 1404 and 902 rpm rather than the intended 500/900/1200/900: the
drive carried a ~+3.4 Hz bias from the analog pot at the time (see the bus message and the
`CLAUDE.md` known issue). It does not affect this ticket — the timeline was what was under test —
but do not read this file as a speed protocol.
