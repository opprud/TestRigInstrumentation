---
id: 0008
title: Auto-arm the heater guard on every run start
area: control
role: dev
status: backlog
assignee: unassigned
depends_on: 0004, 0006
branch:
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
