---
id: 0013
title: Azure archive policy — upload only valid, analysis-worthy tests to the real container
area: ops
role: dev
status: backlog
assignee: unassigned
depends_on: 0010, 0011
branch:
pr:
---

## Goal
Send only **valid, analysis-worthy test runs** to the shared Azure archive container that other team
members analyse — and **not** the small stability/rehearsal runs. Use the real container (from Kim's
`eceherning_connection.json`), with its secret kept out of git.

## Why
Kim provided the real destination (account `csfbst001`, a container-scoped **Admin** SAS). Going
forward only runs others can benefit from analysing should be archived there; the small runs we do
just to confirm stability must not clutter the archive. Ties into 0010 (old container value was
dead) and 0011 (get the uploader into the repo, no secrets).

## Open decisions (Kim to confirm)
- **Container name:** the connection string gives the account + a container-scoped SAS but not the
  container *name*. Filename implies **`eceherning`** — confirm the exact name.
- **Keep/skip gate:** how is a run marked "valid, archive it" vs "small stability run, skip"?
  - (recommended) explicit **opt-in flag** — archive only if flagged; default skip. A valid *short*
    test still gets kept if flagged; stability runs never leak in.
  - or a duration/size threshold (risk: a valid short run is under it).
  - or a manual post-run "promote this run to the archive" action.

## Design
- **Secret handling:** the SAS / connection string lives in a **gitignored** config (e.g.
  `py/azure_connection.json` or an env var); only the **container name** goes in committed config.
  The uploader reads both. **Never commit the SAS** — it is Admin-scoped and valid until 2126;
  treat as highly sensitive and regenerate if exposed.
- The upload path (0011's `azure_upload_guard.py`) checks the keep/skip gate before uploading and
  targets the configured container.

## Acceptance
- A flagged valid run uploads to the real container; a stability run does not.
- No secret in git; container name in committed config; uploader reads the SAS from a gitignored file.

## Owner / test
- **Dev:** wire container + gate + secret handling. **Test:** a flagged run and an unflagged run →
  only the flagged one lands in the archive.
