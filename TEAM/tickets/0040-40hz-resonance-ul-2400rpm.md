---
id: 0040
title: 40 Hz resonance — the motor drives an artefact into UL at 2400 rpm, contaminating the archive's 2400 rpm step
area: acquisition / data-quality
role: dev
status: backlog
depends_on:
branch:
pr:
---

## Finding (0035, motor decoupled, 2026-08-27)
With the coupling **off** (no mechanical bearing path), UL is indistinguishable from the motor-off floor at
600 / 1200 / 1800 rpm, then **jumps +75 % at 2400 rpm (drive 40.1 Hz)** and +12 % at 3000 rpm. The 2400 rpm
standard deviation is ~8x the others, so it is not a steady tone. **Something resonates around 40 Hz and the
motor drives it into the UL probe with nothing mechanically connected** — a motor/structural artefact, not
bearing signal.

UL RMS pooled over temperature (n=45/cell): off 0.03786 · 600 0.03828 · 1200 0.03799 · 1800 0.03821 ·
**2400 0.06629** · 3000 0.04234.

## Why it matters — the archive is affected
**Keratech22 hits 2400 rpm on every temperature plateau**, so **at the 2400 rpm step of every 13 h run part
of UL is motor artefact**, not bearing / lubrication signal. It does not invalidate those sweeps, but UL at
2400 (and to a lesser degree 3000) must have this floor **subtracted** before it is compared with the
neighbouring speed steps or read as a lubrication trend.

## Actions
- **Analysis (do this):** subtract the decoupled UL floor at 2400 / 3000 rpm (measured in 0035) from the
  archive UL before drawing any per-speed lubrication conclusion; flag 2400 rpm as caveated in every
  UL-vs-speed comparison.
- **Investigate the source (optional):** what resonates at ~40 Hz — a structural / mount resonance, a motor
  order, or the probe fixture? If it can be damped or the fixture stiffened the artefact shrinks; if not,
  the subtraction is the mitigation.

## Owner / test
- **Dev:** the floor-subtraction in the UL analysis.
- **Kim / Pi:** if worth chasing, a decoupled dwell around 2350-2450 rpm to bracket the resonance and see
  whether a mount / fixture change moves it.
