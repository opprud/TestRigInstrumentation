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
   > **RESULT 2B (`20260930_112905`, 149 sweeps, archived) — the first POSITIVE attribution in the
   > ladder.** The heater/temp box is the source of **AE's 129.5 / 131.5 kHz pair**: with the box's
   > 220 VAC off, 131.5 kHz **−48.8 %** (9.616e-4 → 4.920e-4), 129.5 kHz **−46.5 %** — a halving against
   > ~2 % measurement scatter (25×), unambiguous. **Chained from the floor:** block 0 1.092e-3 → 2A
   > −11.9 % (the 24 V switch-mode supply's share) → 2B −48.8 % (the box's share of the remainder) =
   > **now 45 % of the floor; the two changes removed 55 %.** So the pair has **≥2 contributors, the box
   > the bigger.** **Confound check PASSED — no channel went dead** (SP still carries its ~4.9 V pedestal,
   > single-capture mean +4.8821 V; UL/AE normal), so the box was NOT feeding any sensor's supply and the
   > 49 % is **genuine conducted EMI, not signal loss.** **Coupling is AE-specific** (UL moved <2.5 % on
   > every line/band) → each channel picks up a different source by a different path, so a fix for one
   > line need not touch the others. **1060.7 kHz did NOT move** (UL −1.5 %, AE +4.0 %, SP −2.3 %) —
   > confirms 0b: the scope+probe chain makes that line, the box can't be its source.
   >
   > **CODE GOTCHA fixed (Pi, 2026-09-30):** first 2B attempt died before its first tick — the profile
   > name held a `/` ("heater/temp control box"), the runner builds the telemetry filename from the
   > profile name and only collapsed whitespace, so the path pointed into a non-existent subdir →
   > `write_text` raised `FileNotFoundError` → set `stop_event` → acquisition stopped at **zero sweeps**,
   > leaving an 18 kB HDF5 that opens fine and holds nothing. `safe_name` now maps anything outside
   > `[A-Za-z0-9._-]` to `-` (existing names produce byte-identical filenames). **Cost one block here;
   > would have silently cost a 13 h run.**

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

