---
id: 0030
title: Audit and refresh stale reference docs (data-layout docs predate the OE / tick_start / new-HDF5 changes)
area: docs
role: dev
status: backlog
assignee: unassigned
depends_on:
branch:
pr:
---

## Problem
Several reference docs predate the 2026-08 changes (OE samples, `tick_start`, `near_sweep`, the new
HDF5 layout, the calibrated tacho) and now describe a data model that no longer matches the files.

## Stale / suspect (last touched)
- **`py/TELEMETRY_STRUCTURE.md`, `py/METADATA_README.md` (2025-10)** — describe the HDF5 / telemetry
  layout, which has changed the most: `/oe_samples`, `tick_start`, `near_sweep`, per-dataset attrs.
- `py/SESSION_SUMMARY.md`, `py/NOTEBOOK_GUIDE.md` (2025-10), `README_Integration.md`,
  `DATA_MANAGEMENT.md`, root `readme.md` — likely drifted.
- `docs/rs510_vfd_driver.md` (2025-11) — should carry the **02-03 source-select** and the
  **summing-pot** findings (currently only in CLAUDE.md known-issues).

## Fresh (leave alone)
CLAUDE.md, `docs/Prerun_Checklist.md`, `docs/OE_sensor.md`, `TEAM/CHARTER.md`.

## Scope
- Reconcile the data-layout docs against a current file (e.g. `scope_20260820_125647.h5`):
  `/metadata`, `/sweeps`, `/oe_samples`, the tick axis.
- Update each doc, or mark it **superseded** with a pointer to the current source of truth.
- Fold the VFD 02-03 / summing-pot notes into `rs510_vfd_driver.md`.

## Acceptance
- Every doc in `docs/` and `py/*.md` is either current or explicitly marked superseded with a pointer.
