---
id: 0038
title: Slip-ring (SP / CHAN3) read through a DETACHED scope probe ground for at least two months — all archived SP data is invalid
area: instrumentation / hardware
role: hardware
status: root-caused
depends_on:
branch:
pr:
---

## Resolution (2026-08-29) — it was the scope probe's ground lead, not the slip ring

The slip ring **works**. The original diagnosis in this ticket was wrong, and so was the
"SP is picking up drive EMI" refinement built on top of it. Both were measured through a
**scope probe whose ground lead was detached**, which removed the DC reference and left the
probe tip acting as an antenna.

Kim found the loose ground while re-assembling the rig. Two independent confirmations followed:

1. **The 5 V pedestal came back.** With the ground attached, CHAN3 sits at a rock-steady
   **Vavg = 4.87 V** at every speed — the slip ring's own ~5 V excitation, the same voltage Kim
   measured at the PSU. Every archived run reads **SP mean = -0.02 V**: no pedestal, because there
   was no reference.
2. **Kim turned the shaft by hand and watched the slip-ring voltage follow it.** Direct, physical,
   and not dependent on any of our software.

Measured across speed with the ground attached (200 ms window, CHAN3 at 40 V full scale):

| condition | Vpp | Vmax | Vmin | Vavg |
|---|---|---|---|---|
| standstill | 3.60 | 6.6 | 2.8 | **4.87** |
| 600 rpm | 6.20 | 7.8 | 2.0 | **4.87** |
| 1200 rpm | 5.60 | 8.4 | 1.8 | **4.87** |
| 1800 rpm | 6.40 | 8.2 | 1.8 | **4.87** |
| 2400 rpm | 2.00 | 6.0 | 3.6 | **4.87** |
| 3000 rpm | 2.20 | 6.0 | 3.8 | **4.87** |
| stopped again | 3.80 | 6.6 | 3.2 | **4.87** |

The mean never moves; the **excursions** grow with rotation and shrink again when it stops, and
they are repeatable in both directions. Note the swing is **not monotonic with speed** — it peaks
around 600-1800 rpm and falls back at 2400-3000. Unexplained, and worth understanding before SP is
used quantitatively.

## The damage: how far back does it go?

**At least 2026-06-29, the oldest run still on the Pi.** SP's DC mean is a clean discriminator —
~5 V with the ground attached, ~0 V without — so it can be read straight out of any archived file.
Every one of the **23 runs still on disk reads -0.014 to -0.039 V**:

```
20260629_123929  20260629_124229  20260629_124542
20260817_093300  20260817_094134  20260817_101906  20260817_103152  20260817_112734
20260818_075336  20260818_081609  20260818_083247
20260819_102659  20260819_104244
20260820_091355  20260820_091646  20260820_093823  20260820_103317  20260820_105246  20260820_112759
20260825_123149  20260827_111736  20260827_122907  20260827_131108
```

**Every SP dataset in the archive is invalid**, including the three 13 h runs and the 0035
noise-floor run. The four blobs in `eceherning` were not checked directly (114 GB), but they were
taken inside this window, so the same applies unless someone proves otherwise — and the check is
one sweep's SP mean per file.

**Nothing else is affected.** UL and AE have their own probes and their own grounds, and both show
correct DC levels and correct rotation response throughout. The 0035 conclusion that the UL/AE
noise floor is flat with temperature stands, and so does the finding that UL responds to the
bearing by a factor 20 over the decoupled floor.

## What this retracts

- **"SP carries no rotation-correlated signal"** (2026-08-27) — wrong. It carries one; we had no
  reference to see it against.
- **"SP is drive EMI: +43 % with the motor on, flat with speed"** (0035 smoke test) — that is what a
  floating probe does near a running VFD. Not a property of the slip ring.
- **"SP motor-off drops from 0.133 to 0.089 when the heater relay closes"** — same cause. A floating
  tip responds to anything nearby switching.

## Follow-on work, now that the channel is real

1. **Scope range corrected (done 2026-08-29).** SP spans **1.8 - 8.4 V**, so the old
   `volt_range 8.0 / volt_offset 0.0` window (-4 to +4 V) clipped over half of it. Now
   **`volt_range 16.0 / volt_offset 5.0`** in all seven live profiles and on the scope. Can be
   tightened to 8.0/5.0 once a full run shows no clipping.
2. **The trigger needs a deliberate level.** The scope triggers on **CHAN3 itself**, negative edge.
   The level had to be re-set for the 5 V pedestal. What the right level is depends on what the
   slip ring actually carries — if it has a once-per-revolution feature the level belongs on that,
   not at mid-swing. **Needs one clean capture of the SP waveform to decide.**
3. **Re-verify SP against speed** through the normal acquisition path and confirm the rotation
   response survives into the HDF5.

## Owner
- **Kim / hardware:** found it. Keep the probe ground in the pre-run checklist.
- **Pi:** scope range + profiles done; trigger level and the SP waveform characterisation open.
