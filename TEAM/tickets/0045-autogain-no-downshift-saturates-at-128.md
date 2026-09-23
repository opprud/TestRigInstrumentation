---
id: 0045
title: Auto-gain never steps 128 -> 64 under rising load — the cell saturates at ~35 kg instead of reading to 74 kg
area: firmware
role: dev
status: open
depends_on: 0032, 0037
branch:
pr:
---

## Symptom
Setting the rig's clamp load on 2026-09-23 with the board in `mode=auto`, `LOAD?` went to
`ERR 21 ADC_saturation raw=8075254 gain=128` at roughly **35 kg**. The board was **still in gain 128**
— the sensitive band, whose range is half of gain 64's. It never stepped down.

Pinning the band by hand (`SETGAIN 64`) immediately restored a reading: **35.53 kg**, stable to 19 g,
and the tightening continued normally to the real 74 kg ceiling.

## Why it matters
Gain 128 rails at ~35 kg; gain 64 reaches ~74 kg. With auto-gain in this state **the usable load range
is halved**, and the failure is silent in the worst way — it does not return a wrong number, it returns
`ERR 21`, which reads as "the load is over range" when the load is actually well inside what the cell
can measure. Anyone setting a load would conclude they had hit the ceiling at half the real value.

`SETGAIN` is **RAM-only** (a reset returns to auto), so the workaround does not survive a board reset
mid-run.

## Evidence
- `ERR 21 ADC_saturation raw=8075254 gain=128` — saturating *in the 128 band*.
- The board sat at gain 128 through a stable `raw=4206391` (16.80 kg) for several seconds — many reads,
  so the 3-read stability gate had every chance to fire and did not.
- Cross-check that the bands themselves are fine: last valid gain-128 reading **35.03 kg**, first
  gain-64 reading **35.53 kg** — the two agree within **0.5 kg (1.4 %)**. The calibration is good; only
  the *switching* is broken.

## Suspected cause
`auto_scale()`'s step-down threshold looks to sit near **7.5 M counts** (CLAUDE.md records the old
128/64/32 ladder stepping down "above 7.5 M"), while the ADC-saturation guard fires at **8.0 M**. That
leaves a 500 k-count window — and a tightening ramp crosses it far faster than the 3-read stability gate
can confirm, so the guard wins every time. If that is right, auto-gain can *only* step down when the load
creeps very slowly through a narrow band.

## Fix direction
Step down on **headroom**, not on a near-rail threshold: leave 128 as soon as the raw exceeds roughly
half of full scale (~4.2 M), which is where gain 64 can still represent the value comfortably. The
step-*up* threshold (2.5 M) must then keep enough hysteresis below it to avoid oscillation.
Re-check the stability gate: a gate that blocks switching during a ramp defeats the purpose, since a ramp
is exactly when the band needs to change.

## Second finding — readings between the guard and the rail are compressed
Above the 8.0 M guard the raw keeps moving but **understates the load**. Measured: after the 5th turn the
raw sat at ~8.206 M (~76 kg by the gain-64 slope) when turn-counting from the anchor said ~89 kg; the 6th
turn then pushed it to **8388607 = 0x7FFFFF**, the hard 24-bit rail, where it stayed. So the conservative
guard at 8.0 M is **correctly placed** — those values must not be handed out as measurements. Worth a
comment in the firmware so nobody later "recovers" the range by raising the guard toward the rail.

## Acceptance
- Under a rising load the board steps 128 -> 64 on its own and reads continuously to the ~74 kg ceiling,
  with no `ERR 21` below it.
- Verified on hardware by tightening through the crossing while logging, not only in unit tests.

## Owner / test
- **Pi / Dev:** the `auto_scale()` threshold + gate change.
- **Kim / rig:** re-run the tightening sweep past the crossing to confirm on hardware.
