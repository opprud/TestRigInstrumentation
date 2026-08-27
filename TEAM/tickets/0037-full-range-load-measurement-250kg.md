---
id: 0037
title: Full-range load measurement to 250 kg — hardware change (HX711 channel B, or a resistor divider on channel A)
area: instrumentation / hardware
role: hardware
status: backlog
depends_on:
branch:
pr:
---

## Purpose
Measure the **full load range up to the cell's 250 kg rating.** Today channel A rails at ~74 kg (0032), so
at the ~150 kg operating load the cell reads over-range (`ERR 21`, `mass_g` null) and the load is only a
~25-30 % estimate. This is the hardware fix that turns the operating load into a real measurement.

## Two options (both need soldering)
1. **Move the cell onto HX711 channel B (gain 32).** Gain 32 is ~4x the range of gain-128 / ~2x of gain-64,
   which reaches into the 150-250 kg region.
   **Discrepancy to settle first:** ticket 0032 recorded "channel B is out — the wiring cannot be moved",
   and the firmware found gain-32 reading an *unconnected* B input (so it was disabled). Kim's view is that
   **with some soldering the cell (or its signal) can be brought onto channel B.** So job one is to resolve
   whether channel B can actually be wired here. If yes, it is the cleanest path — it uses the HX711's own
   extra range with no added components in the bridge signal.
2. **Resistor divider across the signal pair on channel A.** Halves the sensitivity, doubles the range
   (~150 kg+), keeps channel A + auto-gain. Two resistors go into the bridge signal path — choose values,
   tolerance and tempco carefully, because they sit in the measurement and their drift/mismatch shows up as
   load error.

## Trade-offs
- **Channel B:** no added analog components in the signal (best for noise/drift), but gain 32 is coarser
  (fewer counts per kg), it depends on the wiring being feasible, and the firmware currently *disabled*
  gain 32 — re-enabling + calibrating it is part of the job.
- **Resistor divider:** keeps channel A + auto-gain, but the two resistors are a drift/noise risk if not
  well chosen, and halving the sensitivity worsens resolution at light loads too.

## Notes
- Either way, **re-calibrate after** (per-gain, as in the 0031 / 0032 work) and re-verify with a known mass
  in the new range. The 10 kg reference in the last calibration bypassed the cell (0032) — for a 250 kg
  range you need a known load applied **through the cell** to validate past ~74 kg.
- **Pairs with 0036** (fine 1/4-turn load setting): 0036 sets the load precisely, this measures it —
  together the operating load becomes both controllable and measured.
- **Supersedes the "range half" of 0032.**

## Acceptance
- The cell reads a real value across the operating range up to ~250 kg (no `ERR 21` at ~150 kg), calibrated
  and validated against a known through-cell load past 74 kg.

## Owner / test
- **Kim / hardware:** settle channel-B-wiring-vs-divider, then the soldering.
- **Pi / Dev:** re-enable/adjust the firmware for the chosen path (gain 32 was disabled), re-calibrate,
  validate against a through-cell known load.
