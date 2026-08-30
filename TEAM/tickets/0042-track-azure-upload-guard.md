---
id: 0042
title: Track py/azure_upload_guard.py in the repo — it lives only on the SD card
area: ops
role: dev
status: backlog
assignee: unassigned
branch:
pr:
---

## Goal
Get `py/azure_upload_guard.py` (and any other run-critical scripts that exist only on the Pi's SD
card) into git, so a card failure or reflash cannot lose them.

## Why
The Azure uploader that ran the verified 37.75 GB upload after the 13 h run is **untracked** — it
lives only on the SD card. If the card dies or is re-imaged, the uploader is gone and the post-run
data path silently breaks. Version control is the backstop. (Flagged by Pi-Claude, 2026-08-19.)

## Scope
- Add `py/azure_upload_guard.py` to the repo (review it on the way in).
- Sweep for other untracked-but-run-critical scripts on the Pi (`git status --porcelain` in the run
  tree; anything the run/upload path depends on) and track them too.
- **Secrets:** the tracked script reads its credential from the existing config/env, the same way
  `upload_to_azure.py` already does — no new hardcoded secret. NOTE: the cleartext SAS in
  `config.json` is **explicitly accepted, not a cleanup target** (Kim, 2026-08-30: those login
  credentials are not sensitive). So this ticket is purely about getting the untracked scripts into
  git, not about scrubbing anything.

## Acceptance
- `azure_upload_guard.py` is in git; no run-critical script depends on an untracked file.
- A fresh clone has everything the run/upload path needs (credentials still supplied via env/config, as today).

## Owner / test
- **Dev:** add + review the scripts, verify no secrets leak in. **Test:** fresh clone runs the
  upload path once secrets are supplied.

---
## Note (windows, 2026-08-30)
Renumbered from 0011 to 0042 to clear an id collision with the azure-uploader ticket (both were 0011). Still open backlog: `azure_upload_guard.py` is confirmed untracked as of 2026-08-30.
