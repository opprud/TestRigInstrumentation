---
id: 0047
title: RS510 drive — command sequence unknown and Modbus readback lies; decoupled runs have no machine verification
area: drive / control
role: dev
status: backlog
depends_on: 0046
branch:
pr:
---

## Why this is its own ticket
Split out of 0046 (Pi/windows, 2026-10-01). Characterising the drive's **noise** is done; understanding
how the drive **accepts commands and reports state** is a separate problem, and it must not be debugged
mid-experiment with an operator standing at the bench reading the display. 0046's block 5 cost most of a
morning to a lying register and a command sequence nobody can model. Capture it here, investigate it
deliberately.

## What is empirically established
- **One command sequence worked every time it was used:** `start_forward` alone from a **stopped** drive,
  and `stop()` then `start_forward` to change speed. It drove 0 / 8.40 Hz / 25.21 Hz reliably on
  2026-10-01.
- **It is a pattern, not a rule:** 50.42 Hz broke even that sequence. There is no working model of why.

## What is NOT established (do not build on these — each was contradicted by the next attempt)
- a minimum-frequency limit,
- `set_frequency` before `start_forward` breaking the command,
- stop-required-before-change as a hard rule.
All three are marked NOT ESTABLISHED in the 2026-10-01 run notes.

## The readback lies — in both directions
- The drive reported `cmd=0.00 ud=0.00 run=STOP` while Kim read **25.21 Hz** on the display and could
  hear the motor. **Every verification loop built on the readback is worthless.**
- This is not new: **CLAUDE.md already records the same from 2026-08-19** (drive showed `cmd=0.0` while
  the shaft turned at 2985 rpm; stale display minutes after a run). The standing rule — *verify actuation
  against the tach, never a readback* — is correct and this ticket exists because, decoupled, the tach
  cannot do it (below).

## Decoupled work has no machine verification today
- With the motor **decoupled**, the tach mark is on the **RIG** side, so it reads `rpm=0.00` with a frozen
  pulse count — the sensor is fine, nothing turns in front of it. So **a human reading the drive display
  is the only valid speed verification for any decoupled run.** It cost a run twice on 2026-10-01.

## Proposed work
1. **Move the tach pickup/mark to the MOTOR side of the coupling.** Makes decoupled runs self-verifying
   (start, speed and stop) and stamps `telem_rpm_meas` on every sweep instead of a hand-recorded note.
   **Re-verify the §3 calibration (`rpm = 59.83 × Hz − 11.7`) after moving** — the constant was derived
   with the mark on the rig side and must be re-checked, not assumed. Kim's hardware call.
2. **Find a command model that holds across the full range**, including what breaks at 50.42 Hz — on the
   bench, instrumented, not mid-experiment. Candidate factors to test cleanly: accel/decel state, a
   busy/fault status bit, the run-command-once-then-frequency-only path the runner uses.
3. **Fix the runner's actuation path** (noted in 0046's ACTUATION NOTE): it sends RUN once, sets
   `vfd_started=True`, then writes frequency only and never retries, and it loses the shared serial port
   to the Omron poll (270 `Could not exclusively lock port` errors). Until then, **pre-start the drive
   from a short script + passive profile** is the standing workaround.

## Update 2026-10-01 (second decoupled session) — both recommendations now twice-earned
- **The source-select mode does NOT survive a power cycle.** After Kim re-powered the VFD to refit the
  sinus filter, **seven consecutive start commands were refused** (display 0.00) while plain register reads
  worked fine; re-setting the source mode and the next command succeeded first try. **`Prerun_Checklist`
  §3 says "check 02-03 before a run" — it must say re-check (and re-set) the source after *every power
  cycle*, because it falls back.** (This is the `00-05` Main Frequency Source / `00-02` Main Run Source
  parameter — the docs miscall it "02-03"; see 0046.)
- **Readback lied again, the other direction:** `stop()` and a new frequency were both refused while the
  motor demonstrably ran at 8.40 Hz, the register reporting `STOP cmd=0.00 ud=0.00` the whole time.
- Net: **the command is unreliable in both directions and must be retried until a human confirms it** — and
  decoupled, only a human reading the display can confirm it. Both recommendations below are now
  **twice-earned in a single day**; treat them as do-before-the-next-decoupled-run, not "proposed."

## Owner / test
- **Pi / dev:** the command-model investigation, the runner actuation fix.
- **Kim / hardware:** the tach-mark move (+ re-cal), and reading the display during any decoupled run
  until the mark is moved.