> **LADDER CORRECTION (Kim, 2026-10-01 — "igen en ting af gangen").** The original block 3 (*"+ VFD
> energized, motor slow, sinus OFF"*, delta = "drive EMI") bundled **two** changes — the drive gets mains
> power *and* the motor starts turning — and with the motor **coupled to the rig** it is effectively
> **three**, because rotation brings mechanical vibration. A ladder from silence cannot move two rungs at
> once, so "drive EMI" would not have been what that delta measured. Split into 3a / 3b / 4, with **block
> 5 (decoupled) as the only rung that can separate drive EMI from vibration.** Baseline for all drive
> blocks is **2B** (linear PSU, heater box off); the box stays off through 3a–4 and comes back only in
> the 4b reversibility test.

**3a. + VFD energized at the MAINS, motor STILL (not commanded), sinus OFF.** Delta vs 2B = the idle
   drive's electrical contribution **alone** — DC bus charged and switching live, nothing rotating.
   Needs nothing from Kim if the drive is already energized and idle; motor coupling is irrelevant here
   (a stationary motor makes no vibration).
   > **RESULT 3a (`20261001_084527`, 74 sweeps, archived):** an idle energized VFD costs **SP +54.5 %
   > total** (0.016962 → 0.026213), broadband +43–80 % in every band, SP 131.5 kHz **+93.9 %**, 129.5 kHz
   > **+94.1 %**, 38.67 kHz +68.3 %. **UL +3.4–5.1 %, AE +0.6 % (untouched), 1060.7 kHz +2.4 %.** SP is
   > hit hardest because the slip ring sits on the shaft near the motor and is galvanically tied through
   > the rig — again each channel has its own path.
   > **This measures block 0's spec:** the drive was required off at the *mains*, not merely
   > un-commanded, because an idle VFD's DC bus + switching is still live — now quantified at **55 % of
   > SP's total noise before the motor turns at all.** A floor taken with the drive merely *stopped* is
   > **not a floor** — state it plainly for any future baseline.

**3b. + motor turning ~600 rpm, sinus OFF.** Delta vs 3a = adds rotation. **CAVEAT: with the motor
   COUPLED to the rig (Kim's current setup) this delta carries drive-load EMI *and* mechanical vibration
   together — it is NOT pure drive EMI.** Only block 5 (decoupled) splits them.
   > **First attempt 2026-10-01 did NOT actuate — the documented 02-03 trap.** Pi commanded 600 rpm /
   > 10.08 Hz; the drive echoed `vfd_cmd_hz 10.08` but the shaft never moved (tach `rpm_meas 0.0`, pulse
   > counter frozen at 2425345). Kim had set the drive to **local/manual** when he energized it, so Modbus
   > frequency is accepted, echoed and ignored (Prerun_Checklist §3). Pi stopped at 90 s and **deleted the
   > partial** rather than archive sweeps mislabelled "600 rpm" on a stationary shaft. **PENDING KIM'S
   > CALL:** (1) set **02-03 to communication** and Pi drives — *recommended*, because 3b and 4 differ
   > only by the sinus filter so the speed must be **identical** across them or it pollutes that delta,
   > and block 5's rpm sweep needs programmatic control anyway; or (2) Kim **hand-drives** and Pi uses the
   > passive profiles — the tach stamps `rpm_meas` on every sweep either way, so speed is still recorded,
   > but the two blocks may not sit at the same rpm. Verify actuation against the tach after (§3).
   > **RESULT 3b (`20261001_103916`, 589 rpm verified three ways — Pi's command, the drive display 10.08 Hz
   > read by Kim, and the tach):** with the motor **coupled**, "motor running" measures the **bearing, not
   > the drive.** UL total **+868.8 %** (0.0300 → 0.2905), its 1–10 kHz band **+9429 %** — that is the
   > Kistler probe's bearing acoustic emission, i.e. **signal, not noise.** AE +84.0 % (50–100 kHz +367 %
   > = the accelerometer responding to rotation). SP +71.0 %, **uniform across every band** — some may be
   > electrical but it cannot be separated from vibration here. **So UL and AE cannot be used as noise
   > measurements at all with the coupling in, and SP's rise is confounded.** 3b stays archived as a clean
   > operating-point record but is **NOT a rung in the noise ladder** → block 5 (decoupled) is the only
   > block that can answer the drive-EMI question once the shaft turns.
   > **Oil-film aside (uncontrolled, Pi):** UL at ~600 rpm was 0.125 V in the 2026-09-23 baseline and
   > 0.29 V here = **2.3×**, after ~6 days idle — the direction the rest-reset finding predicts. Configs
   > differ (box off, linear 24 V, different day) so it is **an observation, not a controlled result**;
   > noted because it is an independent hint from a measurement built to look for something else.

**4. (SUPERSEDED as a noise rung, 2026-10-01 — fold into block 5.)** Originally "same as 3b but sinus ON,
   delta = what the sinus filter cleans." 3b proved a **coupled** motor block is bearing-dominated, so a
   sinus-filter delta would be buried under the bearing signal on UL/AE and confounded on SP. **The sinus
   on/off comparison moves into block 5 (decoupled), which already runs both** — a coupled block 4 adds
   nothing the decoupled sweep won't give cleanly. (Architect call; Pi/Kim to confirm.)

**4b. (reversibility test — profile added 2026-10-01.) Heater box back ON with the drive energized.**
   Delta vs the box-off drive block confirms the 2B attribution **reverses**: if the box is the source of
   AE's 129/131 kHz pair, that pair must return when the box comes back on. Guards 2B against a one-way /
   drift reading.

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
   > **ELEVATED 2026-10-01: this is now THE pivotal block, not "optional, last."** 3b showed every
   > motor-turning block with the coupling IN measures the bearing (UL +869 %), so decoupling is the
   > **only** way to read drive EMI at all once the shaft turns — and it also **absorbs the sinus-filter
   > comparison** (blocks 3b/4 coupled cannot give it cleanly). Run the sweep at **sinus OFF and ON** so
   > this one block answers both *"does noise scale with rpm while decoupled"* (EMI vs vibration) **and**
   > *"what does the sinus filter buy."* **Kim's bench action: decouple the motor from the rig** — now the
   > critical path, ahead of block 4b.
   > **RESULT 5, sinus ON (decoupled — `20261001_113117` / `114015` / `114854` at 0 / 500 / 1500 rpm,
   > archived): the ticket's central question, ANSWERED.** Relative to the 0 rpm floor: 500 rpm → UL
   > +3.3 %, AE +67.6 %, SP +54.8 %; 1500 rpm → UL +1.9 %, AE +65.4 %, SP +54.7 %. **A STEP, NOT A RAMP**
   > — 500 and 1500 rpm are 0.1 % apart on SP. PWM noise proportional to output frequency would put 1500
   > well above 500; it does not. **So the drive's contribution is its output stage being ACTIVE, not the
   > frequency it runs at.** Decoupled, so vibration is excluded by construction — this turns 0035's
   > *coupled* inference (*"SP +43 % flat with speed"*, vibration argued away) into a **measurement**
   > (+55 % flat, decoupled, no vibration possible). Internal check: Kim read **8.40 Hz and 25.21 Hz** on
   > the drive display, so the two speeds were genuinely different yet produced the same noise. **UL
   > unaffected (+2–3 %)** — it does not pick up drive EMI; each channel its own path again.
   > **VERIFICATION CAVEAT (decoupled):** the tach mark is on the RIG side, so decoupled it reads 0 with a
   > frozen counter — a human reading the drive display is the ONLY valid speed verification, and the
   > Modbus readback **lies both directions** (reported `cmd=0.00 run=STOP` while the motor ran at
   > 25.21 Hz, as CLAUDE.md already records from 2026-08-19). Every 5-series note carries Kim's reading +
   > time. The drive's command/readback behaviour is split out to **ticket 0047**; moving the tach mark to
   > the **motor** side (to make decoupled runs self-verifying) is proposed there too.
   > **NEXT — the sinus-OFF twins:** same three speeds, filter OFF, deltas vs 5a/5b/5c give the sinus
   > filter's effect **decoupled** (the ticket's other main question). One wire move from Kim. Working
   > command sequence: 0 rpm needs no command, 8.40 Hz from stopped, then stop → 25.21 Hz.
   > **RESULT 5, sinus OFF (decoupled — `20261001_125027` / `125757` / `130453` at 0 / 500 / 1500 rpm,
   > archived): the sinus filter MAKES THE SENSOR NOISE WORSE, and on AE it is the WHOLE "drive EMI."**
   > Removing the filter cut **AE −41 %** (500 rpm 0.02395 → 0.01403; 1500 rpm 0.02362 → 0.01407) and
   > **SP −12 %** (0.1365 → 0.1206); UL ±0.5 %. AE without the filter reads 0.0140 running = **exactly its
   > floor** (0.0139–0.0143) — so the entire +68 % "drive EMI" on AE (RESULT 5 sinus ON) was **created by
   > the sinus filter**; without it AE cannot tell the drive is running. On SP the filter is about half
   > (+55 % over floor with it, +33 % without). **NULL CONTROL PASSES:** at 0 rpm (no drive output,
   > nothing to filter) the two configs agree to 2.7 % vs ~2 % scatter — so the at-speed differences are
   > the filter acting on the output, not its mere presence in the enclosure. That free control is why the
   > result is trustable, and the ticket's single coupled sinus block would never have produced it.
   > **⛔ DO NOT REMOVE THE SINUS FILTER TO CLEAN UP THE SENSORS.** It is not there for the sensors: it
   > limits dv/dt at the motor terminals and suppresses **bearing currents** — the electrical erosion that
   > pits bearing races. On a *bearing test rig* removing it would introduce electrical wear in the
   > specimen under test, contaminating the experiment slowly, invisibly and indistinguishably from real
   > mechanical degradation. A filter that *amplifies* noise points at its **installation**, not the
   > principle. (Deserves a hard line in CLAUDE.md.)
   > **5h-5j — filter ON, ground RESTORED (next; Kim found a missing ground between the sinus filter and
   > the VFD).** Against 5a-5c (filter ON, ground MISSING) that changes exactly one variable, giving a
   > three-way split of the filter's **principle** from its **installation**:
   >
   >     5a-5c   filter ON,  ground MISSING   (done)
   >     5e-5g   filter OFF                   (done)
   >     5h-5j   filter ON,  ground RESTORED  (next, profiles written)
   >
   > **Pre-registered prediction (written into the 5h-5j profiles before measuring):** if the ground was
   > the cause, filter+ground lands at or below the no-filter level — AE falls from ~0.0239 toward its
   > ~0.0140 floor — **and the filter can stay** (what we want for bearing currents); if the ground is
   > irrelevant, filter+ground resembles the filter-without-ground series, the filter itself is the
   > problem, and the fix is shielding / cable routing.
   > **RESULT 5h-5j, filter ON + ground RESTORED (decoupled — `20261001_133652` / `134851` at 0 / 500 rpm,
   > archived): the prediction FAILED, in the OPPOSITE direction — restoring the ground made it markedly
   > WORSE.** At 500 rpm vs 5b (filter ON, ground MISSING): **AE +127.2 %, SP +75.1 %**, UL +1.4 %. AE
   > ordering against its 0.0140 floor: no filter 0.0140 (+0 %) < filter/no-ground 0.0240 (+71 %) <
   > **filter+ground 0.0544 (+288 %, worst).** Null control passes again (0 rpm all three agree). **Likely
   > a CLOSED GROUND LOOP:** the filter is already grounded elsewhere, so the restored strap closes a loop
   > — a textbook antenna / entry path for common-mode current from the drive into the sensors (partial
   > ground = half an antenna +71 %; closed loop tripled it, +288 %). **So the fix is NOT "restore the
   > missing ground."** The grounding **topology** is wrong and needs a deliberate single-point scheme, not
   > straps added or removed one at a time — the removed ground may well have been removed for a reason.
   > (1500 rpm + filter+ground unmeasured — the drive refused stop/new-freq while running; confirmation not
   > discovery, since 5a-5c already showed noise flat with speed. See ticket 0047.)
   > **RESULT 5k — reversibility (ground REMOVED again, decoupled 500 rpm, filter ON, `20261001_141121`,
   > archived): the ground attribution is CONFIRMED IN BOTH DIRECTIONS.** AE made and unmade: no-ground
   > 0.0240 → +ground 0.0544 (×2.27) → ground-removed-again **0.0267, within 11.5 % of the original.** So
   > the +288 % was NOT an artefact of the power-cycle / mode-reset that happened alongside 5h-5j — those
   > were not undone, and the effect **followed the ground.** Honest residual: AE +11.5 % (inside the
   > ~26 % run-to-run wander), SP +20.2 % (larger — plausibly cable positions shifted while working the
   > strap, which matters precisely because the coupling is common-mode, not signal-borne). Conclusion
   > unchanged and now bidirectionally earned → ticket 0048.

