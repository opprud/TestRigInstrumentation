---
id: 0002
title: Diagnose tacho measured-vs-commanded speed gap (slip vs artifact)
area: control
role: dev
status: backlog
assignee: unassigned
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
2. Characterise the gap:
   - **direction** — is measured *above* or *below* commanded?
   - **magnitude** — a few %, or a large factor?
   - **load-dependence** — does the gap grow with load (torque/force channel)?
   - **stability** — does measured hold a value or jump while commanded changes?
3. Read what firmware is actually **flashed** on the RP2040 (`INFO` → `fw=`) and its `PULSES_PER_REV` / `SETPPR`. **Prime suspect** for a constant-ratio gap is a PPR mismatch: the source was renamed to v1.2.0 (hardcodes PPR=1), but the board may still run older firmware with a different PPR.

## Verdict → action
- measured **modestly below** commanded, load-dependent (≤ ~5 %) → **slip**; sensor OK, use as-is.
- **constant ratio** ≈2× / ≈½× → **PPR mismatch**; set the correct pulses-per-rev (or reflash the intended firmware).
- measured **above** commanded → over-counting (noise / multiple pulses per rev).
- measured **frozen/erratic** vs changing commanded → dropped tacho pulses + firmware holds last value (no timeout) → needs a tach timeout + signal check.

## Deliverable
Per-step ratio table + verdict (slip vs artifact) + recommended fix, reported to the architect. This is the definitive answer to Frederik's "is the sensor working well?".
