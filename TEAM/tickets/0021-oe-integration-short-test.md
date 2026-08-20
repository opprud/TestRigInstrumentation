---
id: 0021
title: Short OE-integration test — validate /oe_samples before committing to a 13 h run
area: ble
role: tester
status: done
assignee: pi-claude
branch: ticket/0021-oe-integration-short-test
depends_on: 0001, 0019
pr:
---

## Why a short test first
Kim's call, and it is the right order: prove the OE path on 15 minutes before spending 13 hours
on it. The BLE integration (ticket 0001) has never run against a live sensor — the HDF5 path is
unit-tested and BlueZ works, but no OE device has ever completed a capture into a run file.

## What is prepared
**Profile `react/public/config/OeIntegration_15min.json`** — derived from `Rehearsal_15min`:
11 rpm steps, 500→1200 rpm, open loop at 59.5 rpm/Hz, 1 M points, 12 s sweep interval.
**No temperature setpoints**, so the heater stays out of it entirely — one less thing to go wrong
and no wait for the oil to come up.

**`py/config.json`** — `oe.enabled: true`, `device_address: 03:24:71:01:04:54` (the MAC as BlueZ
reports it), `interval_min: 3` so a 15-minute run yields roughly 4–5 capture cycles rather than
the 3 that the production 5-minute cadence would give.

## Why it must be a profiled run, and what that costs
The OE sampler is created in the auto path (`acquire_scope_data.py:1449`), next to the runner.
**Manual mode does not start it**, so there is no way to exercise OE without turning the motor —
which means **the bearing must be lubricated first**. Not optional, even for 15 minutes.

## Preconditions
1. **Lubricate the bearing.**
2. **Press the reset button on the OE sensor** — it has been wedged since ~11:40 on 2026-08-19
   and cannot be revived over BLE (ticket 0019). Confirm it answers before starting:
   `python3 ble_debug_scan.py`, or watch the recovery watcher's log.
3. Accept that **UL records nothing meaningful** — the probe is detached (ticket 0015). This is a
   validation run, not a data run.

## Pass criteria
- `/oe_samples/oe_000…` exists with one dataset per channel (`Ambient Microphone`,
  `Machine Microphone`) and the `near_sweep`, `mask`, `sensors` and `telem_*` attributes.
- **The sweep skip count is unchanged** against a no-OE reference run. This is the point of the
  whole design: a mic capture takes 16–120 s against a ~12 s sweep period, and it must never
  delay a sweep. If skips appear, the queue hand-off is not working as intended.
- Failed OE cycles are logged with a reason and counted, and the run does not die.

## Then, and only then
Re-run with `interval_min: 5` for the 13 h run — and use the 100→200 rpm profile so the bottom of
the staircase actually turns the bearing.

## Result: passed on the second run (2026-08-20)
Two runs, both with the motor turning 500→1200 rpm and no temperature setpoints.

| | `20260820_091646` | `20260820_093823` |
|---|---|---|
| Sweeps | 71, contiguous, **0 skipped** | 70, contiguous, **0 skipped** |
| OE cycles with data | 2 of 6 | **5 of 5, zero failures** |

The first run passed the criterion that mattered and failed on capture reliability, which is
exactly what a 15-minute rehearsal is for. Cause and fix are in ticket 0024 — the sensor sleeps
of its own accord and stops advertising, and our 20 s scan window gave up too soon.

**The design's central promise held in both runs:** mic captures of ~149,000 points ran
concurrently with scope digitising and the motor under control, and **never delayed a sweep**.
Each capture is stamped with the operating point it was taken at — 489, 890, 1192, 691 and
490 rpm across the staircase.

**Cadence stays at 3 minutes** (Kim's call, 2026-08-20): ~260 captures over a 13 h run instead of
~156 at the old 5-minute default. The rehearsal showed the tighter cadence costs nothing in sweeps,
and denser mic coverage through the temperature staircase is precisely what the OE sensor is
there to contribute. The 5-minute figure was a cautious guess from before we knew that.

**A 13 h run is cleared to start**, with one caveat that is not ours to resolve: the UL probe is
still detached (ticket 0015), so such a run yields OE + accelerometer + slip ring, and CHAN1 will
record a normal-looking trace that means nothing.

