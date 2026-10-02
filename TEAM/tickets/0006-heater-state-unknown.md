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

## 2026-10-01 — the WRITE ack is unreliable too, not just the status read (0046 block 6)
Block 6 (`20261001_145326`) toggled the heater relay twice. The Shelly's command acknowledgement was
unreliable in **both** directions: the first `--off` returned *"Command sent but no confirmation received
within 5 s"* while the `--on` returned a clean confirmation — and `--status` still reports `???` per
channel. **Both relay states were only known because Kim physically verified them** (confirmed not-pulled
during the first OFF, heard the click at ON). So beyond the status-read problem this ticket already
covers, **`shelly_control.py --off heater` returning cleanly is not proof the heater is off** — and that
is the exact command the **heater guard (0004 / 0008) relies on** to make the rig safe. The guard can
believe it has shut the heater off when it has not, with no read-back that would reveal it. A real fix
needs a **verified** off (measured current, or a confirmed relay state), not a command return code.
Evidence: `eceherning/20261001_145326/RELAY_LOG.txt`.
