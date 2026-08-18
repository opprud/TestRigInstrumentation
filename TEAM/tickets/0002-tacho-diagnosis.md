---
id: 0002
title: Diagnose tacho measured-vs-commanded speed gap (slip vs artifact)
area: control
role: dev
status: diagnosed
assignee: pi-claude
branch:
pr:
---

## Goal
Decide whether the persistent gap between **measured** and **commanded/target** shaft speed is real induction-motor **slip** (sensor reading true speed → OK) or a **tacho artifact** (pulses-per-rev / dropped pulses → fix needed). Frederik is blocked on whether to trust the speed channel.

## Background
- Motor = 2-pole induction (KLEE T712-2). Light-load ≈ **59.5 rpm/Hz**; synchronous = 60 rpm/Hz for 2-pole. Under load the shaft slips a few % below synchronous (nameplate ~5.3 % at full load: 2840 rpm @ 50 Hz).
- We run **open-loop**: the drive follows commanded Hz; the tacho (IFM OGT500 → RP2040) is a monitoring read-out and is the suspect — not the shaft speed.

## Method (from the latest run's telemetry on the Pi)
1. Per speed step, compute `measured_rpm / commanded_rpm` (with `commanded_rpm = commanded_Hz × 59.5`).
2. Characterise the gap: **direction**, **magnitude**, **load-dependence**, **stability**.
3. Read what firmware is actually **flashed** on the RP2040 (`INFO` → `fw=`) and its `PULSES_PER_REV` / `SETPPR`.

## VERDICT (2026-08-18, Pi-Claude) — tacho artifact, NOT slip

**The tacho is not measuring shaft speed.**

- **Decisive evidence:** in a run this morning the drive never started (STOP / 0.0 Hz, shaft stationary — confirmed in drive telemetry + audibly), yet the tacho reported **234.41 rpm for all 41 samples**. A stationary shaft can't produce a real reading → the sensor is picking up something that isn't rotation.
- **Systematic error (13 h run):** `measured = 1.0011 × true + 582 rpm`, max deviation ~5 rpm over 100–2300 rpm, then **hard saturation at 2963 rpm** (`true` = commanded reconstructed from drive Hz × 59.5).
- **Interpretation:** slope ≈ 1 → **scale / pulses-per-rev is correct** (not extra reflections per rev, not miscalibration). The fault is a **constant additive offset of 582 rpm ≈ +9.7 Hz of extra pulses**, independent of shaft speed → a **second pulse source** (electrical pickup / stationary reflection / ambient light).
- **Shaft speed is fine:** open-loop drive freq = target, recorded freq matches target/59.5 at every step; true speed = 59.5 × Hz, ±2–3 % slip. The tacho mismatch does **not** mean the shaft runs at the wrong speed → use commanded-derived speed for analysis.
- **Caveat:** shaft speed can't be independently confirmed right now (the only independent sensor is the faulty one). A hand tachometer or phone strobe at a couple of set points would settle it in minutes.

## Fix (follow-up → ticket 0003 when ready)
Eliminate the spurious ~9.7 Hz pulse source: check electrical pickup (shielding/grounding of the OGT500 signal line), a stationary reflection in the sensor's field, or stray ambient light; and/or add debounce + validation in the RP2040 tach ISR plus a tach timeout (it currently holds the last value). Re-verify against an independent hand-tach / phone-strobe reading. Also investigate the saturation ceiling at 2963 rpm.
