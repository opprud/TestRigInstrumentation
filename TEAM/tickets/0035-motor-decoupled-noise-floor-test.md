---
id: 0035
title: Motor-decoupled noise-floor test — a short run at 20/50/70 C with the coupling off, to measure system noise without bearing signal
area: acquisition / characterization
role: test
status: backlog
depends_on:
branch:
pr:
---

## Purpose
Measure the **system noise floor** — what the sensors (UL / AE / SP scope channels + the OE ultrasound
microphone) read with the **motor coupling disconnected from the rig**, so there is no mechanical signal
from a running bearing. A down-scaled version of the 13 h profile at three temperatures (**20, 50, 70 C**)
to see how the noise floor behaves with temperature.

## Why it matters
- The noise floor is the reference every real signal is read against; without it you cannot separate
  signal from noise in any run.
- **It is the control for the lubrication-regime finding.** The 13 h data showed OE microphone energy
  rising with bearing temperature. This test asks the control question: does the noise floor *itself* rise
  with temperature (electronics drift, heater-relay switching, thermal) with **no bearing running**? If it
  does, part of that "lubrication signal" is thermal/system noise, not lubrication — this test either
  confirms the finding or puts a bound on it.
- With the bearing out of the loop it also exposes residual coupling — VFD/EMI, ground loops, heater-relay
  switching into the sensor lines.

## Setup — the physical change
- **Disconnect / loosen the motor coupling from the rig shaft**, so the motor is mechanically decoupled
  from the bearing.
- **Kim's decision (2026-08-27): run BOTH conditions at each temperature.**
  - **Motor off:** pure sensor + thermal + environmental noise — the true baseline floor.
  - **Motor spinning, decoupled:** the rpm staircase, so the sensors capture the motor's EMI/vibration at
    each speed but without the bearing's mechanical signal.
  - Running both is the point: **motor-on minus motor-off isolates the motor's own contribution** to each
    channel, and both isolate from the bearing signal that a normal run adds on top.
- Everything else as a normal run: same scope channels + settings, OE sampling on, the heater driving the
  temperature steps, the pre-run checklist (incl. the new slip-ring ~5 VDC check).

## Profile — BUILT 2026-08-27 (`react/public/config/NoiseFloor_Decoupled_0035.json`)
- **Temperatures: 40 / 50 / 70 C** (as-run, changed from 30 by Kim 2026-08-27). **30 C is not holdable
  decoupled** — with the shaft stationary the oil is not stirred, so it overshoots SV 30 to 38 C and sits at
  36; and Keratech22 has **no 30 C step**, so 40/50/70 overlay three *real* 13 h temperature steps exactly.
  As-run order: staircase first at each temperature, motor-off baseline immediately after (the 20-25 min
  settle before each staircase is the overshoot decaying — measuring inside it would corrupt the result).
- At each temperature, **two segments**: **motor-off baseline** (10 min at 30, 5 min at 50/70) then a
  **decoupled staircase** 600 / 1200 / 1800 / 2400 / 3000 rpm, 3 min each. Speeds + acquisition +
  `scope_channels` copied from `Keratech22.json` verbatim, so every cell overlays the 13 h data without
  rescaling. ~830 sweeps, ~8 GB, ~33 OE captures at 5 min.
- **Duration ~126 min as-run** (630 sweeps, ~6 GB, ~25 OE captures on a held link) — the heater sets the
  floor; measured heating rate is ~30 C/h with the heater calling, so the settle before each staircase is
  overshoot decaying, not slack. (The earlier ~2 h 46 estimate was for the dropped 30 C low; 40/50/70 lands
  at ~126 min.)
- **The ramps are the design, not dead time:** the motor is held OFF through both ramps, so those 110 min
  are a **continuous motor-off baseline sweeping 30 -> 70 C** — the baseline temperature trend as a curve
  rather than three points, and the segment most likely to expose heater-relay switching into the sensors.

## Baked into the profile (beyond the original ticket)
1. **SV is driven to 25 C in the last minute** — the 0034 heater fail-safe, in the profile itself.
2. **`rpm_meas` may read 0 all test** if the tach's reflective mark ends up on the rig side of the
   disconnected coupling. `open_loop: true` makes that harmless, but the **speed of record is
   `59.83 x vfd_cmd_hz`** — analysis must not read `rpm_meas=0` as "motor off". Stamped in the profile.
3. **PV may fall short of SV** — decoupled there is no friction heat, and the 30 C/h was measured *with* the
   motor spinning. Analysis keys on logged `omron_pv_c`, never the target: a 70 C cell landing at 65 C is
   valid, a mislabelled one is not.

## Analysis
- Per channel (UL / AE / SP, mic_amb / mic_mch): **RMS + spectrum** for motor-off and motor-on at each
  temperature (and each speed for motor-on).
- **Motor contribution = motor-on minus motor-off**, per channel per (speed, temp) — isolates the motor's
  own EMI / vibration into the sensors.
- The **temperature trend** of both the baseline (motor-off) and the motor-on floor across the temperatures
  — does the floor rise, and by how much per channel?
- **Overlay against the real 13 h data** at matching (speed, temp) to bound how much of the
  mic-energy-vs-temperature rise is baseline thermal noise vs motor contribution vs real bearing
  lubrication signal.

## As-run result (2026-08-27) — scope solid, OE under-sampled
- **Scope channels: the noise floor is FLAT with temperature** (AE 1.4 %, UL 3.8 %, SP 4.5 % over 30-75 C,
  no trend) — the control result: the mic-vs-temperature rise in the 13 h data is **not** scope thermal
  drift. Full per-channel findings on the bus, 2026-08-27.
- **The 2400 rpm UL artefact -> ticket 0040** (a 40 Hz resonance the motor drives into UL; contaminates the
  archive's 2400 rpm step).
- **OE half is under-sampled — do NOT conclude from it.** 26 captures over 16 cells (one per motor-on cell)
  is single-sample noise, not a trend. Profile miss, not a device fault (26/26 clean). The OE question needs
  a **short follow-up at ONE temperature with `oe.interval_min: 1`** (~120 captures) before another 2 h run.

## Owner / test
- **Kim:** disconnect the coupling. (Motor choice = **both** on and off, decided 2026-08-27; temps = the resting point >=20 C, then 50 and 70.)
- **Pi / Dev:** the down-scaled profile + the noise-floor analysis (RMS/spectrum per channel per temp) and
  the overlay against the 13 h data.
