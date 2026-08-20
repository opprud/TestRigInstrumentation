---
id: 0025
title: One run tick shared by scope sweeps and OE captures
area: ble
role: dev
status: done
assignee: pi-claude
branch: ticket/0025-oe-scope-time-sync
depends_on: 0001, 0022, 0024
pr:
---

## Why
A sweep and an OE capture could not be placed on a common time axis. Both carried wall-clock
strings only, and wall-clock is neither monotonic nor comparable between two threads that each
stamp their own. The sensor is no help: a block carries `sensor_id`, `data_type`,
`nr_of_samples` and values — **no device-side timestamp** — so a host-side origin is the only
anchor available. The vendor's own `plot_samples.py` makes the same assumption when it
reconstructs time as `index / rate`.

## What was built
`main()` takes `t0 = time.monotonic()` once and hands the same value to both consumers:

- every sweep gets `tick` — run-relative seconds, on `/sweeps/sweep_###`;
- every OE capture gets `tick_start`, taken at the `sample()` call, on `/oe_samples/oe_###`;
- with `sample_rate_hz` from 0022, sample *i* sits at `tick_start + i / sample_rate_hz`.

A missing `t0` logs a warning rather than falling back silently — two independently computed
origins would look fine and quietly fail to align, which is the exact failure this ticket exists
to prevent. A missing tick is left off rather than written as `0.0`, which would read as a
capture at run start.

The accuracy caveat is stamped into the file as `/oe_samples` attributes `tick_definition` and
`tick_accuracy`, not left in this ticket: `tick_start` marks the host's `sample()` call, not the
device's record-start, so it is good to sub-second and **not valid for sample-level (10 us)
waveform overlay**. Whoever opens the file in a year may not have this repo.

Code: commit `9fd3f58b` (`acquire_scope_data.py`, `oe_sampler.py`, `test_oe_hdf5.py`, 14 tests).

## Hardware verification
**First attempt, run `20260820_100348`, lost.** A mains power cut killed the Pi 837 s into the
900 s run — 93 % of the way. The HDF5 was unrecoverable, not merely truncated: the superblock
still said EOF = 2048 bytes and carried the "file open for write" flag, because nothing ever
flushed. Patching the EOF field and clearing the flag on a copy did not open it. Telemetry
survived to the last tick but carries no `tick` fields, so nothing could be salvaged for this
ticket. See the separate flush ticket.

**Retest, run `20260820_103317`, passed.**

| Criterion | Result |
|---|---|
| Sweeps | 70, contiguous `sweep_000`…`sweep_069`, **0 skipped** |
| Sweeps carrying `tick` | **70 / 70**, spanning 28.34 → 898.24 s |
| OE captures carrying `tick_start` | **4 / 4**, no failed cycles |
| `tick_definition` + `tick_accuracy` | present on `/oe_samples` |
| `sample_rate_hz` on datasets | stamped on all 8 |

The scope wedged once at sweep 49 and the retry path recovered it, so the zero-skip result was
earned under the failure mode this rig actually has, not on a quiet run.

## What the shared axis immediately revealed
```
capture  tick_start  near_sweep  sweep_tick   difference
oe_000        5.80           0       28.34      -22.5 s
oe_001      187.44          15      208.34      -20.9 s
oe_002      366.27          30      388.34      -22.1 s
oe_003      548.29          45      568.35      -20.1 s
```

**Every capture begins ~21 s before the sweep it is labelled with.** That is not a defect: a
capture takes ~16 s and is drained by the sweep loop afterwards, so it lands on the next sweep to
complete. But it means **`near_sweep` is a coarse label, not a time** — analysis must use `tick`
and `tick_start`. The consequence is real, because the shaft accelerates between steps:
`oe_001` is stamped 1101 rpm, yet its first seconds were recorded before that step began. Before
this ticket the discrepancy was invisible.

## Caveat on this run's operating points
The captures are stamped 700, 1101, 1404 and 902 rpm rather than the intended 500/900/1200/900.
The drive was carrying a ~+3.4 Hz bias from the analog pot at the time (see the pot ticket). It
does not affect this ticket — the timeline is what was under test — but do not read this file as
a speed protocol.
