---
id: 0027
title: Keratech22.json carried April scope settings that would clip UL 4x
area: control
role: dev
status: review
assignee: pi-claude
branch: ticket/0027-keratech22-scope-settings
depends_on:
pr:
---

## What was wrong
`react/public/config/Keratech22.json` had not been touched since 2026-04-20 and carried
`UL: volt_range 2.0`, `AE: 0.2`, `timebase_range 0.02`, 250 k points, `acq_type HRES`. No `SP`
channel at all, though every run records one.

**Those numbers would clip.** With the acoustic-emission probe fitted, UL is measured at **8.5 V
peak-to-peak** (run `20260818_135505`, and 6.8 V again in `20260820_112759`). A 2.0 V full range is
four times too small for that signal; AE at 0.2 V is worse.

## Why it looked correct
Because a run *did* happen under the name "Keratech 22" and went fine — but **it was not this
file**. The two 13 h profiles have their `name` fields crossed against their filenames:

| file | `name` inside |
|---|---|
| `KaretTest_Oil1.json` | **"Keratech 22"** |
| `Keratech22.json` | **"KaretTest Oil 1"** |

The 13 h run of 2026-08-18 logged `profile_name: "Keratech 22"`, so it ran from
**`KaretTest_Oil1.json`**, and its sweeps confirm it: UL at 16.0, AE at 4.0, timebase 0.2, 500 k
points per channel. This file was never exercised against the current sensors. Anyone reading the
run log and then opening the like-named file would have got settings the run never used.

## Change
`scope_channels` and `acquisition` replaced with what the 2026-08-18 run **measurably used**, taken
from that run's HDF5 rather than copied on trust — which is also what `KaretTest_Oil1.json` holds:
UL 16.0, AE 4.0, SP 8.0, timebase 0.2, `scope_points: "MAX"`, `acq_points: 1000000`,
`interval_sec: 12`, `NORM`. `SP` added. A `scope_settings_note` records why, in the file, so the old
values are not restored by someone who finds them in git history and assumes they were dropped by
mistake.

The 1561 rpm setpoints and 27 temperature setpoints are untouched.

> `acq_points: 1000000` reads as more than the 500 k the run shows per channel — it is not a
> mismatch. Memory is shared across active channels, so 1 M requested with 3 channels lands at
> ~500 k each, exactly what the 18/8 run recorded.

## Left alone deliberately: the crossed names
Renaming would change what the dashboard lists and what future telemetry files are called, and it
would make every existing run's `profile_name` ambiguous against the new names rather than the old.
That is a judgement call for Kim and the architect, not a side effect of a settings fix. **Flagged,
not fixed.**

## Verification
The settings this file now carries are the ones just verified end to end on hardware in run
`20260820_112759`: UL tracks the staircase (0.119 rms at 490 rpm -> 0.529 at 1192 -> 0.139 back at
490), AE tracks in miniature, SP sits flat as a slip ring should.

---

## Resolved: the crossed names, Kim's call 2026-08-20

Not left alone after all — Kim asked for it fixed, and chose to retire the duplicate rather than
swap the `name` fields, so that **every telemetry file ever written keeps meaning what it says**.

| before | after |
|---|---|
| `KaretTest_Oil1.json`, `name: "Keratech 22"`, 793 min, **the file that actually runs** | **`Keratech22.json`** — filename, `name`, and every existing run's `profile_name` now agree |
| `Keratech22.json`, `name: "KaretTest Oil 1"`, 832 min, untouched since April, never run | **`KaretTest_Oil1_superseded_20260420.json`**, `name: "KaretTest Oil 1 (SUPERSEDED 2026-04-20 - do not run)"` |

Swapping the `name` fields instead would have made future runs of the live profile log as
"KaretTest Oil 1" while the 13 h runs of 18/8 and 19/8 say "Keratech 22" — the same test under two
names in the data, which is worse than a filename nobody sees.

**The dashboard was the third crossed copy.** `react/src/components/ConfigSelector.jsx` hardcoded
`{ path: '/config/KaretTest_Oil1.json', name: 'KaretTest Oil 1' }`, so the operator picked
"KaretTest Oil 1" and the telemetry came out as "Keratech 22". That entry now reads
`{ path: '/config/Keratech22.json', name: 'Keratech 22' }` — what you click is what you get.

Also updated to follow the file: `py/tools/unmark_ul.py` (the architect's tool targets it by path),
`Rehearsal_15min.json`'s description, `CLAUDE.md`, and ticket 0025's plateau reference.

The retired file keeps the corrected scope settings from this ticket. Belt and braces: it is marked
"do not run", but if someone runs it anyway it will no longer clip.
