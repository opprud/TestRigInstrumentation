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

## Likely causes — PSU already ruled out (Pi/Kim, 2026-08-27)
**The PSU is good:** Kim measured it at ~5 VDC *before* today's run, so the excitation is verified and the
fault is **downstream of the supply.** Go straight to the wiring and the slip ring, not the PSU.
1. **Wiring / the rotating-side connection** — slip-ring signal or excitation lines to CHAN3 (loose,
   swapped, broken), including the joint where the signal transfers onto the rotating shaft.
2. **The slip ring itself** — worn / dirty brushes or poor contact, so nothing transfers off the rotating
   shaft. With a good PSU and intact wiring, this is the prime suspect.

(The ~5 VDC PSU check stays in the pre-run checklist regardless — cheap insurance for future runs.)

## Test
- PSU at ~5 VDC, shaft spinning, look at CHAN3 for a rotation-correlated signal (scope live view or a short
  capture). Returns -> PSU was the cause, done. Still dead -> check wiring, then inspect the slip ring.

## Owner / test
- **Kim / hardware:** verify PSU voltage; check wiring; inspect the slip ring if the first two are clean.
- **Pi:** re-verify SP shows a rotation-correlated signal after each step.
