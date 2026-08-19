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
