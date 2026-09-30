---
id: 0046
title: Electrical-noise source characterization — attribute sensor-channel noise to PSU / VFD sinus filter / drive EMI, one source at a time
area: acquisition / characterization
role: test
status: backlog
depends_on: 0035, 0038
branch:
pr:
---

## Purpose
Find **where the electrical noise in the sensor channels comes from** and how much each source
contributes — the switch-mode PSU we use today vs a clean linear 24 VDC lab supply, the VFD's sinus
(output) filter on vs off, drive EMI vs mechanical vibration, and the heater relay. Kim's investigation,
2026-09-30.

## Method — a ladder from silence, ONE variable at a time
The whole point is attribution: a 2×2 alone gives you the two factors' *effects* but not *which* element
is responsible. So start from a quiet floor and **add one source at a time**, then do the 2×2, then the
decoupled sweep. Every block:
- **stationary and heater relay HELP OFF** (the heater relay is itself an EMI source — 0035 saw a
  heater-relay → SP coupling — so it must be off for a clean electrical read; it comes back as its own
  factor at the end),
- same scope channels + acquisition settings as a normal run, so blocks compare without rescaling,
- **log which configuration each block is** (PSU type, sinus on/off, motor state) in the run notes /
  `/metadata` so a plot can never be mis-attributed later.
- **Hold the ambient electrical environment CONSTANT across ALL blocks** (other powered devices in the
  room on/off the same) and **record block 0's room state**. 2026-09-30: an *unrelated* device near the
  cabling was 1.06 MHz-coupling into SP at ~10 % (SP total −10.6 % when Kim switched it off). The ambient
  is a hidden variable: a delta is only clean if the intended variable is the *only* thing that changed,
  so a device switched on during block 4 would look like the sinus filter. If something must stay on,
  record it per block so it can be subtracted.

## Blocks

