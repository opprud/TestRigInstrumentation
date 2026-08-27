---
id: 0036
title: Load-application mechanism — switch the weight/clamp tightening to Allen bolts adjustable in 1/4-turn increments
area: mechanical
role: mechanical
status: backlog
depends_on:
branch:
pr:
---

## Purpose
Make the applied load (clamp force / weight) **fine and repeatable to set.** Rework the tightening
mechanism to use **Allen (hex-socket / umbrako) bolts** so the load can be adjusted in defined
**1/4-turn increments** — a known, small load step per quarter turn.

## Why — the current mechanism is coarse and non-repeatable
Measured while setting the ~150 kg operating load (ticket 0032):
- **Load per turn is not repeatable** — consecutive turns gave **+19.9 / +13.9 / +31.5 kg** (a factor 2.3
  between neighbours).
- **Hysteresis:** back off one turn and return -> −23.8 % (cycle 1), −16.4 % (cycle 2), −12.5 % (next).

So you cannot dial in a target load or reproduce it run-to-run. Above the load cell's 74 kg ceiling the
load is already only a ~25-30 % estimate (0032); a coarse, non-repeatable adjustment makes that worse.

## The change
- Replace the current tightening with **Allen bolts** adjustable in **1/4-turn steps**, giving a known,
  small load increment per quarter turn.
- Choose the **thread pitch** (and lever / spring geometry) so one 1/4 turn is a sensible load step for
  fine control around the operating load — small enough to dial in a target, not so fine it takes forever.
- Consider a reference mark / detent so 1/4 turns are countable and repeatable by feel.

## Notes / what to settle during the work
- **Characterise the current mechanism first** — what actually sets the load (plate + spring? lever?), so
  the bolt / pitch choice is grounded.
- Bolts + defined increments fix the *granularity*, but the **hysteresis** above is a spring/mechanical
  property that finer steps alone may not remove — check whether the redesign also reduces it, or whether
  a bed-in / preload procedure is still needed.
- **This is the "set the load" half; 0032 is the "measure the load" half.** They complement: fine setting
  (this) + a cell that can read >74 kg (0032's resistor-divider) together make the operating load both
  controllable and measured.

## Acceptance
- Load adjustable in repeatable **1/4-turn increments** with a known, characterised **kg per quarter turn**.
- Per-increment variability materially better than today's ±25-30 % per turn — verified by measuring the
  load-per-quarter-turn over a few cycles (as 0032 measured per-turn).

## Owner / test
- **Kim / mechanical:** the physical redesign (bolts, pitch, geometry).
- **Pi / Kim:** re-characterise load-per-quarter-turn after the change — repeat the turn-by-turn measurement
  from 0032 in 1/4-turn steps to confirm the increment and its repeatability.
