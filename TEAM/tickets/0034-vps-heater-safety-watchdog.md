---
id: 0034
title: VPS heater-safety watchdog — independent daemon on the MQTT-broker VPS that switches the heater off after a test ends / when no live run wants heat
area: ops / reliability / safety
role: dev
status: backlog
depends_on: 0033
branch:
pr:
---

## Why
The on-Pi heater guard cannot protect against a frozen Pi. On 2026-08-26 a freeze at run-end left the
heater regulating at **100 C for 2 h 16 min unattended**, because the guard runs on the host that froze
and could not reach the broker (ticket 0033). The switch-off has to come from a machine that is **not**
the rig Pi. The **Linux VPS that already hosts the MQTT broker** (`185.81.165.190`) is the natural home: it
has local, always-up access to the Shelly, is independent of the rig Pi, and has stable storage for logs.

## What to build
A small always-running daemon (systemd service) on the MQTT-broker VPS that **guarantees the heater
(Shelly Pro 4PM channel 0) is OFF after a test ends, and whenever no live, healthy run legitimately wants
heat.**

**Fail-safe by design:** the *absence* of a positive "a run is alive and heating" signal is what triggers
heater-off. A frozen / dead / rebooting Pi produces no signal, so it results in the heater being cut, not
left on. Kim's requirement — "switch the heat off after a test is finished" — falls out of the same rule:
test-end stops the signal.

### Mechanism
- **Heartbeat (Pi -> VPS over MQTT):** while a heated run is active the Pi publishes a periodic heartbeat
  to an MQTT topic (e.g. `testrig/run/heartbeat`) with `run_id` + "heating wanted". The broker is local to
  the watchdog, so it sees the heartbeat with zero dependence on the Pi being otherwise reachable.
- **Rule:** if the heartbeat has been absent for **N minutes** (config, e.g. 3-5 min — longer than one
  telemetry/OE cycle, shorter than a dangerous overheat) **and** heater ch0 reads ON (or cannot be
  confirmed OFF), publish ch0 -> OFF locally and log it; keep re-issuing until `output:false` is confirmed.
- **Clean test-end is the same rule:** at run-end the heartbeat stops -> the watchdog backs up the on-Pi
  guard and ensures the heater is off even when the guard's own switch-off failed (the 04:19 case that
  motivated this).
- **State + control over MQTT** (see 0033 / `py/shelly_control.py`): read via `Switch.GetStatus` /
  `NotifyStatus`; send off via `Switch.Set {"id":0,"on":false}` to `<device>/rpc`.

### Must-haves
- **Independent of the rig Pi** — runs on the broker VPS, `localhost:1883`.
- **Fail-safe** — unknown/absent heartbeat + heater-not-confirmed-off => send OFF (OFF is always safe).
- **Persistent logging on the VPS** (the Pi's journald is volatile, 0033) — every intervention recorded.
- **Idempotent + rate-limited** — re-issue OFF until confirmed, without thrashing.
- **Manual override / maintenance flag** for a deliberate heater-on outside a run (bench work); default =
  no run heartbeat => heater off.
- **Self-monitored** — systemd `Restart=always`; a dead watchdog should alert (and arguably means the
  heater must not be allowed on).

### Optional companion (from 0033)
The same daemon can also power-cycle the Pi (Shelly ch3) after M minutes of silence — **heater OFF first,
then cycle the Pi.** Keep heater-off as the safety-critical core; the Pi-cycle is convenience recovery.
Scope decision at implementation.

## Acceptance
- Heated run active + healthy: the watchdog does nothing (heater stays under the run's control).
- Kill the Pi mid-heat, or simulate the run-end guard failure: within N minutes the watchdog switches the
  heater OFF from the VPS and logs it, with the Pi unreachable throughout — confirmed by bearing/oil
  temperature falling.

## Owner / test
- **Dev:** the VPS daemon + systemd unit + the Pi-side heartbeat publisher.
- **Tester (Pi/Kim):** the frozen-Pi drill above, on the bench, before it guards a real overnight run.