**6. (optional, last) heater relay as its own factor.** Repeat block 0's stationary floor but **toggle only
   the heater relay** (ch0) at fixed everything-else. Any step in the sensor channels on the toggle = the
   heater-relay coupling path (the second coupling 0035 flagged), isolated from the drive.

> **DATA NOTE (telem-stamp scan, Pi 2026-09-30):** the block 0 (`20260930_093141`) and 2A
> (`20260930_102402`) h5s carry **no `telem_*` per-sweep stamps** — they predate the `_telemetry_store`
> race fix and the dead-VFD Modbus timeouts lost the race. **Immaterial for 0046:** these are
> stationary / dead-drive / no-heat blocks with no operating point to record, and the waveform +
> `/metadata` + scaling attributes are complete — which is all the RMS/spectrum attribution uses. The
> config (PSU / sinus / motor) lives in the run notes, not in `telem_*`. Post-fix blocks (2B onward) are
> fully stamped. The full archive scan (only the five 2026-09-30 VFD-off runs affected; all four
> findings-critical runs fully stamped, no JSONL repair needed anywhere) is recorded in CLAUDE.md.

> **ACTUATION NOTE (Pi, 2026-10-01) — the runner cannot drive the VFD during a run; pre-start it.** One
> serial port, two consumers: the runner polls the Omron on `/dev/ttyUSB0` while a drive command needs the
> same port, and the write loses (270 `Could not exclusively lock port` errors in 3 min, shaft never
> moved). Worse, the runner sends RUN **once**, sets `vfd_started=True`, then writes frequency only — a
> frequency with no run command does nothing and it never retries (the rig's standing lesson: verify
> actuation against the tach, not a readback). **Workaround that worked for 3b:** start the drive from a
> short script **before** the run, then use a **passive** profile — the drive holds speed unprompted,
> nothing contends, and `telem_rpm_meas` still stamps the real speed every sweep. Stop + confirm (rpm 0
> **and** a frozen pulse count) after. Needs `02-03`/`00-05` on **communication** (5), not a pot. Deserves
> a line in CLAUDE.md.

