---
id: 0026
title: Hold the OE BLE link open between captures so the sensor never sleeps
area: ble
role: dev
status: done
assignee: pi-claude
branch: ticket/0026-oe-persistent-ble-link
depends_on: 0001, 0024
pr:
---

## Why
The sensor sleeps of its own accord when idle — its `pdm_mic_config.json` carries `sleep_time: 30`
— and **a sleeping device does not advertise**. That cost 4 of 6 cycles on 2026-08-20 (ticket
0024), which was fixed by widening the scan window to 45 s and retrying, i.e. by *waiting the
sleep out*. Staying connected removes the window instead.

Kim's call 2026-08-20: the unit runs on **fixed supply, not a battery**, so the connection count
no longer buys anything. That was the only argument for disconnecting between captures.

## Change (`py/oe_sampler.py`)
The cycle was scan → connect → sample → **disconnect**, every time. It is now scan → connect once,
then sample on the held session, with the link released only when the run ends.

- `_connect()` — scan + open a session (the 0024 scan retry logic, unchanged).
- `_ensure_connected()` — reuse the held session if it is still up, else replace it. Returns
  whether *this* call established it, which decides whether a failure is worth retrying.
- `_capture()` — the sample itself, no longer responsible for tearing down what it did not open.
- `_teardown()` — release and forget, tolerant of a disconnect that fails.
- `run()` releases the link in a `finally`, so the sensor is not left in a session nobody is on
  the other end of — including when the task is cancelled.

**A held link that has quietly died costs seconds, not a capture.** If a sample fails on a reused
session, the session is thrown away, re-established and the capture retried **once**, within the
same cycle. A *fresh* session that fails is not retried — it was just proved dead, and retrying it
only delays the run's own failure policy from logging it. Reconnects are counted and reported when
the task stops, so an unattended run leaves evidence of how often the link dropped.

Relying on `connected` is sound rather than optimistic: `oe_device` registers a
`disconnected_callback` that clears the flag, so an unexpected drop is visible at the next cycle
instead of surfacing as a 120 s sample timeout.

## Escape hatch
`config.json → oe.keep_connected` (default `true`). Setting it `false` restores the old
per-capture session exactly. It is a config knob and not a code change on purpose: whether a held
link survives 13 hours is a property of *the sensor*, not of this file, and if it turns out not to,
the rig should be revertible without a deploy.

## Tests
`py/test_oe_sampler.py`, 8 tests, no BLE and no sensor — the `ble` adapter is replaced with a fake
harness, so what is under test is this file's own decisions:

- a held link is reused across captures (one connect, one scan, three samples);
- `keep_connected: false` still opens and closes one session per capture;
- a dead held link costs one reconnect and still produces the capture;
- a brand-new session that fails is *not* retried;
- an empty reply is an error, not an empty capture;
- a silent sensor spends every scan attempt before being reported as not advertising;
- the link is released when the run stops;
- a failing capture never takes the run with it.

`test_oe_hdf5.py` (14 tests) still passes.

## Not yet verified on hardware — this is the whole risk
**The premise is untested: that a connected device does not sleep.** It is inferred from the
vendor's config and from the fact that a sleeping unit stops advertising, not measured. Two
outcomes would change the design:

1. The device sleeps anyway while connected — then this buys nothing and 0024's wait-it-out
   remains the real fix.
2. The link does not survive hours — then the reconnect path carries the run, and its cost per
   drop needs measuring against the 3-minute cadence.

**Pass criteria:** a 15-minute run at the 3-minute cadence with **all** cycles yielding data, zero
sweeps skipped, and `[oe] stopped` reporting **0 reconnects**. Then a longer soak before the 13 h
run, since a 15-minute test never meets the failure this ticket is really about.

---
## Closed 2026-08-30 (windows)
Persistent BLE link implemented in py/oe_sampler.py (justified by the fixed supply, Kim 2026-08-20). Validated on run 20260829_145507: 152 captures, 7 transient failures, 5 reconnects over 13 h. Done.
