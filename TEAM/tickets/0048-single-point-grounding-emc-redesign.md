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

> **⚠ PREMISE SUPPORTED BUT NEEDS ONE VERIFIED-RPM REPEAT (revised twice, 2026-10-02).** This ticket was
> opened on the "ground-ON is worse when running" result (ground off/on/off = +71 %/+288 %/+91 %,
> reversible across 5b→5i→5k). An earlier banner here retracted it entirely because **5i** is the block
> Kim read as 0.00 (rpm unverified) — **that over-retracted it.** The doubt is *conservative* (less
> rotation cannot create more noise; ground-ON *stationary*, 5h, is only 0.0141, so 5i's 0.0544 required
> the output stage active). So the direction holds: **ground-ON is worse once the drive output switches**;
> only the magnitude is uncertain. **Do one clean running ground-on/off pair at a verified rpm before
> designing any single-point scheme** — that is the gating measurement, not a redesign. Also from 0046:
> the floor is only **1.5–2× over the scope's quantization limit**, so if a quieter *floor* is the goal
> (vs removing the ground's running penalty), the lever is **ADC resolution / voltage range**, not
> shielding.

## Why this ticket exists
0046 characterised the sensor-channel noise and ended on a conflict it cannot resolve by measurement: the
**sensor-cleanest** configuration and the **specimen-safest** configuration are currently opposites. The
job here is to make them the **same** configuration — keep the sinus filter (it is required, see below)
and get the sensor channels back to their quiet floor — because the dominant noise term is the
**installation / grounding**, not the filter component itself. This is an EMC design task, not more
characterisation.

## The sinus filter: what it is actually for (corrected 2026-10-05, Kim / review)
The filter limits **dv/dt** at the motor terminals and suppresses **bearing currents** — the dv/dt-driven
EDM discharges that pit bearing races. **But that protection is for the MOTOR's own bearings**, which sit in
the VFD's electrical path (capacitive stator↔housing → shaft voltage → discharge through the motor
bearings). **The test specimen bearing — the one the sensor package measures — is mechanically downstream
and electrically away from the VFD, so it does NOT see those bearing currents.** Removing the filter would
therefore **not** electrically erode the specimen. (An earlier version of this ticket claimed the filter
protects the *specimen* — that was wrong; corrected on review feedback.) The filter still matters for the
**motor's** longevity and for how much VFD noise couples into the sensors.

**So the filter is a development aid, not a specimen-safety hard constraint.** The end goal is a
data-sampling / processing pipeline **robust to unfiltered VFD noise** — field machines vary (many run
without a VFD) and the specimen is electrically unaffected either way — but that robustness is **easier to
reach from a clean baseline**, which is what the filter (and removing external noise sources) buys during
development. **Keep the filter ON for now** for clean dev data and motor health; running without it later as
a robustness test is a legitimate step, **not prohibited and not a specimen hazard.**

> **Worth confirming (measurable):** that the test shaft is electrically **isolated** from the motor
> (insulated coupling / separate ground), so the specimen's electrical immunity is *known, not assumed* —
> fits the motor-isolation experiment below.

## ✅ SAFETY GATE CLEARED: it is a FUNCTIONAL ground, not protective earth (Kim, 2026-10-02)
0046 found that removing the filter–VFD ground *reduces* sensor noise, so the quiet configuration has the
strap OFF — which would be an electrical-safety violation if the strap were protective earth (PE). **Kim
has identified it: it is a FUNCTIONAL / screen ground, not PE.** So leaving it off is a legitimate
engineering choice, not a hazard, and **no safety constraint forces the configuration either way.**
`docs/0046_RIG_RESTORE.md` updated accordingly. What remains is the engineering trade-off below.

## Interim operating configuration (re-corrected 2026-10-02)
The running numbers are **reversible** and support leaving the ground off: ground-off +71 %/+91 % (5b/5k)
vs ground-on +288 % (5i); stationary the two are equal. (A mid-day note here briefly swung this to "ground
RESTORED" after an over-retraction of the +288 % block — that swing is itself reverted; see the premise
banner.)

