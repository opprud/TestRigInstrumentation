---
id: 0006
title: heater_state() must treat a missing/null Shelly output as UNKNOWN, not off
area: control
role: dev
status: done
assignee: pi-claude
branch: ticket/0006-heater-state-unknown
pr:
depends_on: 0004
---

## Goal
Close the one path where the heater guard could claim success it has not proved.

## The defect (found by the architect in PR #3 review)
`heater_state()` read the channel as:

```python
return not bool(c.get("output"))
```

If the API returns the channel **without** `output`, or with `output: null`,
`bool(None)` is `False`, so the guard reads **"heater is off"**, logs
`VERIFIED: OFF` and exits — without the heater ever having been switched.

That is the same failure class as everything else found on 2026-08-18: an unknown
state treated as a success. Here it defeats the guard's entire purpose, because the
one scenario it exists to prevent is a heater left energised on an unattended rig.

## Fix
Only a real boolean is a state. Anything else — absent, null, or an unexpected type —
returns `None` (UNKNOWN) and is logged, so the guard keeps retrying and, if it still
cannot confirm, says so loudly instead of exiting quietly.

## Verified
Six cases against a stubbed API response:

| API `output` | result | meaning |
|---|---|---|
| `True` | `False` | on |
| `False` | `True` | off |
| `None` | `None` | UNKNOWN ✔ (was wrongly "off") |
| absent | `None` | UNKNOWN ✔ (was wrongly "off") |
| `"off"` (string) | `None` | UNKNOWN ✔ |
| channel not in list | `None` | UNKNOWN |

## Note on tonight's run
The guard armed for run `20260818_135505` (PID 23082) is running the **old** code, and
per the architect it is not being restarted. Its risky path only executes when the
trigger fires at ~03:08. Rather than restart it, a **second** guard running this fixed
code was armed alongside it — additive, no gap in coverage, and both simply send the
same OFF command. Outcome goes on ticket 0005.
