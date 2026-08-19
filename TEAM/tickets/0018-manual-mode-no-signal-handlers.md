---
id: 0018
title: Manual mode has no signal handlers — SIGTERM leaves an unreadable HDF5
area: acquisition
role: dev
status: open
assignee: pi-claude
branch: ticket/0018-manual-mode-no-signal-handlers
pr:
---

## What happens
`acquire_scope_data.py config.json` with no profile takes the manual path:

```python
# --- Manual mode (unchanged) ---
if not args.profile:
    acquire_loop(scope_cfg)
    return
```

Signal handlers are registered further down, in the auto path only. So in manual mode a SIGTERM
kills the process where it stands, the `with h5py.File(out_path, "w")` block never unwinds, and
the file is left without a valid object header:

```
OSError: Unable to synchronously open file (bad object header version number)
```

Reproduced on 2026-08-19: `timeout 240 python3 acquire_scope_data.py config.json` produced a
9.5 MB file that h5py cannot open at all. Not a partial read — nothing is recoverable.

## What is *not* affected, and why that matters for how urgent this is
**Profiled runs — every real test — are safe.** The auto path registers both SIGINT and SIGTERM,
and `api_server.py` escalates deliberately: SIGINT first, then SIGTERM, then SIGKILL, so the
dashboard's Stop button gives the writer a clean shutdown before anything harsher arrives. A
control run ending in SIGINT was verified readable the same day: 7 sweeps, 3 channels, correct
shapes.

Ctrl-C in manual mode is also safe — `KeyboardInterrupt` propagates out of the `with` block and
h5py closes the file on the way out. **Only a signal-based kill of manual mode loses data.**

So this is narrow. It is worth fixing anyway because the failure is silent and total: the file
looks like a normal HDF5 on disk, with a plausible size, and only fails when someone finally
tries to open it — possibly long after the scope session it recorded is gone.

## Fix
Register the same handlers before `acquire_loop()`, setting the loop's stop flag so the `with`
block exits normally. Manual mode has no runner and no heater, so nothing else needs unwinding.

## Verify
Start manual mode, `kill -TERM` it mid-sweep, and confirm `inspect_hdf5.py` opens the result and
reports the sweeps written up to that point.
