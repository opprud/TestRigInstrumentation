---
id: 0004
title: Heater safety guard — switch the oil heater off when a run ends, however it ends
area: control
role: dev
status: done
assignee: pi-claude
branch: ticket/0004-heater-guard
pr:
---

## Goal
Guarantee the oil heater is switched off when a rig run finishes — including when
the run **crashes, is killed, or overruns** — without depending on a Claude session,
the dashboard, or a human being awake.

## Why
A 13 h run finishes at ~03:00. The heater is on Shelly channel 0 and is energised
for the whole run. If the acquisition process dies at 01:00, nothing switches it
off: the API server does not own the schedule, and a monitoring session may be
closed. That leaves a heater powered overnight on an unattended rig.

This is the same class of failure as the two found on 2026-08-18 (a stationary
motor and a failed scope setup, both silent): the system is *sure* everything is
fine because nothing raised an error.

## Implementation — `py/heater_guard.py`
Detached watchdog (`nohup`), independent of the API server and of any agent session.
Fires on whichever comes first:

| Trigger | Case covered |
|---|---|
| `run_end` in the run's telemetry JSONL | clean finish |
| telemetry silent past `--stale-min` (default 15) | crashed / killed run |
| absolute `--deadline` passes | overrun backstop |

Switching off is safe in all three: the run is finished, dead, or past its planned end.

```bash
nohup python3 heater_guard.py --run <run_dir> --deadline <epoch> \
    --stale-min 15 --channel-id 0 --channel heater >> heater_guard.log 2>&1 &
```

**Command path vs verification path.** The off command goes through
`shelly_control.py` (MQTT, direct to the broker), so it works with the backend down.
Verification reads the **API's** `/api/shelly/status`, which keeps a persistent MQTT
subscription and a cached state. `shelly_control.py --status` was found to print
`???` when the device does not publish inside its short listen window — the guard
treats that as **UNKNOWN, never as "off"**, and keeps retrying (12 attempts with
backoff) rather than reporting success it cannot prove. If it still cannot confirm,
it says so loudly in the log instead of exiting quietly.

## Verified (2026-08-18, against the live rig)
- `heater_state(0)` correctly read the heater as **on** during the live run, and the
  spare channel as **off** — so the read path distinguishes states.
- `run_end` detection: false before, true after, and tolerant of a corrupt JSON line.
- The MQTT off-command path was exercised safely on spare channel 1 (already off, so
  no physical change): the command is published; the CLI's own confirmation window is
  what times out, which is exactly why verification goes through the API.
- **Not** exercised: an actual heater switch-off. That happens for real at the end of
  the run now in progress (`20260818_135505`), which is where the guard proves itself.

## Live
Armed 2026-08-18 14:04 for run `20260818_135505`, PID 23082, backstop deadline
2026-08-19T03:53:06, logging to `py/heater_guard.log`.

## Follow-ups (raise as new tickets if wanted)
- The guard is started by hand. It could be launched automatically by `run_start`
  so every run is covered without anyone remembering.
- `shelly_control.py --status` / `--off` cannot confirm within their 5 s window —
  worth fixing at the source rather than working around it here.