**Decision (architect, 2026-10-02): run bearing tests with the filter ON and the functional ground OFF**
— it is the quieter *running* configuration, and leaving a **functional** (non-PE) ground off is a
legitimate choice. The filter stays for **clean development data and the motor's own bearing health** (not
for the specimen — see the corrected filter section above); elevated sensor noise is a known, subtractable
offset. Running "no filter" is a legitimate **robustness test** later, not a specimen hazard — just keep it
ON while the data pipeline is being developed. Hold this as **provisional until the verified-rpm ground repeat**
confirms the magnitude. Separately, the floor itself is quantization-limited (1.5–2×), so the deepest
"quieter floor" lever is **ADC resolution**, independent of the ground's running penalty.

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

## Experiments to try (Kim + review feedback, 2026-10-05)
From the review (Eskild Herskind, CeramicSpeed) and Kim, on the counterintuitive "the sinus filter makes
the sensor noise worse" result. **Mechanism identified:** the VFD couples **capacitively between the stator
windings and the motor housing** (common-mode); the motor sits **close to the bearings and in direct
electrical contact with the base plate**, so that common-mode path runs straight into the rig / sensors
(and is also the classic bearing-current path). Candidates, each tested **one change at a time against the
decoupled-AE acceptance metric (below), at a verified rpm** (0047):

- **Ferrite / common-mode chokes** on the cables (drive output, and/or the sensor cables). Low risk, often
  the single most effective CM fix — **try this first.**
- **Split the shielding by cable SEGMENT.** The **drive→filter** cable carries raw PWM (high CM) and wants
  shield + 360° ground at both ends. The **filter→motor** cable carries the near-sinusoidal, low-dv/dt
  output — **Kim's hypothesis (2026-10-05): drop the shield AND the ground at both ends on the filter→motor
  segment**, because post-filter there is little CM to contain, and that shield/ground is a prime suspect
  for *being* the coupling path. Consistent with the **+288 % AE** measured when the filter–VFD ground was
  restored (a closed loop). **Test it; do not assume** — the +288 % still owes one verified-rpm confirm.
- **Break the motor→base-plate electrical path** if feasible (isolate the motor mount, or give the
  common-mode current a dedicated return), since that direct contact near the bearings is the suspected
  injection point.
- **Single-point / star grounding** (candidate approach above) — but "ground on both sides" already
  measured **worse** once, so measure each configuration, never strap in blind.

Ceiling (0046 §3.2): the quiet floor is quantization-limited (~1.5–2×), so the gain shows at the *running*
signal (where AE doubled), not all the way down to the floor.

**~1 kHz peak on UL — RESOLVED, and NOT an EMC target (Pi desk-analysis, 2026-10-05).** 5 Hz-bin
periodograms on the archived blocks refute the VFD-carrier hypothesis: the peak is **absent** in all three
drive-dead blocks *and* in B3a (drive **energized, motor STILL**, +7 % = nothing) — **it requires ROTATION,
not an energized drive.** It is a **sharp structural resonance, 0.91–1.00 kHz, Q ≈ 70–100**: independent of
the sinus filter (present with the filter out, B5f), not a rotation harmonic (speed triples 500→1500 rpm,
frequency moves 1.5 %), amplitude **falls** with speed (2766× at 500 rpm → 772× at 1500), and it shifts
~7 % (985–1000 Hz decoupled → 910–925 Hz coupled in the 13 h run) — a switch frequency does not move when
you decouple a shaft. It reaches UL **even with the motor mechanically decoupled from the bearing**, so the
path is the **bench structure, not the bearing**. **→ Mechanical, not EMC: tracked under ticket 0040 (UL
resonance), out of 0048's scope.** Changing the carrier will not touch it. Cheapest next step: **move the UL
probe at 500 rpm** — if the frequency follows the probe mount, the resonance is in the mount; if it stays,
it is in the bench. (A *second* resonance at ~2.4 kHz dominates ≥ 1800 rpm — uncharacterized, also 0040.)

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
