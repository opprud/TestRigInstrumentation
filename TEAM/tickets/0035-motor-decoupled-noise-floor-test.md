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
- **One decision to confirm with Kim — does the motor spin, or stay off?**
  - **Motor spinning, decoupled (recommended; this is what "a down-scaled 13 h" implies):** run the same
    rpm staircase, so the sensors capture the motor's EMI/vibration **at each speed** but without the
    bearing's mechanical signal — a per-operating-point noise floor you can subtract from real data.
  - **Motor off:** pure sensor + thermal + environmental noise, no motor contribution at all. Simpler, but
    it does not separate motor-EMI from bearing signal, and it drops the speed dimension.
- Everything else as a normal run: same scope channels + settings, OE sampling on, the heater driving the
  temperature steps, the pre-run checklist (incl. the new slip-ring ~5 VDC check).

## Profile — down-scaled
- Temperatures **20, 50, 70 C** (three points, vs the 13 h's 40 -> 100 in 5-degree steps). **Note: 20 C may
  be below what the heater can hold** — the heater only heats, so 20 C is effectively the rig's resting
  temperature; confirm it is reachable / just log the ambient resting value if the heater cannot pull down.
- A short rpm staircase per temperature *if the motor spins* — a handful of speeds spanning the range,
  a few minutes each, enough sweeps per (speed, temp) cell for a stable RMS and spectrum.
- Total target well under an hour. New profile JSON (do not reuse `Keratech22.json` — different intent,
  fewer temps, decoupled).

## Analysis
- Per channel (UL / AE / SP, mic_amb / mic_mch): **RMS + spectrum of the noise floor** at each temperature
  (and each speed, if the motor spins).
- The **temperature trend** of the noise floor 20 -> 70 C — does it rise, by how much, per channel?
- **Overlay against the real 13 h data** at matching (speed, temp) to quantify signal-above-noise, and
  specifically to bound how much of the mic-energy-vs-temperature rise is noise-floor drift vs lubrication.

## Owner / test
- **Kim:** disconnect the coupling; confirm the motor-on/off choice and whether 20 C is reachable.
- **Pi / Dev:** the down-scaled profile + the noise-floor analysis (RMS/spectrum per channel per temp) and
  the overlay against the 13 h data.
