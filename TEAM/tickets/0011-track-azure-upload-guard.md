---
id: 0011
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
- **Secrets:** do NOT commit the Azure SAS / connection string. Keep it in a gitignored config/env
  and make the tracked script read it from there. (`config.json` currently holds a cleartext SAS —
  fold that into this cleanup.)

## Acceptance
- `azure_upload_guard.py` is in git; no run-critical script depends on an untracked file.
- No secret committed; a fresh clone has everything the run/upload path needs (minus secrets).

## Owner / test
- **Dev:** add + review the scripts, verify no secrets leak in. **Test:** fresh clone runs the
  upload path once secrets are supplied.
