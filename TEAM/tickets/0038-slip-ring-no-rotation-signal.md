---
id: 0038
title: Slip-ring (SP / CHAN3) carries no rotation-correlated signal — verify PSU ~5 VDC, then wiring / slip-ring hardware
area: instrumentation / hardware
role: hardware
status: backlog
depends_on:
branch:
pr:
---

## Problem
In the 2026-08-27 post-power-cycle recommissioning run the **SP / slip-ring channel (CHAN3) showed no
rotation-correlated signal** — nothing that tracks the shaft turning. The slip-ring path is not delivering
a usable signal, so **SP data must be treated as suspect until this is fixed and re-verified** (Pi, 2026-08-27).

## Blocks
- **0035** (motor-decoupled noise-floor test) needs a working SP channel; a dead SP makes the SP part of
  that test meaningless.
- Any run's SP channel is untrustworthy until this is fixed.

## Likely causes, cheapest first
1. **Slip-ring excitation PSU not at ~5 VDC.** The slip ring runs off its own bench PSU with no software
   readback (now a pre-run checklist item, added 2026-08-26). A wrong voltage would leave SP dead or garbage.
   **First step: measure the PSU, set it to ~5 VDC, spin the shaft and see if the rotation signal returns.**
   This may be the whole of it.
2. **Wiring** — slip-ring signal / excitation lines to CHAN3 or to the PSU (loose, swapped, broken).
3. **The slip ring itself** — worn brushes / poor contact, so nothing transfers off the rotating shaft.

## Test
- PSU at ~5 VDC, shaft spinning, look at CHAN3 for a rotation-correlated signal (scope live view or a short
  capture). Returns -> PSU was the cause, done. Still dead -> check wiring, then inspect the slip ring.

## Owner / test
- **Kim / hardware:** verify PSU voltage; check wiring; inspect the slip ring if the first two are clean.
- **Pi:** re-verify SP shows a rotation-correlated signal after each step.
