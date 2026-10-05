# What run `20261002_122423` MEASURED — sensor analysis

**Companion to `docs/RUN_20261002_STATUS.md`, not a replacement.** That document covers the run's
health, the tickets it settles and its data quality — and every number in it is correct. This one asks
the question it does not: **what did UL, AE and SP actually record?** Nobody had looked at the sensor
data from the first clean post-rebuild 13 h dataset.

**Method.** Welch periodogram, Hanning, `nperseg=32768`, DC removed, `scaling='density'` integrated over
each band, so the bands sum to the broadband RMS (verified: 0.994 / 0.964 / 0.999 of total for
UL / AE / SP). Sweeps selected from the run's own `telem_*` attributes. Levels are compared against the
coupled noise floor of ticket 0046, block 2B (`docs/0046_noise_floor.csv`).

---

## 1. Dynamic range over the speed staircase, at ~70 °C

| target rpm | measured | UL | AE | SP | UL × floor | AE × floor | SP × floor |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0.0293 | 0.0137 | 0.1067 | **1.0** | **1.0** | 6.3 |
| 500 | 493 | 0.1235 | 0.0166 | 0.1300 | 4.3 | 1.2 | 7.7 |
| 1000 | 994 | 0.3312 | 0.0263 | 0.1234 | 11.5 | 1.8 | 7.3 |
| 1800 | 1798 | 0.6903 | 0.0732 | 0.1225 | 23.9 | 5.1 | 7.2 |
| 2600 | 2592 | 1.0277 | 0.1226 | 0.1288 | 35.6 | 8.6 | 7.6 |
| 3000 | 2963 | 0.9727 | 0.1179 | 0.1306 | **33.7** | **8.3** | 7.7 |

**UL is the rig's instrument.** It sits exactly on its 0046 floor with the shaft stopped and reaches
**34× that floor** at speed — and it rises monotonically through every step. Nothing else on the rig has
that range.

**AE is usable but modest:** on the floor at rest, 8× at 3000 rpm, and it only lifts clear of the floor
above ~900 rpm. Below that it is within 1.5× of background.

**⚠️ SP DOES NOT TRACK SPEED AT ALL.** It sits at 6.3× its floor with the shaft **stopped** and 7.7× at
3000 rpm — flat across the entire staircase. The 0046 blocks saw SP excursions grow with rotation, but
those were measured with the **drive dead**. With the drive live, as in any real run, the drive's output
stage dominates SP completely and **the rotation signal is buried.** This is the practical consequence
of the 0046 finding that the drive output is SP's largest source, and it means **SP data from a driven
run is a drive-noise record, not a slip-ring measurement.**

---

## 2. Temperature, at a fixed 1800 rpm — and the central finding needs refining

Steady state only (first hour excluded, see §3), 45 → 100 °C:

| | UL | AE | SP |
|---|---|---|---|
| **broadband RMS** | 0.6732 → 0.6116 — **0.91×** | 0.0625 → 0.0911 — **1.46×** | 0.1313 → 0.1213 — 0.92× |
| 0–10 kHz | 0.6674 → 0.6142 — 0.92× | flat (1.01×) | 0.78× |
| **10–50 kHz** | 0.0321 → 0.0469 — **1.46×** | 0.0327 → 0.0410 — 1.25× | 0.78× |
| **50–100 kHz** | 0.97× | 0.0345 → 0.0662 — **1.92×** | 0.79× |
| 100–200 kHz | 0.99× | 0.0336 → 0.0479 — 1.43× | 0.83× |
| 200–500 kHz | 1.00× | 1.22× | 0.93× |
| 500 kHz–1.25 MHz | 0.99× | 0.98× | 1.01× |

### The headline: broadband UL RMS conflates two opposite trends

**UL's 0–10 kHz band is essentially all of UL** (0.667 of a 0.673 total), and it falls 8 %. **UL's
10–50 kHz band rises 46 %.** Because the low band dominates the RMS, the rise is invisible in a
broadband number — the RMS simply reports the low band's fall.

**AE rises everywhere from 10 kHz to 500 kHz, peaking at 50–100 kHz where it nearly doubles (1.92×).**

So both acoustic channels say the same thing in their mid-to-high bands: **emission increases with oil
temperature**, while UL's low-frequency content decreases. That is the signature of a thinning oil film —
less damping and more asperity contact produce more high-frequency emission — and it is the opposite of
what "UL falls with temperature" suggests.

**CLAUDE.md records the finding as UL RMS falling −16 to −36 % reversibly with bearing temperature. That
is true of broadband RMS and it is measured; but as physics it is at best half the story, and this run
measures the fall at only −9 % over 55 degrees.** Anyone reading oil-film behaviour out of UL should work
in bands, not in RMS.

### Is AE's rise just the heater?

No, and it is worth showing why, because the heater's duty cycle does move AE (see `0046_REPORT.md` §6).
The heater's **entire** AE contribution, measured at full power against modulating, is
0.0206 − 0.0145 = **0.0061 V**. AE's rise here is **0.0275 V — 4.5× the heater's maximum possible
contribution.** And the rise is concentrated in 50–100 kHz, which is the heater **relay's** band, but
block 6 measured the relay's effect on AE at only ~1.07×, against the 1.92× seen here. Neither heater
mechanism is large enough.

---

## 3. The run-in transient dominates any single ramp

At a fixed 1800 rpm inside the first hour, with the oil at a near-constant 41–43 °C:

| tick | PV | UL |
|---|---|---|
| 1152 s | 43 °C | 1.0166 |
| 1176 s | 42 °C | 1.0906 |
| 1200 s | 42 °C | 1.0121 |
| 2580 s | 41 °C | 1.0164 |
| 2616 s | 41 °C | 0.9641 |
| 2640 s | 41 °C | 0.8707 |
| steady state | 45 °C | **0.6732** |

**UL falls 34 % from the first 1800 rpm point to steady state while the temperature does not change.**
Against the whole 45 → 100 °C temperature effect of −9 %, the transient is **3.8× larger**.

This confirms the 2026-09-24 confound on a 13 h dataset and sharpens it: **on a single monotonic ramp the
transient, not temperature, is the dominant term.** `docs/Prerun_Checklist.md` §8 asks for settling or a
recorded time-since-start; this quantifies why. It also explains how a single ramp produced the
−42 to −50 % once quoted as the temperature response.

---

## 4. What to take from this run

1. **Use UL, in bands.** It has 34× dynamic range and it is the only channel on the rig that does.
2. **Do not read the slip ring from a driven run.** SP is flat against speed; it is recording the drive.
3. **Exclude the first hour, or record time-since-standstill.** The transient outweighs temperature.
4. **Report UL as bands, not RMS**, whenever the question is about the oil film.

## 5. Limits

- One run, one oil, one clamp load — **150 kg**, the standard set 2026-10-05, which is above the load
  cell's range, so **load is null throughout the file**: take it from these notes, not from the h5.
- Temperature and time-since-start are **correlated by construction** in this profile: SV rises
  monotonically. §3 separates them only because the first hour holds temperature roughly constant while
  the transient runs. A proper separation needs the temperature-cycling design of `UL_TempCycle_6h`.
- Speeds are open-loop from drive frequency; `rpm_meas` agreed to a median 0.29 % (see the status report).
- Bands are relative to this run's own method; compare against `docs/0046_noise_floor.csv`, which uses
  the same windowing, rather than against figures computed elsewhere.

---
*Written 2026-10-03 from the run's own HDF5 on the Pi. Source data: `eceherning/20261002_122423/`.*
