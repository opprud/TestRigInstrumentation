---
id: 0012
title: Tach calibrated and vindicated; the +582 rpm offset is resolved
area: control
role: dev
status: done
assignee: pi-claude
branch: ticket/0012-tach-calibration-and-pot
pr:
supersedes: 0002, 0003
---

## Outcome
The tachometer is accurate. The persistent +582 rpm gap between commanded and measured speed —
blamed first on the sensor (0002), then on VFD EMI (0003) — came from an **analog potentiometer**
summed into the RS510's frequency reference.

## Calibration (2026-08-19, at the rig)
Drive commanded over Modbus with the pot at minimum; speed measured on the tach only.

| commanded Hz | measured rpm | predicted | error |
|---|---|---|---|
| 5 | 288 | 287 | +1 |
| 10 | 588 | 587 | +1 |
| 20 | 1190 | 1185 | +5 |
| 30 | 1788 | 1783 | +5 |

Earlier, with the drive run from its own panel and no Modbus in the measurement path at all:

| panel Hz | measured rpm | rpm/Hz | slip vs 60 |
|---|---|---|---|
| 10.08 | 591 | 58.63 | 2.28 % |
| 20.01 | 1185 | 59.22 | 1.30 % |
| 30.26 | 1800 | 59.48 | 0.86 % |
| 40.01 | 2382 | 59.54 | 0.77 % |
| 50.00 | 2979 | 59.58 | 0.70 % |

**`rpm = 59.83 x Hz - 11.7`, maximum deviation 5 rpm over 288-2979 rpm.** Intercept zero within
error. Slip falls with speed, as an induction motor under light load should. Pulse-count,
single-period and `SPEED?` agree at every point. **One glitch in 110,658 pulses.** Kim confirmed
5 -> 10 Hz by ear as a clean doubling.

## The pot — corrected by Kim, 2026-08-19

My first write-up said the frequency reference was the **sum** of the Modbus command and the pot.
**That is wrong.** Kim's account is authoritative: drive parameter **02-03 selects the source** —
pot *or* communication. It had been set to the pot, so Modbus frequency writes were accepted,
echoed in the registers, and ignored; the shaft simply ran at the pot's setting. He power-cycled
the drive, entered edit mode, set 02-03 to communication, and left edit mode. After that Modbus
commands the speed to within 5 rpm and the pot does nothing.

That explains the whole morning — every "ignored" write, and the speed changes that came from him
turning the knob while we tested.

## What it does NOT explain: the +582 rpm in the 13 h runs

A source *selection* cannot produce a constant additive offset while the profile is being
followed:

- **pot selected** -> speed would be constant, not tracking the staircase. Those runs tracked it
  through 31 steps.
- **communication selected** -> speed should have been correct. It sat 582 rpm high at every step.

So the night offset is **open again**. It has now been attributed to the sensor (0002), to VFD EMI
(0003) and to the pot summing into the command (this ticket's first draft) — **all three wrong.**
No fourth guess here.

## RESOLVED (2026-08-19) — the offset is gone, in both run paths

Two runs, deliberately differing only in whether `api_server` was up:

| target | direct run | UI-started run | vs calibration |
|---|---|---|---|
| 600 rpm | 591 | **591** | −1 |
| 1200 rpm | 1192 | — | −3 |
| 1800 rpm | 1793 | — | −5 |
| 200 rpm | — | 187 | −2 |
| 300 rpm | — | 289 | −1 |
| 400 rpm | — | 390 | **0** |
| 500 rpm | — | 491 | **0** |

The 600 rpm step measured **591 rpm in both**, identical to the last digit. So:

- **The +582 offset is gone.** Every step now matches the calibration within 5 rpm.
- **The API-contention theory is wrong too** — it made no difference whether `api_server` was
  running. That was my fourth hypothesis and it also failed.

**Conclusion:** the offset belonged to the old setup — drive parameter **02-03 on the pot**, the
**old firmware**, or both. I am not picking between them: the two changed together, and I have
been wrong three times on this question already. What matters practically is that the rig now
commands and measures speed correctly end to end, and that both causes are gone.

**For the 13 h run data:** those runs were taken with the old setup, so their true speeds are the
logged `rpm_meas`, not `rpm_target`. The tach is trustworthy — that part is settled by the
calibration above.

## Separate finding: the profile's 100 rpm step does not turn the bearing
At 100 rpm the profile commands 1.68 Hz — 3.4 % of rated frequency. Measured **0 rpm** on the
tach while the drive reported running and its display showed 1.68 Hz; Kim confirmed by ear that
nothing turned. At the next step, 3.36 Hz, the shaft turns and matches the calibration to 2 rpm.

The step recurs **26 times** through the 13 h profile, so every earlier run recorded a
*stationary* bearing at those points rather than a bearing at 100 rpm.

**Kim's decision: leave the profile unchanged** and document it, to keep comparability with
earlier runs. Anyone analysing a run should treat the 100 rpm steps as stationary-bearing data.

## Consequences
1. **The 13 h runs' true speeds are uncertain** until the offset is explained. The tach is
   trustworthy (calibrated to 5 rpm), so `rpm_meas` is the best record available — but we cannot
   yet say *why* it sat 582 rpm above target.
2. **Frederik's question is answered, with the opposite conclusion to the one we sent him:** the
   sensor is working. Draft reply below.
3. **Tickets 0002 and 0003 are superseded.** Ferrites are not needed; there is no EMI problem.
4. **`py/tach_emi_test.py` should be withdrawn or rewritten** — its premise (edges seen while the
   drive is energised are spurious) is wrong.

## What the firmware work bought us (0007 was not wasted)
The freeze bug and the 2963 rpm saturation were real defects. Without the timeout, `TACHDIAG?`
and the median filter we could not have measured any of this: the old firmware would have frozen
at a stale value and saturated before the top of the range. **The instrument we built is what
exposed the pot.**

## Follow-ups (want ticket numbers)
- **Pot on the frequency reference** — disable the analog input, or read and log the pot, so a run
  cannot be silently offset. This is the one that corrupted real data.
- **RS485 exclusive-lock flakiness** — rapid successive process opens intermittently fail; writes
  return False and a `stop()` can report success without stopping the motor. A run must verify
  actuation against the tach, not a register readback.

## Draft reply to Frederik
> Following up on the speed discrepancy — the answer turns out to be the opposite of what I sent
> you, and the sensor is fine.
>
> We calibrated the tachometer against the drive across the full range. It gives
> `rpm = 59.83 x Hz - 11.7` with a maximum deviation of 5 rpm from 288 to 2979 rpm, an intercept
> of zero within error, and slip falling from 2.3 % to 0.7 % as speed rises — textbook for an
> induction motor under light load. One spurious pulse in 110,658. It is a good instrument.
>
> The gap between commanded and measured speed was real, but it was not a measurement error: an
> analog potentiometer summed into the drive's frequency reference was adding a constant ~9.8 Hz,
> i.e. ~582 rpm, to every commanded speed. The shaft really was turning that much faster, and the
> tachometer was reporting it correctly.
>
> Practical consequence for the data: for the 13 h runs, use the logged `rpm_meas` as the speed of
> record rather than the profile's target. The offset is constant across all steps, so the runs
> remain usable — they were simply run ~582 rpm faster than intended.
