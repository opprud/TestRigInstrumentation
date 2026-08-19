---
id: 0012
title: Reverse-engineer and document the RP2040 board schematic (esp. the tacho input interface)
area: hardware
role: hardware
status: backlog
assignee: kim
depends_on:
branch:
pr:
---

## Goal
Produce a schematic of how the RP2040 microprocessor board is wired — reverse-engineered from the
physical board — and commit it to git, so the hardware is documented and not only in the build.

## Why
There is no schematic or wiring diagram anywhere in the repo (confirmed 2026-08-19) — only a pin
table in `firmware/RP2040_README.md` (Tach = GPIO 0, HX711 DOUT = GPIO 4, SCK = GPIO 2). The actual
analog interface between the OGT500's **24 V PNP** output and the **3.3 V** GPIO 0 (level shift,
possible optocoupler, termination, filtering) is undocumented.

This directly **blocks ticket 0003 (tacho EMI fix):** we cannot decide pull-up vs pull-down for the
PNP sensor, or where to place the EMI mitigations (ferrite / stronger termination / RC), without
knowing the input circuit. It is also the same class of risk as the untracked uploader (0011) —
critical knowledge living only in the physical build and in someone's head.

## Scope — trace from the board
- **Power:** USB 5 V → 3.3 V rail, decoupling.
- **RP2040 (Seeed XIAO):** module and its relevant pins.
- **HX711 load cell:** DOUT (GPIO 4), SCK (GPIO 2), supply, load-cell wiring.
- **Tacho input (the EMI-critical part):** how the OGT500 **24 V PNP** output reaches **GPIO 0** —
  level shift / optocoupler / divider, the termination (pull-up or pull-down + value), any existing
  R/C filtering, connectors. This is the part 0003 needs.
- Confirm pin assignments against the firmware: `TACH_PIN=0` with `INPUT_PULLUP`, `HX711_DOUT=4`,
  `HX711_SCK=2`.

## Deliverable
- A schematic (hand-drawn photo, KiCad, or a clear diagram) **committed to git** (`docs/` or
  `firmware/`), plus a short description.
- Enough detail to answer: **pull-up vs pull-down** for the PNP sensor, **where the EMI mitigations
  go**, and how to rebuild the board.

## Owner
- **Kim** reverse-engineers the board at the bench (his hardware task). Pi-Claude can cross-check pin
  assignments against the firmware and help draft the committed schematic/description once traced.
