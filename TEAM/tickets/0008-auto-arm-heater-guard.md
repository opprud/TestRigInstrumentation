---
id: 0008
title: Auto-arm the heater guard on every run start
area: control
role: dev
status: review
assignee: pi-claude
depends_on: 0004, 0006
branch: ticket/0008-auto-arm-heater-guard
pr:
---

## Goal
Guarantee the oil heater is switched off when **any** run ends — with no manual per-run step.
Every run must auto-spawn the detached heater guard (tickets 0004 + 0006) at start.

## Why
Ticket 0004's guard is currently launched by hand for a specific run. A run started without arming
it — forgotten, or via a path that does not arm it — leaves the heater energised overnight, exactly
the failure 0004 exists to prevent. The guarantee must not depend on a human remembering.

## Design
Hook into the authoritative run-start path (`acquire_scope_data.py main()`, where the run folder is
created and the profile/duration are known — the same place the OE task starts). At run start, spawn
`py/heater_guard.py` **detached** so it outlives the run process:

```python
import subprocess, sys, os, time
def arm_heater_guard(run_dir, profile_cfg, shelly_cfg):
    if not shelly_cfg.get("heater_guard_enabled", True):
        return None
    dur_s    = float(profile_cfg.get("duration_minutes", 0)) * 60.0
    margin_s = max(45*60, 0.05*dur_s)                     # cover retries / overruns
    deadline = time.time() + dur_s + margin_s
    ch_id = int(shelly_cfg.get("heater_channel_id", 0))
    ch    = shelly_cfg.get("heater_channel_name", "heater")
    guard = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heater_guard.py")  # STABLE path, not /tmp
    log   = os.path.join(run_dir, "heater_guard.log")
    with open(log, "ab") as lf:
        p = subprocess.Popen(
            [sys.executable, guard, "--run", run_dir, "--deadline", str(deadline),
             "--channel-id", str(ch_id), "--channel", ch],
            stdout=lf, stderr=lf, stdin=subprocess.DEVNULL,
            start_new_session=True)                        # detach: survives the run process dying
    print(f"[heater-guard] armed pid={p.pid} deadline={deadline:.0f} log={log}", flush=True)
    return p.pid
```
Call it once, right after the run folder exists. Record the PID in the run log.

## Requirements
- **Detached** (`start_new_session=True`) — must survive the run process being killed (that is the point).
- **Stable script path** — resolve `heater_guard.py` relative to a fixed location under `py/`, never a
  `/tmp` worktree (the bug Pi-Claude hit: an overnight cleanup left the guard unable to switch).
- **One guard per run** (idempotent — don't double-arm).
- **Config-driven, default ON** — `shelly_config`: `heater_guard_enabled` (default true),
  `heater_channel_id`, `heater_channel_name`. A run must not silently start unguarded.
- Uses the fixed `heater_state()` (ticket 0006): null/absent output = UNKNOWN.

## Acceptance
- Start any run → a heater-guard process auto-spawns; PID + log recorded.
- Kill the run process → the guard keeps running and still switches the heater off on run_end / stale / deadline.
- Clean finish / crash / overrun → heater off + verified (as 0004 already does).
- Disable flag works (default on).

## Owner / test
- **Dev:** wire the auto-arm into the run-start path. **Tester (Pi):** a short run → confirm the guard
  auto-armed, survives a killed run process, and switches off at the end.

## Implementation (Pi, 2026-08-19)

`_arm_heater_guard()` in `acquire_scope_data.py`, called immediately after the run folder is
created — the same place the run folder is announced. Manual mode (`no profile`) returns before
that point and drives neither motor nor temperature, so it is deliberately not armed.

Config lives in `shelly_config.json`: `heater_guard_enabled` (default **true**),
`heater_channel_id`, `heater_channel_name`, plus `heater_guard_stale_min` — added because the
acceptance test needed a shorter staleness window than 15 min, and it is worth having anyway.

### Verified against the rig
| Criterion | Result |
|---|---|
| Auto-spawns on run start | ✅ pid + log recorded in the run folder |
| Survives the run being killed | ✅ `kill -9` the run; guard alive with **ppid 1** |
| Switches off on a dead run | ✅ triggered after 2.6 min, `VERIFIED: channel 0 is OFF` |
| Disable flag | ✅ logs `run is UNGUARDED` and returns None |

### Two defects found while testing, both fixed here
1. **`subprocess` and `sys` were not imported** in `acquire_scope_data.py`. The arming would
   have raised `NameError` on *every* run — caught by its own error handling, so each run would
   have started unguarded while printing a warning nobody was watching for.
2. **A run dying in its first seconds never creates a telemetry file**, and the staleness check
   was predicated on that file existing. The only remaining trigger was the deadline — for a
   13 h run, nearly 14 hours of energised heater. The guard now also fires on "no telemetry file
   after `stale_min` and no acquisition process". Verified in 11 s with a 3 s window.

### Limitation
The heater was already off during testing (last night's run switched it off at 03:08), so the
switch-off exercised the full command and verification path but not an actual state change. The
real state change was proven on the 13 h run — see ticket 0005.
