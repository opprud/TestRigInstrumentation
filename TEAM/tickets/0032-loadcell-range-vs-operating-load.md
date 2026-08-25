---
id: 0032
title: Load-cell calibrated range (1-6 kg) is ~10x below operating load; pan can't extend it, operating load is extrapolated
area: mechanical / instrumentation
role: dev
status: backlog
depends_on:
branch:
pr:
---

## Problem
The load cell was calibrated 2026-08-25 over **1-6 kg** (per-gain least squares; slopes verified; the two
gain slopes differ by 1.991 as they must). But **the rig operates ~10x higher** (old telemetry ~62 kg). The
**10 kg reference never reached the cell** — loaded it read *below* empty (861841 vs 884533 counts at gain
128, -104 g), twice, after repositioning; it rests on the frame beside the pan. So:
- The calibration **pan tops out ~6 kg** — bigger reference weights won't extend it; the limit is the
  calibration load-path, not the reference.
- Operating load is therefore an **extrapolation** off a short calibrated span, unvalidated at the load the
  rig actually runs.

## Accuracy bound (measured)
Same 6 kg placed four times: spread **555 g (9.3 %)**, sd 275 g — against +/-25 counts / **0.1 g** electrical.
Placement dominates electronics ~2750x. So **absolute** logged load is good to **+/-3-5 % (~+/-3 kg at
operating load)**; **within a run** (static load, not re-placed) it is +/-0.1 g (relative / trend is tight).
Quote the right bound per use. (Does not touch the OE lubrication result — that leaned on Omron temperature,
not load.)

## Open question (Kim — mechanics)
- Is the operational bearing load applied **through the same cell / load-path** as the calibration pan?
- Is there any way to apply a **known** load near operating level (~60 kg) **through the cell** — a calibrated
  actuator, a known large mass, or the operational loading mechanism at a known setting — so the calibration
  can be validated / extended past 6 kg?

## Options if operating-level calibration is not possible
- Treat the cell as a **monitor** (drift / change detection) against the **independently-known applied load**
  (the set force / weights), not as the absolute source of truth for logged load.
- Document the extrapolation + the +/-3-5 % bound wherever logged load is used.

## Note
The zero drifts with the mechanics (unloaded raw moved 379 g over the session; empty pan reads -252 g), so
tare is re-taken in-situ after mounting; only the slope travels with the unit.
