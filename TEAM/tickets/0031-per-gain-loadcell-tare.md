---
id: 0031
title: Per-gain load-cell tare — cmd_tare stores one shared tare_offset; raw counts scale with gain
area: firmware
role: dev
status: backlog
depends_on:
branch:
pr:
---

## Problem
Load-cell **slope is per gain** (`g128` / `g64` / `g32`) but **tare is a single shared value.**
`cmd_tare()` stores one `tare_offset` in raw ADC counts, and raw counts scale with the HX711 gain. So a
tare taken at gain 128 is off by ~2x once auto-scale drops to 64 (and ~4x at 32). `mass = (raw -
tare_offset) * slope()` then carries a gain-dependent zero error whenever the gain at measurement differs
from the gain at tare.

## Impact / when it bites
Only when the gain **changes between tare and measurement**. During a run the applied bearing load is
roughly static, so auto-scale should sit in one band and the shared tare is correct — **workable today by
taring at the gain the run will sit at.** It bites if the operating load sits **near a band boundary**
(auto_scale raw thresholds: 128->64 >6.5 M, 64->32 >7.5 M, 32->64 <5.0 M, 64->128 <2.5 M) and
noise/vibration flips the gain mid-run — then half the samples carry a ~2x zero error. Hysteresis + the
3-read stability gate damp rapid flipping but do not remove it near a boundary.

## Fix
Per-gain tare: `t128` / `t64` / `t32` in the `CalRecord` (bump `CAL_VERSION`), `cmd_tare()` writes the
current gain's slot, `cmd_load()` subtracts the current gain's tare, `SETCAL` / `CAL?` carry it. Mirrors
how slope is already per-gain.

## Decision (2026-08-25)
**After the 13 h run, provided the operating load sits comfortably mid-band** — confirm during today's
calibration that the gain is stable at operating load (not near 2.5 M / 6.5 M / 7.5 M raw). **If it sits
near a boundary, this escalates to before the 13 h run** — or pin the gain for the run, if auto-scale can
be locked (`auto_scale()` currently runs inside `cmd_load()`, so verify a lock actually holds). Raised from
Pi's flag on 2026-08-25 while flashing v1.2.2 for the load-cell calibration.

## Owner / test
- **Dev:** implement per-gain tare + `CAL_VERSION` bump.
- **Tester (Pi):** tare at 128, drop to 64 via a heavier load, confirm `mass_g` zero holds across the switch.
