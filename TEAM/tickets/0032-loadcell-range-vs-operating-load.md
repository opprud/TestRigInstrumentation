---
id: 0032
title: Load cell over-ranges at ~74 kg but the rig runs ~150 kg — operating load is estimated (~25-30%), not measured
area: mechanical / instrumentation
role: dev
status: partial — accuracy half resolved; range half open (hardware)
depends_on:
branch:
pr:
---

## Accuracy half — RESOLVED (2026-08-25)
The ±3-5 % I first reported was the **bench pan procedure**, not the cell. **Mounted in the rig the cell is
~50x quieter** — reading spread **2.8 g** vs 150 g within a bench measurement and 555 g between bench
placements. The cell is undamaged (rated **250 kg**, not the 250 lb first reported; zero returned within
**18 g** of tare after an estimated ~98 kg). Per-gain calibration stands (g128 0.004821, g64 0.009727
g/count, ratio 1.991). **Kim's stated accuracy requirement is ±10-15 %, and below the ceiling we are inside
it.** This half closes.

## Range half — OPEN, and it is hardware
Channel A / gain 64 is the floor; the ADC rails at ~78 kg (**74 kg guard -> `ERR 21`, no value above it**).
**The rig runs ~150 kg — so at operating load the cell is over-range and returns nothing.** It is not
measuring the operating load; it is blind to it. Load above the ceiling is *set*, not read:
- **Load per clamp-turn is not repeatable:** consecutive turns +19.9 / +13.9 / +31.5 kg (factor 2.3).
- **Hysteresis (bedding in, not gone):** back off one turn and return -> −23.8 % (cycle 1), −16.4 % (cycle 2),
  −12.5 % (next). So above the ceiling the load is estimated to **~25-30 %**.
- Today's setting ≈ **150 ± 40 kg** (Kim's decision to go up despite the bound).

**Consequence for runs above 74 kg:** logged load is `ERR 21`; the real load is a **metadata estimate** that
must be written into the run metadata explicitly, because the cell will not carry it.

## Fix if >74 kg must be controlled/measured (Kim's hardware call)
**Resistor divider across the signal pair** — halves sensitivity, doubles range to ~150 kg, keeps channel A +
auto-gain, needs a fresh calibration. Channel B (gain 32, ~163 kg) is **out** — the wiring cannot be moved
(gain 32 was reading an unconnected channel B, now disabled, ticket-adjacent to the firmware work). Described
to Kim, not done.

## Note
Zero drifts with the mechanics (unloaded raw moved 379 g over the bench session), so tare is taken **in-situ
after mounting** (done: tare 690680 @128 / 346464 @64, rig then reads −5.6 / −6.5 g); only the slope travels
with the unit.
