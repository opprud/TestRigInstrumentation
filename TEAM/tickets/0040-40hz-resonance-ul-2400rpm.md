---
id: 0040
title: Structural resonances in UL — the 0.83-1.00 kHz line is characterised and MECHANICAL; a second ~2.4 kHz peak is open; the original 2400 rpm artefact does not survive the rebuild
area: acquisition / data-quality
role: dev
status: in-progress
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


---

# UPDATE 2026-10-05 — two resonances characterised, and the original finding re-scoped

Folded in from the 0046 block archive, the 13 h run `20261002_122423`, and two purpose-built blocks
(`20261005_124521`, `20261005_131704`). Requested by windows on the bus; mechanism is now **decided**,
not proposed.

## A. The 0.83-1.00 kHz line on UL — MECHANICAL, decided

A sharp structural resonance, **Q ≈ 70-100** (10-15 Hz half-width), excited by **shaft rotation**.

**What it is not, in the order the hypotheses fell:**

| hypothesis | killed by |
|---|---|
| VFD switching carrier | **B3a** `20261001_084527`: drive energized, motor STILL → no peak, +7 % over the drive-dead blocks |
| the sinus filter's LC resonance | **B5f** `20261001_125757`: present with the filter OUT, 1971x the local floor |
| a rotational harmonic | speed **tripled** 500→1500 rpm and the frequency moved **1.5 %** (985 → 1000 Hz) |
| electro-acoustic magnetostriction (Eskild) | **`20261005_131704`**, below |

**The magnetostriction kill, which needed to see inside the transition.** With a 5 s window per record
(25 slices of 200 ms, 100 kHz sampling), thirteen state changes were captured *within* a record:

| direction | n | ordering |
|---|---|---|
| **stop** | 8 | the UL line collapses, and **0.6-0.8 s LATER** SP falls, i.e. the drive stops delivering |
| **start** | 5 | SP rises (drive delivering) → **0.4 s later** the line appears |

The line is bracketed **inside** the drive's activity and lags it on both edges. Magnetostriction would
switch on and off *simultaneously* with the drive's output, and could never vanish while the drive is
still delivering — which it does, every time, with 0.6-0.8 s to spare. The collapse is also **gradual,
0.4-1.0 s over 2-5 slices**, where an electrical cessation would fall inside one slice. Coherent
sequence: drive brakes → shaft stops → the line dies with the shaft → drive releases → SP falls.

**Its frequency moves with the mechanics, which is the other reason it is structural:**
985-1000 Hz decoupled · 910-925 Hz coupled · 820-845 Hz in the 0049b block. A switching frequency does
not shift because a shaft is uncoupled.

**Amplitude against shaft speed (coupled, PV 60-80, n=8 per point):** it **peaks at 200-300 rpm**, which
is where any test of it belongs:

| rpm | 89 | 192 | 280 | 380 | 480 | 693 | 993 |
|---|---|---|---|---|---|---|---|
| peak/floor | 6.1x | **41.2x** | **39.7x** | 31.0x | 28.0x | 25.7x | 17.6x |

**The path to UL is the bench structure, not the bearing** — the line is strongest in the decoupled
blocks, where the bearing shaft is not turning at all and only the motor spins.

**Not settled:** whether the resonance lives in the UL probe's own mount or in the bench. **One short
block decides it: move the probe and re-measure at 200 rpm.** If the frequency follows the mounting it is
the fixture; if it stays put it is the bench.

**Also not settled:** whether UL's recorded signal is raw or already demodulated inside the Kistler probe.
The ~1 kHz energy is a **raw** spectral line at 2770x the floor while the Hilbert envelope of the
ultrasound band sits at 2.2-3.4x — the same as at rest — so there is no heterodyne modulation **in the
recorded signal**. If the probe demodulates internally, that line *is* an envelope and the physical
frequency is elsewhere. **Hardware question, answerable from the probe's model/datasheet** (asked on the
bus 2026-10-05).

## B. A second peak at ~2.4 kHz — open

Dominates UL from **1800 rpm upward** and grows with speed, while the 1 kHz band keeps rising underneath:

| rpm | dominant peak | peak/floor |
|---|---|---|
| 500 | 925 Hz | 40.5x |
| 1000 | 910 Hz | 52.4x |
| 1800 | **2420 Hz** | 18.1x |
| 2500 | **2420 Hz** | 30.9x |
| 3000 | **2345 Hz** | 48.2x |

Uncharacterised: no hypothesis tested, no mechanism, no mount dependence. **Next measurement after the
probe move**, and it should reuse the long-window method — a 0.2 s record cannot resolve a transition.

## C. The original 2400 rpm finding does NOT survive the rebuild — re-scope the action

The finding above is dated **2026-08-27**, which is **before the 2026-09-02 rebuild**, and CLAUDE.md makes
that a hard boundary: absolute levels do not carry across it. The ticket's prescribed action — *subtract
the decoupled UL floor measured in 0035 from the archive* — would therefore apply a **pre-rebuild** floor
to **post-rebuild** data. **Do not do that.**

And measured on post-rebuild coupled data (13 h run, ~70 °C), **there is no 2400 rpm anomaly at all:**

| rpm | 2200 | 2300 | **2400** | 2500 | 2600 |
|---|---|---|---|---|---|
| UL | 0.883 | 0.895 | **0.864** | 0.916 | 1.028 |

2400 rpm sits **−5.7 %** against the mean of its neighbours — slightly low, not high. Nothing to subtract.

**And the 75 % was relative to the decoupled floor, which is the wrong denominator for a real run.** The
excess was 0.06629 − 0.03821 = **0.0281 V**. Against the coupled signal at 2400 rpm (0.864 V) that is
**3.2 %**. Even if the artefact persists post-rebuild, it is a 3 % correction, not a 75 % one, and the
ticket's wording invites an over-correction.

**Revised action:** the floor-subtraction is **withdrawn**. If anyone wants the artefact quantified for
post-rebuild data, it needs a fresh decoupled dwell at 2350-2450 rpm — the old numbers cannot be reused.

## Carried forward
- [ ] **Move the UL probe, re-measure at 200 rpm** — mount vs bench for the 0.83-1.00 kHz resonance.
- [ ] **Characterise the ~2.4 kHz peak**, long-window method, 1800-3000 rpm.
- [ ] **Answer the probe-demodulation hardware question** (Kim / Eskild) — it decides whether these are
      acoustic frequencies or modulation rates.
- [x] ~~Subtract the 0035 decoupled floor from the archive~~ — withdrawn, see §C.
