---
id: 0013
title: Heater guard — retry the MQTT status query before calling the state unknown
area: control
role: dev
status: review
assignee: pi-claude
branch: ticket/0013-heater-guard-status-retry
depends_on: 0004, 0006, 0008
pr:
---

## Problem
`heater_state()` queried `shelly_control.py --status` **once**. That CLI only listens for a few
seconds and prints `???` when the device does not publish inside its window — which happens
roughly half the time. A single `???` was therefore treated as UNKNOWN, and with the API server
down (its own retry loop's fallback path) the guard could never confirm a switch-off it had in
fact performed.

Observed 2026-08-19 on the run `20260819_102659`: the guard fired correctly on `run_end`, the off
command reported `✓ [0] Heater: OFF`, and the heater really was off — but the guard kept retrying
because its verification query returned `???`. A manual retry got `OFF 0.0W 0mA` on the second
attempt.

## Fix
Query up to three times, 5 s apart, before returning UNKNOWN. Any definite answer wins
immediately, so the normal case costs nothing.

## Related finding — worth its own ticket
**`shelly_control.py` hardcodes `client_id="shelly_ctrl"`.** Two concurrent invocations therefore
connect to the broker with the same client id and disconnect each other, which is what produced
most of the `???` responses here: the still-running guard was polling while a second query ran.
The guard's own retry loop makes this self-inflicted. Suggest deriving the client id per process
(e.g. append the pid).

## Verified
With the stale guard stopped and no competing MQTT client: `heater_state(0)` returns a definite
answer, and `heater_state(1)` correctly returns UNKNOWN for a channel the API reports without an
`output` value — the ticket 0006 behaviour still holds.
