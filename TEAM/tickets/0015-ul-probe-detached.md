---
id: 0015
title: UL probe detached for OE sensor mounting — mark the affected runs
area: ops
role: tester
status: review
assignee: pi-claude
branch: ticket/0015-ul-probe-detached
pr:
---

## Situation
The ultrasound probe was unscrewed on 2026-08-19 to make room for mounting the BearingBrain OE
BLE sensor. A mechanical change is needed before both can be fitted. Until then the rig runs
**without UL**.

## Why this needs marking rather than remembering
CHAN1 (alias `UL`) still produces a perfectly normal-looking group in every HDF5: 500,000 points,
the same scaling attributes, the same size. Nothing in the file says the probe was disconnected.
Six months from now nobody can tell those runs apart from real ones by inspection.

This is the same failure class as everything else found on 2026-08-17/19 — data that looks valid.
The difference is that here we know in advance, so it costs nothing to record it.

## What was done
The note travels **with the data**, not only in documentation:

- `py/config.json` -> `test_parameters.ul_probe_status = "DETACHED since 2026-08-19"` plus a full
  explanation in `test_parameters.notes`. `acquire_scope_data.py` writes `test_parameters` into
  `/metadata/test_parameters`, so **every HDF5 written in this period carries the warning inside
  it**.
- `py/config.json` -> the `UL` channel entry gets an inline `[DETACHED …]` note.
- `react/public/config/KaretTest_Oil1.json` -> the same text appended to the profile description.
- `CLAUDE.md` -> first entry under Known issues.

## Deliberately NOT done
**CHAN1 was not disabled.** Dropping it would change the HDF5 structure and make these runs
awkward to compare with earlier ones. Keeping the channel and marking it costs a third of the file
size in useless data, which is the cheaper trade.

## To undo when the probe is refitted
Remove all four notes together — `config.json` (`ul_probe_status`, `notes`, the `UL` channel
note), the profile description, and the `CLAUDE.md` entry. A stale warning is worse than none.
