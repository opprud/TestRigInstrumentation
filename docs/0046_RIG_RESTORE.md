# Restoring the rig after ticket 0046

**The rig is NOT in a state to run a bearing test.** Ticket 0046 deliberately took it apart
electrically and mechanically, one variable at a time, and every one of those changes is still in
place. This list exists so none of them is forgotten — several are invisible from the dashboard and
would silently corrupt a run rather than stop it.

Written 2026-10-01 at the end of the 0046 block series.

## Must be restored before any bearing run

- [ ] **Re-couple the motor to the rig.** It was decoupled for block 5 so that noise scaling with rpm
      could be attributed to the drive rather than to vibration. A decoupled rig turns no bearing:
      the test would run its whole schedule and record a stationary specimen.
- [ ] **Move the 24 V sensor supply back from the linear lab supply to the rig's own supply** — or
      decide deliberately to keep the linear one. Block 2A measured the switch-mode supply's
      contribution as **null** (inside run-to-run scatter), so there is no noise reason to keep the
      lab supply, and a bench instrument is not a permanent part of the rig.
- [ ] **Settle the sinus filter and its ground, and this one needs a decision, not a default.**
      Current state: **filter FITTED, filter-VFD ground REMOVED.** Measured at 500 rpm, decoupled:

      | configuration | drive | AE | vs AE's 0.0140 floor |
      |---|---|---|---|
      | filter, no ground (5a) | **at rest** | 0.01428 | at the floor |
      | filter + ground (5h) | **at rest** | 0.01412 | at the floor |
      | no filter (5f) | live | 0.01402 | at the floor |
      | filter, no ground (5b) | live | 0.02398 | +71 % |
      | filter + ground (5i) | live | **0.05440** | **+288 %** |
      | filter, no ground again (5k) | live | 0.02668 | +91 % |

      **Read the two halves together: the ground costs nothing at rest and a factor two when the
      drive's output stage is switching**, and 5b → 5i → 5k is reversible (up with the strap, back
      down without it). Two caveats, both recorded 2026-10-02 against the full 23-block dataset in
      `docs/0046_noise_floor.csv`:
      - **Kim read 0.00 on the drive display during 5i**, so that block may not share its neighbours'
        motor state. This pulls conservative rather than the other way: a motor running *less* in 5i
        cannot explain twice the noise. The reading stands, but it deserves one repeat at a
        **verified** rpm before a grounding scheme is designed on it.
      - **The filter alone does nothing at rest** (5e → 5a, 1.02x). It shapes what the drive emits;
        it is not itself a source.

      **The strap is a FUNCTIONAL ground, not protective earth (Kim, 2026-10-02).** That settles the
      safety question: leaving it off is a legitimate engineering choice rather than a hazard. One
      thing still blocks treating it as the answer:
      1. **The filter protects the specimen.** It limits dv/dt at the motor terminals and reduces
         bearing currents — electrical erosion that pits bearing races. On a bearing test rig,
         running without it risks eroding the very bearing being characterised, slowly and
         invisibly, in a way indistinguishable from real mechanical degradation.

      So the sensor-cleanest and specimen-safest configurations are **opposites**, and the real fix is
      a deliberate single-point grounding scheme — not choosing the quietest of three poor options.
- [ ] **Check drive parameter 02-03 is on communication.** It does **not** survive a power cycle on
      this drive: after the VFD was re-powered on 2026-10-01, seven consecutive start commands were
      refused while plain register reads worked fine, until the mode was set again.
      `docs/Prerun_Checklist.md` §3 says to check it before a run; after any power cycle it is not
      optional.
- [ ] **Check the pot is at its bottom stop** (Prerun_Checklist §3). Unchanged by this work, but it
      is the other setting that lets a run look healthy while the shaft does something else.
- [ ] **Verify the tach against commanded Hz** once re-coupled — `59.83 x Hz - 11.7`. With the motor
      decoupled the tach reads 0 with a frozen counter, so it has been unusable throughout 0046 and
      its health has not been checked since.

## Already back to normal

- Heater/temp control box: **ON** (restored 2026-10-01).
- Heater relay: left **OFF** by the run's heater guard.
- External tachometer (the one that produced the 1060.7 kHz line): **OFF**, and it should stay off,
  or at least be recorded in the run notes when it is on.

## What cannot be fixed by restoring anything

**The 1060.7 kHz line is in the instrument chain**, not the rig. It survived the PSU swap, a shorted
probe tip, and the drive being energized. No work on the rig's supplies, boxes, cabling or grounding
will remove it. Splitting scope-internal from probe/cable pickup needs the probe off and a BNC short
at the input — a separate small test with its own baseline, since removing the probe changes the 10x
attenuation and therefore comparability.

## And record what else is in the room

Block 0's spec says "no extra bench gear powered near the sensor cabling". That is a negative
instruction nobody can verify afterwards, which is why an external tachometer went unnoticed as the
dominant 1.06 MHz source. **Record the room's state positively** in the run notes for any run that is
meant to be a reference.