## Analysis
Per channel (UL / AE / SP, and OE if run): **RMS + spectrum** for every block. The deltas that matter:
- **0→2A:** the switch-mode-vs-linear 24 V PSU contribution (result: null for the 1.06 MHz line).
- **2A→2B:** the heater/temp box's conducted EMI (result: halves AE's 129/131 kHz pair).
- **2B→3a:** the idle energized drive's electrical contribution (result: +55 % SP, before rotation).
- **3a→3b:** rotation — but **coupled, so drive-load EMI + vibration together, not separable here.**
- **3b→4 and the sinus row of the 2×2:** what the sinus filter buys.
- **block 5 (decoupled):** does noise track rpm *while decoupled* → **the one clean EMI-vs-vibration
  split**, per channel.
- **block 6:** heater-relay coupling, isolated.
Look in the spectrum for switch-mode / PWM switching frequencies and their harmonics, not just RMS.

> **RESOLVED — the 129/131 kHz "line" was never one phenomenon (narrow 126–135 kHz, 500 Hz bins, Pi
> 2026-10-01).** On **SP** every bin 126–135 kHz is flat (~2.4–2.5e-04 at blocks 0/2A/2B) and doubles
> *uniformly* to ~4.8e-04 when the drive is energized (3a) — so 3a's "+94 % at 129/131 kHz on SP" was
> **the broadband floor rising, not a line**; the ±1.5 kHz band could not tell. On **AE** the structure
> is real (bins 2.1–6.0e-04, peaks near 129.0 / 131.5 kHz) and switching the box off collapses the
> **whole region** to flat ~2.0e-04 — so **2B's AE attribution stands** (the box adds structure *and*
> broadband there). The two shared the analysis band, not a source.
> **METHOD RULE this cost us (keep it):** a band-integrated amplitude at a nominal frequency **cannot
> tell a line from broadband**, and a "strongest spectral lines" listing just picks the loudest random
> bin. **A line is real only if the same frequency repeats across channels AND across runs** — 1060.7 kHz
> does, SP's 129/131 kHz does not. Written into the 3a notes so nobody inherits the error from the
> archive.

