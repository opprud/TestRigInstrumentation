---
id: 0033
title: Raspberry Pi intermittently freezes — needs an MQTT power-cycle to recover; a freeze mid-run loses the whole HDF5
area: ops / reliability
role: dev
status: backlog
depends_on:
branch:
pr:
---

## Problem
The Pi that runs the rig (scope acquisition, motor/temp control, dashboard, BLE/OE) **intermittently
freezes** — becomes fully unresponsive (SSH, serial, the bus, the dashboard all stop). Observed again
2026-08-26 at/after the end of the 13 h run `20260825_123149`; Kim reports it happens "at times", i.e.
recurring, not a one-off.

## Why it matters
- **A freeze mid-run loses the whole run.** The acquisition HDF5 is never flushed until a clean close
  (CLAUDE.md flush note) — a hard power-cut therefore costs the entire file, not just the last sweep. A
  freeze during a 13 h run is a total-loss event, which raises the priority of *both* diagnosing the freeze
  *and* periodic-flushing the HDF5.
- Recovery needs a **physical / MQTT power-cycle**, so an unattended overnight run that freezes is dead
  until someone intervenes.

## Recovery (works today — documented so it is fast next time)
The Pi's mains is **channel 3 ("CPU" / "Raspberry pi") of the Shelly Pro 4PM** (`shellypro4pm-c8f09e84cdf8`),
independent of the Pi itself, so it can be cycled over MQTT from any machine that reaches the broker.
Credentials + broker host are in `py/shelly_config.json` (`mqtt` block). **Channel 3 = Pi; channel 0 =
Heater — never cut 0.**
```
mosquitto_pub -h <host> -p 1883 -u mqttuser -P <pw> -t 'shellypro4pm-c8f09e84cdf8/rpc' \
  -m '{"id":42,"src":"shelly_ctrl","method":"Switch.Set","params":{"id":3,"on":false}}'   # OFF
# wait ~10 s
mosquitto_pub -h <host> -p 1883 -u mqttuser -P <pw> -t 'shellypro4pm-c8f09e84cdf8/rpc' \
  -m '{"id":42,"src":"shelly_ctrl","method":"Switch.Set","params":{"id":3,"on":true}}'    # ON
```
Byte-identical to what `py/shelly_control.py set_switch()` publishes. `shelly_control.py --off cpu`/`--on cpu`
does the same but runs *on* the Pi, so it is useless when the Pi is the frozen thing.

## Directions to investigate (cause + resilience)
- **Cause:** correlate freezes with long-run memory growth (acquisition + BLE/`bleak` over 13 h), USB/serial
  (RP2040/FTDI) resets, the BLE stack, SD-card IO stalls, thermal, or PSU sag. Cheap first step: persistent
  journald + a memory/temp sampler so the next freeze leaves evidence.
- **Watchdog:** the Pi's own hardware watchdog (systemd `RuntimeWatchdog`) for soft hangs, and/or an
  **external** heartbeat (VPS or a second device) that pings the Pi and auto-issues the Shelly channel-3
  power-cycle after N minutes of silence — the only thing that helps a truly frozen Pi on an unattended run.
- **Shrink the loss:** periodic HDF5 flush (the parked flush item) so a freeze costs one interval, not the
  whole file. Watchdog + flush together turn a freeze from "lose the night" into "lose minutes".

## Owner / test
- **Dev:** instrument for the next freeze; prototype the external heartbeat -> Shelly-cycle watchdog.
- **Tester (Pi/Kim):** capture state at the next freeze before cycling, if the Pi is reachable at all.
