---
id: 0041
title: Switchable 3.3 VDC supply for the OE sensor on a spare Shelly channel, so Claude Pi can power-cycle it to recover a wedged sensor
area: instrumentation / reliability
role: hardware
status: backlog
depends_on: 0001, 0019, 0026
branch:
pr:
---

## Problem this solves
When the OE BLE sensor wedges (stops advertising / stops answering on the UART characteristic), there
is **no way to recover it without walking to the rig and pressing the button**. Ticket 0019 established
why: the protocol has no reset primitive, and even if it did the command would have to travel through
the very application layer that has stopped. The sensor sits on a **fixed supply** (not USB, not the
Shelly), so today a hard reset is a physical trip — and a wedged OE sensor blocks every run that needs it.

## The fix (Kim, 2026-08-30)
Give the OE sensor its **own 3.3 VDC supply, fed through a spare channel of the Shelly Pro 4PM** we
already control over MQTT — **Kim proposes Shelly channel 2**. Then a wedged sensor is recovered by
**power-cycling that channel**, which Claude Pi can do himself, over the same broker that already drives
the heater guard and the Pi's own channel-3 cycle. No trip to the rig.

This is the hardware answer to 0019: no *soft* reset exists, so give it a *hard* one.

## The one hard constraint: >= 30 s off-time
The OE sensor holds a **super-capacitor**. On power-down it must **discharge fully or the device does
not actually reboot** — a too-short cut just browns it out and it comes back in the same wedged state.
**Minimum OFF time is 30 seconds** (Kim). This is a floor to enforce in code, not a suggestion; make it
a config value (default >= 30 s, room to raise it) and **verify the real discharge time empirically** on
the actual unit — if 30 s does not reliably reboot it, raise the default.

## Parts
### Hardware (Kim)
- A separate **3.3 VDC PSU** sized for the OE sensor's rail (current headroom over its peak draw).
- Wire its mains/input through a **spare Shelly Pro 4PM output**. `shelly_config.json` currently has
  channel id 1 and id 2 both as "Spare"; **confirm which physical output = Kim's "channel 2" and record
  the exact `id`** when wiring (do not assume — the config names and the panel labels are offset).
- **Never share the OE output with channel 0 (Heater) or channel 3 (Pi/CPU).** It gets its own channel.

### Config (dev)
- Add the channel to `shelly_config.json`: name `"OE"`, description `"OE sensor 3.3 VDC supply"`,
  `enabled: true`, with the confirmed `id`. `shelly_control.py set_switch()` already toggles any channel,
  so no new control code is needed — `--on oe` / `--off oe` should just work once named.

### Recovery logic (dev, in `py/oe_sampler.py`)
Escalation order, so the power-cycle is a last resort, not a reflex:
1. Normal capture. With the persistent BLE link (0026) the sensor should not sleep on its own.
2. On failure, the existing scan-retry / reconnect (widened window) runs first.
3. **Only if that is exhausted**, power-cycle the OE channel: `OFF` -> wait **>= 30 s** (super-cap
   discharge) -> `ON` -> wait for boot **and BLE advertise** before reconnecting -> resume captures.

Guard rails:
- **Between captures only** — never power-cycle during an in-flight capture / BLE transfer.
- **Rate-limit per run** — cap the number of cycles (e.g. a few); if it still will not come back, **log
  loudly and give up**, do not thrash the rail for 13 h.
- **Log every cycle** — timestamp, trigger reason, off-duration, and whether the sensor came back — so a
  run's OE gaps are explainable afterwards.
- Reuse the exact MQTT publish the heater guard / channel-3 cycle already use (byte-identical to
  `set_switch()`), so there is one power-control path, not two.

## Why it is safe
Cutting and restoring a *sensor* rail is unconditionally safe — unlike the heater (never cut-to-recover
logic there) it has no thermal or data-integrity hazard. The only failure mode is an OE gap, which is
strictly better than the whole sensor being dead for the rest of the run.

## Acceptance / test
- **Hardware (Kim):** OE sensor runs from the new 3.3 V rail through the confirmed Shelly channel;
  `shelly_control.py --off oe` / `--on oe` visibly powers it down and up.
- **Empirical (Pi):** measure the minimum OFF time that reliably reboots the sensor; confirm >= 30 s
  holds, set the default with margin.
- **Recovery (Pi):** force a wedge (or use an unplug/replug proxy), confirm `oe_sampler` power-cycles the
  channel autonomously and resumes captures, with the whole sequence in the log.

## Owner
- **Kim / hardware:** PSU + wiring + confirm the channel id.
- **Dev:** config entry + the recovery logic and its guard rails.
- **Pi / test:** discharge-time measurement + forced-wedge recovery.
