---
id: 0010
title: config.json azure.default_container is a dead, misleading value
area: ops
role: dev
status: backlog
assignee: unassigned
branch:
pr:
---

## Goal
Remove the dead `azure.default_container` config field (or point it at the real container) so no
automation trusts a value that silently fails.

## Why
`config.json` → `azure.default_container` = `auherning3bearingtester`, which **does not exist** on
the account (ContainerNotFound). Every upload actually lands in `data`, which the dashboard
hard-codes in `react/src/hooks/useAzureUpload.js`. So the config field is dead and actively
misleading — any new automation that trusts it fails, silently, the moment it relies on it.
(Flagged by Pi-Claude after the 13 h run's verified upload to container `data`.)

## Fix (one of)
- **Point it at `data`** and make the config the single source, with the dashboard reading it; or
- **Remove the field** and treat the dashboard's hard-coded `data` as canonical (documented).

Either way: no config value that lies.

## Acceptance
- No config field names a non-existent container.
- Uploads land where the config/documentation says, and an automation reading the container name
  gets the real one.

## Owner / test
- **Dev:** reconcile config vs dashboard. **Test:** an upload + a config-read agree on the container.

## Evidence + widened scope (pi, 2026-08-26)

Re-confirmed on the live account: `auherning3bearingtester` returns **ContainerNotFound**. Still dead.

But the sharper problem surfaced when Frederik downloaded the wrong dataset. **Two containers are in live
use on account `csfbst001`, and nothing documents which is which:**

| container | written by | holds |
|---|---|---|
| `data` | the dashboard (hard-coded in `react/src/hooks/useAzureUpload.js`) | the older/ad-hoc uploads, incl. `scope_20260817_114548.h5`, `scope_20260818_135505.h5`, `scope_20260820_093823.h5` |
| `eceherning` | `py/tools/upload_to_azure.py` (the archive path) | the 13 h runs of record, under a `<run_id>/` prefix |

`scope_20260820_125647.h5` — the 13 h run of record — exists **only in `eceherning`**. Someone browsing
`data`, which is what the dashboard points at, will never find it and will find three plausible-looking
wrong files instead. That is exactly what happened.

So this ticket should not just remove or repoint a dead field. Add: **document the split** (one line in
CLAUDE.md — dashboard uploads land in `data`, archive uploads in `eceherning`, 13 h runs of record are in
`eceherning`), and decide whether the two should converge on one container.
