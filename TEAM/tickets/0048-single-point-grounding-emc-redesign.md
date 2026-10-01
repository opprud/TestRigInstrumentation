---
id: 0048
title: Single-point grounding / EMC redesign of the filter–VFD–sensor system — keep the sinus filter AND clean the sensor channels
area: hardware / EMC
role: hardware
status: backlog
depends_on: 0046
branch:
pr:
---

## Why this ticket exists
0046 characterised the sensor-channel noise and ended on a conflict it cannot resolve by measurement: the
**sensor-cleanest** configuration and the **specimen-safest** configuration are currently opposites. The
job here is to make them the **same** configuration — keep the sinus filter (it is required, see below)
and get the sensor channels back to their quiet floor — because the dominant noise term is the
**installation / grounding**, not the filter component itself. This is an EMC design task, not more
characterisation.

## The constraint that rules everything: the sinus filter stays
The filter is not there for the sensors. It limits **dv/dt** at the motor terminals and suppresses
**bearing currents** — the electrical erosion that pits bearing races. On a **bearing test rig**, running
without it risks introducing electrical wear in the specimen under test: slow, invisible, and
indistinguishable from real mechanical degradation. **Removing the filter to quieten the sensors is
prohibited** — it would silently contaminate every bearing-life measurement the rig exists to make. (This
belongs as a hard line in CLAUDE.md too.)

## ⛔ SAFETY GATE: is that strap protective earth, or a functional ground?
**Not established — and it must be before the "ground removed" state is left in place.** 0046 found that
removing the filter–VFD ground *reduces* sensor noise (closed-loop signature), so the quiet configuration
has the strap OFF. **But if that strap is protective earth (PE), removing it for noise is an electrical-
safety violation, not an optimisation** — it defeats the fault path that keeps exposed metal from going
live. Whether it is PE or a functional / screen ground has not been determined from the wiring.
- **Someone who can see what it physically connects must identify it** before the strap is left off.
- **If it is PE it stays on, full stop** — the noise is then solved elsewhere (single-point topology,
  shielding, cable routing), never by defeating protective earth.
- Until identified, the rig's present "ground removed" state is a **temporary test condition to be
  restored**, not a configuration to run in.

## What 0046 established (the evidence to design against)
Decoupled, motor at 500 rpm, AE floor ≈ 0.0140 (AE is the most affected channel):

    configuration            AE rms     vs floor
    no filter                0.0140      +0 %      <- cleanest, but specimen-UNSAFE
    filter, ground MISSING    0.0240     +71 %
    filter, ground RESTORED   0.0544    +288 %     <- worst

- Restoring the filter–VFD ground made it **markedly worse**, not better — the signature of a **closed
  ground loop** (the filter is already grounded elsewhere; the extra strap closes a loop, which is a
  textbook antenna / entry path for common-mode current from the drive into the sensor system).
- Null control passed at every step (0 rpm: all configs agree to ~2–3 %), so the effect is the filter/
  grounding acting on the drive's **output**, not its mere presence.
- The drive's own EMI is a **step** tied to the output stage being active, flat with rpm (0046 block 5).
- Each channel couples by its **own path** — UL is unaffected throughout; AE and SP carry it. A fix for
  one need not touch the others, and the metric to optimise is **AE at speed**.

## Hypothesis
The **grounding topology** is wrong, not a single missing/added strap. Adding or removing individual
straps moves between "half an antenna" (+71 %) and "closed loop" (+288 %); neither is the fix. It needs a
deliberate **single-point (star) grounding** scheme for the filter / VFD / sensor system, designed as a
whole. **Understand the existing topology before changing it** — the ground that had been removed may have
been removed deliberately.

## Candidate approach (to investigate + apply, measurement is the arbiter)
Standard VFD-EMC practice, to be confirmed against the rig's actual layout — not trial-and-error:
- **Single-point / star ground:** one reference node; avoid parallel ground paths between filter, VFD
  chassis, motor frame and the sensor system that can form loops.
- **Separate the sensor/signal ground reference from the power/drive ground**, bonded at one point only.
- **Shielded motor cable with the shield terminated 360° at both ends** (drive and motor), so common-mode
  returns on the shield rather than through the sensor grounds.
- Check filter placement and lead lengths (a sinus/dv-dt filter belongs close to the drive output with
  short leads).

## Acceptance test (ready-made from 0046)
Re-run the **decoupled** 5-series with the **filter ON** under the new grounding: 0 / 500 / 1500 rpm,
pre-start the drive + passive profile, human-verify speed (0047). **Target: AE at or near its 0.0140 floor
while running** — i.e. the filter installed so it does not inject — with UL/SP no worse. That restores
"filter on = sensor quiet = specimen safe" as one configuration.

## Owner / test
- **Kim / hardware + EMC:** map the existing grounding topology, design and implement the single-point
  scheme, cable shielding/termination. The judgement call on what the removed ground was for.
- **Pi / dev:** the decoupled before/after measurement against the AE-floor acceptance target; archive
  each grounding variant like a 0046 block so the change is self-documenting.
