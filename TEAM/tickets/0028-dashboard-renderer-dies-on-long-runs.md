---
id: 0028
title: The dashboard tab dies during long runs — 5.8 GB of unread log text polled into React state
area: dashboard
role: dev
status: backlog
assignee: unassigned
depends_on:
branch:
pr:
---

## Symptom
During the 13 h run of 2026-08-20 the dashboard at `localhost:3000` stopped responding twice and
had to be reloaded (Kim: *"error code 5"*, Chromium's page for a killed renderer). It did **not**
happen during the 13 h run of 2026-08-18.

**Nothing was actually down.** Measured while the symptom was live: vite answered `200` in 3 ms on
three consecutive requests, `/config/Keratech22.json` served correctly, the API answered `200`, and
the acquisition process, `api_server` and vite had all run continuously since start. System memory
was 13 GB free with swap untouched, and there were no OOM events in the kernel log.

The giveaway was process uptime: **one Chromium renderer had been up 2 h 20 min while every other
Chromium process had been up 6 h 31 min.** A single tab's renderer had been killed and respawned.

## Cause
`react/src/Dashboard.jsx:292` polls `/api/run/status` **every 500 ms** while a run is in progress
and stores the entire response with `setRunStatus(s)`.

That response is **62 KB**, of which **58 KB is `stdout_tail`** — 200 lines of run output. Grepping
`react/src/` for consumers of `stdout_tail` returns **nothing**: no component renders it. It is
fetched, parsed, and stored twice a second for the length of the run, and never read.

Over 13 hours:

| | |
|---|---|
| requests | ~95,000 |
| JSON parsed | **~5.8 GB** |
| React state updates | ~95,000, each allocating a fresh 200-element string array |
| use made of the log lines | none |

## Why it is new
The code has not changed: the only commit touching `react/src` since 2026-08-18 is a one-line
profile path in `ConfigSelector.jsx`. What changed is exposure — the tab was left open across a
full 13 h run on a Pi that had also been running Chromium for six hours. The defect has presumably
always been there; this run held it open long enough to matter.

## Fix (any one of these is enough; the first two together are the honest fix)
1. **Do not ship what nobody reads.** Trim `stdout_tail` out of the status response, or gate it
   behind a query parameter so only a view that actually displays the log asks for it. 62 KB -> ~1 KB.
2. **Drop the poll to 2 s.** The payload is a progress counter — step, sweep, elapsed. At 500 ms it
   buys nothing on a 13 h run and costs 4x the traffic and state churn.
3. Strip `stdout_tail` client-side before `setRunStatus` if the endpoint must keep returning it for
   other callers.

## Do not do this while a run is live
Editing `Dashboard.jsx` triggers a vite HMR reload of the operator's page. Harmless in itself, but
the charter is explicit about not pushing disruptive changes while the Pi is running a live test,
and the dashboard is the operator's only window into it.

## Note for the meantime
Reloading the page fully restores it, and **the run is unaffected** — the acquisition process is a
child of `api_server`, not of the browser. The one real hazard in that chain is separate: if
`api_server` dies, its unread stdout pipe fills and the acquisition process blocks in `write()`,
staying alive while doing nothing. That is watched for during this run by heartbeat on the
telemetry and HDF5 file mtimes rather than by a liveness check, which would report such a run as
healthy for thirteen hours.
