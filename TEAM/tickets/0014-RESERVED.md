---
id: 0014
title: RESERVED — secret/credential backstop (SAS out of config.json + branch-independent ignore)
area: infra
role: dev
status: reserved
assignee: windows
branch:
pr:
---

## Why this number is held
Reserved on 2026-08-19 by the architect for the pending **secret/credential backstop** work:

1. Move the Azure SAS out of `py/config.json` (it is in cleartext, has `rwdlactf` including
   delete, expires 2126, and has been in the history of a **public** repo since 2026-04-20).
2. A **branch-independent** ignore for credential files. The `.gitignore` rule that covers
   `**/*_connection.json` only protects branches that have it; `py/eceherning_connection.json`
   showed up as untracked on a branch that predated the rule. A `.git/info/exclude` entry was
   added locally as a stop-gap, but that is per-clone and travels with nobody.

## Why it is a stub rather than an empty slot
Pi-Claude and the architect independently issued 0012 and 0013 for different work on the same
day. A held number with nothing in its place is just an invitation to the same collision, so
unused numbers keep a `RESERVED` or `WITHDRAWN` file. See the numbering rule in ticket 0009.

Replace this file when the work starts. Do not renumber around it.
