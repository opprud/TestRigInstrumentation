---
id: 0033
title: Raspberry Pi intermittently freezes — leaves the heater running unattended, loses the whole HDF5 mid-run, and needs an MQTT power-cycle to recover
area: ops / reliability
role: dev
status: in-progress
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

---

## Evidence from the 2026-08-26 freeze (pi, added 2026-08-26)

### Two corrections to the problem statement above
1. **The run id is `20260825_145918`, not `20260825_123149`.** The 12:31 run was stopped by Kim at 14:58
   (heater never switched on — the CLI-launch trap); the night's run started 14:59:18 and is the one that
   was live when the Pi froze.
2. **This freeze did not lose the run.** The run ended cleanly at 04:12:28 with `duration_reached`, the
   HDF5 was closed, the heater guard logged until 04:19:12, and the Pi rebooted at **06:19:44** — roughly
   two hours later. The file is intact (3964 sweeps, 154 OE captures, verified by reopening it). The
   total-loss risk in "Why it matters" is real but is **not** what happened here.

### New consequence: a freeze also defeats the heater switch-off — this is a safety issue, not only data loss
The heater guard triggered correctly on `run_end` at 04:13:21 and then could not act:

```
[04:13:21] TRIGGER: run_end in telemetry (clean finish)
[04:13:21] switch-off attempt 1/12 -> API status unavailable (ConnectionRefused); falling back to MQTT CLI
[04:13:31] state UNKNOWN — command was sent, but could not confirm
   ... 12 attempts over 6 minutes, all inconclusive ...
[04:19:12] !!! could not confirm channel 0 OFF after 12 attempts
[04:19:12] heater guard exiting WITHOUT confirmation
```

The heater **stayed on**. Measured at 06:27: Omron **PV 100.0 °C against SV 100.0 °C** — still regulating
on setpoint, **2 h 16 min of unattended heating after the run ended**. Switched off by hand at 06:28
(`✓ [0] Heater: OFF` first try, once the host was healthy again); bearing then fell 101 → 98 → 94 → 90 °C
in four minutes, which is the only proof that counts that the relay opened.

**Implication for the watchdog design in "Directions" above:** the external heartbeat must switch
**channel 0 (Heater) OFF** as well as power-cycling **channel 3 (Pi)**, and must do the heater first.
Cutting the heater from outside is unconditionally safe; leaving it on while the host is frozen is not.

**Implication for ticket 0017** (guard — retry the MQTT status query, currently `review`): retries cannot
fix this case. Twelve attempts against a broker the frozen host cannot reach produce twelve inconclusive
results. The guard was not misbehaving — it correctly reported that it had lost the ability to act, which
is the most a process on the dying host can do. 0017 remains worth having for transient broker blips; it
is not a mitigation for 0033.

### Cause: no forensics survive on this host — treat persistent logging as a prerequisite, not a nice-to-have
Attempted post-mortem after the reboot:
- `journalctl --list-boots` lists **only the current boot** — journald is volatile here, so nothing from
  before the freeze exists.
- There is **no `/var/log/syslog` and no `/var/log/kern.log`** at all.

So memory growth, USB/serial resets, the BLE stack, SD-card IO stalls, thermal and PSU sag are *all*
equally consistent with the available evidence, because there is none. Every freeze so far has been
unfalsifiable after the fact. The "cheap first step" in Directions is really the **blocking** first step:
until `Storage=persistent` is set in `/etc/systemd/journald.conf` (plus a memory/temperature sampler), the
next freeze will also leave nothing and this ticket cannot progress. Not yet changed — awaiting Kim's
go-ahead, as it is a system-level change on the rig host.

### One hypothesis, offered as circumstantial only
The Shelly API was **already refusing connections at 04:13:21**, one minute after the run ended and two
hours before the reboot. If that is the onset rather than a coincidence, the freeze began at *teardown* —
when 13 h of scope sockets, the held BLE session and the HDF5 buffers were all released — rather than
during steady-state acquisition. Worth pointing the first instrumented look at the teardown path.

## Instrumentation is now IN PLACE on the Pi (pi, 2026-08-26, authorised by Kim)

The "cheap first step" is done. The next freeze will leave evidence.

### Why nothing survived before — it was deliberate, not an oversight
Raspberry Pi OS ships **`/usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf`** containing
`Storage=volatile`, to spare the SD card. `/var/log/journal/` already existed but was empty and unused.
The same drop-in directory sets `ForwardToSyslog=yes`, which goes **nowhere** because no syslog daemon is
installed — hence no `/var/log/syslog` either. So the host was configured to forget, from two directions.

### What was changed
**1. Persistent journal** — `/etc/systemd/journald.conf.d/50-persistent-for-freeze-diagnosis.conf`
(`/etc` overrides `/usr/lib`, and 50 sorts after 40):
```ini
[Journal]
Storage=persistent
SystemMaxUse=500M       # capped — SD wear is the reason the default is volatile
SystemMaxFileSize=50M
SystemMaxFiles=20
SystemKeepFree=2G
SyncIntervalSec=60s     # default 5 min is exactly the window lost in a freeze
```
`SyncIntervalSec` matters more than it looks: journald syncs ERR-and-above immediately but buffers lower
priorities for 5 minutes by default, so the run-up to a hard hang — the interesting part — was the part
guaranteed to be lost. Verified after `journalctl --flush`: `/var/log/journal/<machine-id>/` now holds the
journal, `/run/log/journal` is empty.

**2. Per-minute health sampler** — `/usr/local/bin/rig-health-sample.sh`, driven by
`rig-health.timer`/`.service` (enabled at boot, 60 s interval). One journal line per minute, tag
`rig-health`:
```
mem_avail=15148M/16218M swap_used=0M load=1.42 1.04 0.69 temp=58.2C throttled=0x0 root_free=80G
  top=[claude:583M labwc:111M python:84M ]
```
This covers the hypotheses the journal alone cannot: **slow memory growth** over a 13 h run (acquisition +
`bleak`), **thermal**, and — via `vcgencmd get_throttled` — **PSU sag / undervoltage**, which is a classic
Pi freeze cause and would otherwise be invisible. Baseline on an idle host: 15.1 GB of 16 GB available,
0 swap, 59 C, `throttled=0x0`, 80 GB free.

### After the next freeze, read this before power-cycling anything
```bash
journalctl -b -1 -n 100 --no-pager          # the previous boot's last words (now exists)
journalctl -t rig-health -b -1 | tail -60   # the last hour of memory/thermal/undervoltage trend
journalctl -b -1 -p err --no-pager          # kernel oops, OOM killer, USB/serial resets
```
A `throttled` value other than `0x0` in the final samples implicates the power supply; a falling
`mem_avail` implicates a leak; neither moving points at the BLE/USB/SD paths instead.

### To revert
Delete `/etc/systemd/journald.conf.d/50-persistent-for-freeze-diagnosis.conf` and
`systemctl restart systemd-journald`; `systemctl disable --now rig-health.timer` and remove the three
files under `/usr/local/bin` and `/etc/systemd/system`.

**Still open on this ticket:** the external heartbeat -> Shelly watchdog (must cut channel 0 Heater as
well as cycling channel 3 Pi, heater first), and the periodic HDF5 flush. The instrumentation above only
makes the *cause* findable; it does not yet make an unattended run survive a freeze.
