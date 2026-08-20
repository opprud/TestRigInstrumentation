---
id: 0024
title: OE captures succeed only 2 of 6 cycles — the sensor sleeps and we stop looking too soon
area: ble
role: dev
status: open
assignee: pi-claude
branch: ticket/0024-oe-capture-reliability
depends_on: 0001, 0021
pr:
---

## What the short test found
Run `20260820_091646`, 15 min, motor turning 500→1200 rpm, OE at a 3-minute cadence.

**The important criterion passed:** 71 sweeps, contiguous numbering, **0 skipped**, while OE
captures of ~149,000 points ran concurrently with scope digitising. A mic capture never delayed a
sweep — which was the whole point of handing captures to the scope thread over a queue and
draining it non-blocking.

**But only 2 of 6 OE cycles produced data:**

```
capture 1  OK                       -> oe_000  (near_sweep=1,  488 rpm)
capture 2  OK                       -> oe_001  (near_sweep=16, 889 rpm)
FAILED (1)  RuntimeError('device returned no sample data')
FAILED (2)  ConnectionError('not advertising within 20s')
FAILED (3)  ConnectionError('not advertising within 20s')
FAILED (4)  ConnectionError('not advertising within 20s')
```

Both successes came first, then the device went off the air and stayed off for the rest of the
run.

## Likely cause
The device's own `pdm_mic_config.json` carries **`sleep_time: 30`**, and the vendor's
`run_sampler.py` logs *"Sending to sleep for 30 seconds"* — so the unit sleeps of its own accord
after activity, and **a sleeping device does not advertise**. `oe_sampler.py` uses
`SCAN_TIMEOUT_S = 20.0`, so a cycle that starts during a sleep window gives up almost immediately
and is counted as a failure.

This is a guess at the mechanism, not a measurement: what is measured is that the device stopped
advertising after two captures and did not come back within any subsequent 20 s window.

## What to change
1. **Raise `SCAN_TIMEOUT_S`** well past the sleep period so a cycle waits the device out rather
   than declaring failure — 60–90 s, with the sample timeout unchanged.
2. **Retry inside a cycle** rather than losing the whole interval: two or three scan attempts
   before counting a failure.
3. **Log the gap**, so an unattended run leaves evidence of how long the device was unreachable
   rather than just a failure count.

Deliberately *not* proposed: shortening the cadence to compensate. More attempts against a
sleeping device is not more data, and each attempt occupies the radio.

## Do not fix by sending sleep ourselves
`oe_sampler.py` never calls `oe.sleep()`, and that is correct — see 0001. The vendor's sampler
sends the device to sleep after every session; we do not, precisely so it stays reachable.
Whatever sleep the device is doing here is its own.

## Pass criteria for the retest
Another 15-minute run at the same cadence with **at least 5 of 6 cycles** producing data, and
sweeps still at zero skips. Only then is a 13 h run worth starting.
