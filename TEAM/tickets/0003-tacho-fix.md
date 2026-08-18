---
id: 0003
title: Fix tacho spurious-pulse artifact (remove +9.7 Hz second pulse source)
area: control
role: dev
status: backlog
assignee: unassigned
depends_on: 0002
branch:
pr:
---

## Goal
Make the tacho read **true shaft speed**: remove the spurious pulse source that adds a constant offset, and restore an independently-verified speed read-out.

## From the diagnosis (ticket 0002)
- `measured = 1.0011 × true + 582 rpm`, plus a **234 rpm phantom on a stationary shaft** → a pulse source independent of rotation.
- Scale/PPR is correct (slope ≈ 1) — **do NOT** re-teach pulses-per-rev; this is not a calibration error.
- **Clue:** the spurious contribution differs between runs (234 rpm phantom at zero vs 582 rpm offset over 13 h) → the source is **variable/environmental**, not a fixed mechanical feature.
- A hard **saturation at 2963 rpm** also to explain.

## Approach
1. **Independent ground truth first** — hand tachometer or phone strobe at 2–3 set points, to calibrate against and confirm shaft speed (open-loop reconstruction says 59.5 × Hz ± slip).
2. **Locate & kill the second source:**
   - *Electrical pickup* — OGT500 signal-line shielding/grounding; route away from VFD/motor power cables; check supply noise. (The VFD is a strong EMI source.)
   - *Stationary reflection* — something reflecting in the sensor's field with the shaft still (the 234-rpm-at-zero proves a static source): re-aim/mask, revisit teach threshold and sensor distance.
   - *Ambient light* — shield the diffuse-reflection sensor from stray light.
3. **Firmware hardening (RP2040)** — ISR debounce + pulse-interval validation to reject spurious pulses; add a **tach timeout** so a lost signal reads 0 / sets a stale flag instead of holding the last period. First confirm what firmware is actually flashed (`INFO` → `fw=`); the intended v1.2.0 source dropped the 100 µs glitch filter — reinstate a proper one.
4. **Saturation** — find why `measured` caps at 2963 rpm (period-measurement floor / counter limit?).

## Acceptance
- Shaft **stationary** → tacho reads ~0 (no 234 rpm phantom).
- `measured` matches an independent hand-tach/strobe reading within a few % at 2–3 set points → intercept ≈ 0, slope ≈ 1 (offset gone).
- No saturation within the operating range.
- Re-run ticket 0002's measured-vs-commanded comparison → offset gone.

## Owner / test
- **Dev:** firmware (debounce / timeout / saturation). **Tester (Pi, at the rig, when free):** hardware (shielding / reflection / light), the independent ground-truth check, and the confirmation run.
