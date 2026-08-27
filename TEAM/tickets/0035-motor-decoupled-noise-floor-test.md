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

## Profile — down-scaled, both conditions per temperature
- Temperatures: **the resting/ambient point (>=20 C) as the low, then 50 and 70 C.** Kim (2026-08-27): the
  heater only heats, so don't try to pull down to 20 C — take whatever valid temperature the rig rests at
  above 20 C as the bottom point, then heat to 50 and 70.
- At each temperature, **two segments**:
  1. **Motor off** — a few minutes at rest -> the baseline noise floor for that temperature.
  2. **Motor on, decoupled** — a short rpm staircase (a handful of speeds spanning the range, a few minutes
     each).
- Enough sweeps per (condition, speed, temp) cell for a stable RMS + spectrum. Total target well under an
  hour. New profile JSON (not `Keratech22.json` — different intent, fewer temps, decoupled).

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