> **1060.7 kHz — CLOSED as instrument-side (0b + three confirmations).** The line survived the linear-PSU
> swap (2A), a shorted SP probe tip (0b), and the drive being energized (3a: +2.4 %). It is made in the
> scope+probe chain, not on the rig, and **no rig-supply/box/drive work removes it** — characterise and
> subtract it as a constant floor under every block. The only open sub-question is scope-internal vs
> probe/cable pickup (a BNC-short "block 0c"), which matters **only if someone later wants to lower the
> floor**, not to attribute it.

## Conclusion (2026-10-01)
Every major question in the ladder is answered, each pinned to one source by one controlled step:
- **24 V switch-mode PSU:** null (2A) — not the 1.06 MHz line, not a measurable contributor.
- **Heater/temp box:** real structure on AE near 129/131 kHz, halves when it is off (2B).
- **1060.7 kHz:** instrument-side (scope+probe chain), three independent confirmations — characterise and
  subtract, not a rig fault (0b, 2A, 3a).
- **Drive EMI:** a **step** present whenever the output stage is active, **independent of rpm** (block 5,
  decoupled, 500 ≈ 1500 rpm) — 0035's inference turned into a measurement.
- **Sinus filter:** at speed it is the **largest** sensor-noise contributor and on AE the *entire* "drive
  EMI"; and the dominant term is its **installation**, not the component — a grounding **topology** fault
  (closed loop) that *amplifies* common-mode injection (+288 % AE with the strap closed).

**The finding that outranks the numbers:** the **sensor-cleanest** configuration (no filter) and the
**specimen-safest** configuration (filter, for bearing-current suppression) are currently **opposites**.
Running without the filter puts AE at its floor but risks dv/dt-driven **bearing-current erosion of the
specimen under test** — slow, invisible, indistinguishable from real mechanical degradation. This is **not
a measurement problem to optimise away; it is an EMC installation / grounding design question.** Do not let
anyone silently pick the quiet configuration. **Follow-up: a single-point grounding redesign of the
filter / VFD / sensor system — ticket 0048 (EMC, not characterisation).**

**Remaining ladder items are optional confirmations, not open questions:** 4b (heater box back on with the
drive energized — reversibility of 2B), 6 (heater-relay toggle), and the explicit {PSU}×{sinus} 2×2, which
2A and block 5 already answer in substance.

## Owner / test
- **Kim / hardware:** swap PSU (switch-mode ↔ linear 24 VDC), sinus filter in/out (**a quick wire-move**, confirmed Kim 2026-09-30 — so the {PSU}×{sinus} 2×2 is two fast swaps), decouple the motor,
  run manual mode. Record which configuration each block is.
- **Archive EVERY block run to Azure** (Kim, 2026-09-30): the uploader (h5 + sidecars + md5, 0013) to
  `eceherning` — **do NOT mark these `DO_NOT_ARCHIVE`**, each block is analysis-worthy characterization
  data. Encode the config (block #, PSU type, sinus on/off, motor state) in the run notes so every blob
  is self-describing.
- **Pi / dev:** the block profiles (or manual-mode drive + a stationary acquire), the RMS/spectrum
  analysis per channel per block, and the deltas above.