**0. Bare floor — the reference.** Sensors powered at their operating point (**24 VDC switch-mode PSU
   + slip-ring ~5 VDC PSU both ON**, Kim 2026-09-30), but **nothing driving them: VFD fully powered down
   (mains off, not merely un-commanded — an idle VFD's DC bus + switching is still live), motor off,
   heater relay open (Shelly ch0 off — the unit stays powered, it's toggled in block 6).** No extra bench
   gear powered near the sensor cabling. ~30 min stationary acquire, same scope channels/settings as a
   normal run. This is "sensors sitting quiet" — the floor every later block is read against.
   **Read the floor from a run whose settings applied:** the scope refuses its first connection after idle on ~4/5 cold starts (deterministic, recovers on attempt 2 — Pi), so the two `ConnectionRefused` lines at the top of every block log are EXPECTED, not a noise finding; check the `acquisition depth requested=… scope reports=…` line before trusting block 0.

> **BLOCK 0 MUST ALSO RECORD WHAT ELSE IN THE ROOM IS POWERED (Kim, 2026-09-30).** Learned the hard
> way during the first attempts: an **external device that is not part of the bench but sits close to
> the sensor cabling** was the *dominant* source of the 1060.7 kHz line, and switching it off dropped
> that line to **28 %** and **SP's total AC RMS by 10.6 %**. It was caught only because Kim happened to
> switch it off mid-run, which produced an accidental in-run A/B. Before that, the line had been
> attributed to one of the two PSUs on the reasoning that the drive was fully dead — so **block 2 would
> have shown the linear supply "fixing" something the switch-mode supply never caused**, with the false
> attribution baked into the reference floor that every later delta is measured against.
>
> The block-0 spec already said *"no extra bench gear powered near the sensor cabling"*. That is not
> enough on its own, because it is a negative instruction nobody can verify after the fact. **Record the
> room's state positively, in the run notes, as part of block 0's configuration:**
>
> ```
> ROOM INVENTORY (block 0 only — the floor every delta is read against)
>   device / instrument ............ state (ON / OFF / unplugged) ... approx. distance to sensor cabling
>   ...
>   anything switched OFF specifically for this block, and why
> ```
>
> Block 0 only. The later blocks are read as *deltas against* block 0, so as long as the room does not
> change between them the inventory does not have to be repeated — but **if anything in the room is
> switched on or off mid-ladder, that block is void** and must be re-run, exactly as the split attempt
> `20260930_085938_SPLIT_device_off_at_t20` was.

**1. (folded into block 0.)** The switch-mode PSU is already ON in the floor, so there is no separate
   "turn the PSU on" step — the switch-mode-vs-linear contribution is the **block 0 → block 2** delta.

**2A. Swap the sensor supply to the linear 24 VDC lab supply** (everything else as block 0). **Delta vs
   block 0** = the 24 V switch-mode PSU's own contribution, isolated. With the 5 V slip-ring/OE supply
   linear and the VFD dead, the 24 V switch-mode is the *only* switching supply left on the bench, so
   residual 1060.7 kHz **vanishing** here = it's the switch-mode PSU; **surviving** = the source is not a
   bench supply (Pi's supply / scope / room).

**2B. Switch off the heater/temperature control box** (Kim, 2026-09-30 — a black box on its own 220 VAC,
   cannot be opened, so treat it as a whole), everything else as 2A. The heater element is off throughout,
   so anything that changes is the **box's own electronics/PSU**, cleanly separate from block 6's relay
   toggle. **Because the box can't be inspected, the result tells us what it feeds:** a channel going
   **DEAD** (flat/zero) = the box was powering that sensor's supply → a confound, flip it back on and note
   it; a channel merely getting **quieter** = the box's conducted EMI, which is what we want. Watch the
   live view as Kim flips it; one change at a time; log the off timestamp for a clean in-run A/B.

**0b. (diagnostic — insert before block 3, Pi/Kim 2026-09-30.) Disconnect the sensor from a scope
   channel, or short the probe at the input, and re-acquire ~5 min.** If 1060.7 kHz is still present
   with **nothing connected**, it is the **scope itself** — an instrument artefact under EVERY block
   that no rig-supply work can remove, and every later delta is measured on top of it (characterise +
   subtract it, don't chase it on the rig). If it disappears, the line is coupled in from outside and
   2B / the room are the candidates. **Run this BEFORE 2B** — a 'scope internal' result makes 2B moot
   for the 1.06 MHz line. Result of 2A (2026-09-30): the 24 V switch-mode PSU is NOT the 1.06 MHz
   source (line survived the linear swap, within scatter) — so the source is off-bench; do NOT buy a
   linear sensor supply to remove it.
   > **RESULT 0b (`20260930_110822`, 50 sweeps, archived):** CH3/SP probe tip shorted to its own ground
   > clip (UL + AE left connected as in-run controls — Kim could not reach them, which is better: SP
   > carries the question, the two live channels are a control inside the same acquisition). **1060.7 kHz
   > SURVIVED, −7.4 % (1.185e-3 → 1.097e-3), while UL/AE moved <2 %.** All three channels carry the line
   > at comparable amplitude regardless of what is connected = **common source on the instrument side,
   > not the rig.** No rig-supply/box/cabling work removes it. → **2B is moot for the 1.06 MHz line**
   > (still run 2B for the box's *other* effects + the dead-channel confound check). CAVEAT written into
   > the run notes: SP also went +25 % broadband when shorted — that is the shorted tip+clip loop acting
   > as a magnetic-pickup antenna (+ slip-ring's low source-Z removed), a property of the measurement, so
   > **do NOT quote it as "shorting the probe increased rig noise."**
   >
   > **OPEN FORK — not run, documented (Pi/windows 2026-09-30):** 0b rules out the *rig* but does not
   > split **scope-internal vs probe/cable pickup**. That split needs the probe removed and a **BNC short
   > at the scope input** — which drops the 10× attenuation and so needs its own baseline (a "block 0c",
   > not a variant of 0b). **Decision: not worth running for 0046** — "the line is in the instrument
   > chain, not the rig" is a sufficient answer for attribution. 0c is only needed if someone later wants
   > to *reduce* the floor rather than just attribute it. Left as a documented option.

**3. + VFD energized, motor slow (manual mode), sinus filter OFF.** Delta vs 2 = drive EMI at the sensor
   channels with no output filtering.

**4. Same as 3 but sinus filter ON.** Delta vs 3 = how much the sinus filter cleans the drive EMI.

### The 2×2 (the "4 combinations")
Blocks 1–4 already contain it, but run it explicitly as a clean 2×2 at one condition (manual mode, slow
motor, no heat, ~5 min per cell):

| | switch-mode PSU | linear 24 VDC |
|---|---|---|
| **sinus OFF** | | |
| **sinus ON**  | | |

**5. RPM sweep 500 → 3000 rpm, sinus ON and OFF — with the MOTOR MECHANICALLY DECOUPLED from the rig.**
   Decoupling is the key control: it removes bearing/rig vibration, so any noise that **scales with rpm
   while decoupled is electrical (drive PWM/EMI), not mechanical.** Same logic that settled SP in the 0035
   smoke test (SP jumped +43 % *flat* with speed = drive EMI, not vibration). Speed of record is
   `59.83 × vfd_cmd_hz` if the tach mark ends up on the rig side of the coupling (see 0035).

**6. (optional, last) heater relay as its own factor.** Repeat block 0's stationary floor but **toggle only
   the heater relay** (ch0) at fixed everything-else. Any step in the sensor channels on the toggle = the
   heater-relay coupling path (the second coupling 0035 flagged), isolated from the drive.

## Analysis
Per channel (UL / AE / SP, and OE if run): **RMS + spectrum** for every block. The deltas that matter:
- **0→1→2:** the switch-mode-vs-linear PSU contribution.
- **3→4 and the sinus row of the 2×2:** what the sinus filter buys.
- **block 5:** does noise track rpm *while decoupled* → EMI vs vibration split, per channel.
- **block 6:** heater-relay coupling, isolated.
Look in the spectrum for switch-mode / PWM switching frequencies and their harmonics, not just RMS.

## Owner / test
- **Kim / hardware:** swap PSU (switch-mode ↔ linear 24 VDC), sinus filter in/out (**a quick wire-move**, confirmed Kim 2026-09-30 — so the {PSU}×{sinus} 2×2 is two fast swaps), decouple the motor,
  run manual mode. Record which configuration each block is.
- **Archive EVERY block run to Azure** (Kim, 2026-09-30): the uploader (h5 + sidecars + md5, 0013) to
  `eceherning` — **do NOT mark these `DO_NOT_ARCHIVE`**, each block is analysis-worthy characterization
  data. Encode the config (block #, PSU type, sinus on/off, motor state) in the run notes so every blob
  is self-describing.
- **Pi / dev:** the block profiles (or manual-mode drive + a stationary acquire), the RMS/spectrum
  analysis per channel per block, and the deltas above.
