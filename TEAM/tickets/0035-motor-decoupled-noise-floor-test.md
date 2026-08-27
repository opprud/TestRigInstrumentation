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
- **Temperatures: 30 / 50 / 70 C** — 30 C is the held low (Kim + windows converged on it; the rig's own
  resting point drifts 24 -> 28 C on friction alone, so a held nominal is the comparable choice).
- At each temperature, **two segments**: **motor-off baseline** (10 min at 30, 5 min at 50/70) then a
  **decoupled staircase** 600 / 1200 / 1800 / 2400 / 3000 rpm, 3 min each. Speeds + acquisition +
  `scope_channels` copied from `Keratech22.json` verbatim, so every cell overlays the 13 h data without
  rescaling. ~830 sweeps, ~8 GB, ~33 OE captures at 5 min.
- **Duration ~2 h 46 min, not "under an hour" — the heater sets the floor.** Measured rate from the 13 h run
  is 30 C/h with the heater calling, so 30->50 and 50->70 are ~40 min each (50 min + 5 min settle allowed):
  ~110 min of ramp vs ~55 min of measurement. It does not compress without dropping a temperature, and Kim
  chose the three deliberately.
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

## Owner / test
- **Kim:** disconnect the coupling. (Motor choice = **both** on and off, decided 2026-08-27; temps = the resting point >=20 C, then 50 and 70.)
- **Pi / Dev:** the down-scaled profile + the noise-floor analysis (RMS/spectrum per channel per temp) and
  the overlay against the 13 h data.
