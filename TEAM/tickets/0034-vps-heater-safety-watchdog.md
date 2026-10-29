---
id: 0034
title: VPS heater-safety watchdog — independent daemon on the MQTT-broker VPS that switches the heater off after a test ends / when no live run wants heat
area: ops / reliability / safety
role: dev
status: in-progress
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

## Hardware notes (from the 2026-08-26 incident, Pi)
- **Never require confirming the heater is ON.** This Shelly returns `???` for channel state (no retained
  MQTT state) — the guard's 12 inconclusive attempts on 04:13-04:19 are what that looks like in practice.
  The "cannot be confirmed OFF => send OFF" rule above is deliberate; do not let it be "improved" into a
  confirmed-ON gate. **The falling bearing temperature (a minute or two) is the only real confirmation the
  relay opened.**
- **Fold the Omron setpoint into the interlock — drive SV down after a run.** After the incident SV sat at
  100 C; cutting ch0 makes that inert, but any later re-energising of the relay resumes full heating with
  nobody present. The watchdog (or the on-Pi guard on a clean end) should also drive **SV down** — a single
  Modbus write. Belt and braces.

## Owner / test
- **Dev:** the VPS daemon + systemd unit + the Pi-side heartbeat publisher.
- **Tester (Pi/Kim):** the frozen-Pi drill above, on the bench, before it guards a real overnight run.

## Implementation log (2026-10-29, windows)

VPS daemon built and verified on the live relay. Code in `py/vps_heater_watchdog/`
(`watchdog.py`, `config.example.json`, `heater-watchdog.service`, `install_root.sh`, `README.md`).

**Deployed** on the broker VPS under user `claude-win` at `/home/claude-win/heater-watchdog/`.
paho-mqtt is **vendored** (`vendor/paho`, extracted from the wheel with `python3 -m zipfile`)
because the VPS has neither `pip` nor `python3-venv` and both need root. Runs on stock
`/usr/bin/python3` 3.10 with `PYTHONPATH=vendor`.

**Design decisions**
- **`armed` flag, default false (observe-only):** logs the decision and publishes
  `testrig/watchdog/status` every cycle, but never actuates. Ships disarmed so it cannot cut a
  live run before the Pi heartbeat publisher exists. The on-Pi guard stays primary until armed.
- **Heater state is unknown-safe:** this Shelly keeps no retained channel state. Rule is "heat
  not wanted AND (heater ON OR not confirmed OFF) → send OFF". Never gated on a confirmed-ON read.
- **Startup grace** (`startup_grace_sec`, 200 s): after a (re)start with no heartbeat yet, hold
  actuation one window so a live run can resume heartbeats before the watchdog acts.
- **Maintenance override:** `touch ~/heater-watchdog/MAINTENANCE` stands the watchdog down for
  deliberate bench heating; default (no file) = fail-safe.
- **Omron SV-down not done here** — the VPS can't reach the RS485 Omron; relay cut is the hard
  backstop and de-energises the heater regardless of SV. SV-down stays a Pi-side clean-end action.
- **Pi power-cycle (ch3, from 0033) disabled** (`pi_cycle_enabled:false`).

**Acceptance (live relay, heater toggled with Kim's authorisation):**
| case | input | decision | relay |
|---|---|---|---|
| A | fresh heartbeat | `run-alive` | untouched |
| B | no heartbeat, heater OFF | `off-confirmed` | untouched |
| C | no heartbeat, heater ON, `armed:false` | `would-cut` (log only) | **stays ON** |
| D | no heartbeat, heater ON, `armed:true` | `INTERVENTION → Switch.Set OFF` | **→ OFF, 0 W** |

**Heartbeat contract for the Pi side (NOT yet implemented → blocks arming):**
`testrig/run/heartbeat` (non-retained), `{"run_id","heating":true,"ts":<unix>,"host":"pi"}`,
~30 s cadence while a heated run wants heat; stop at run-end.

**Remaining**
1. Install the systemd service (needs one root step on the VPS: `sudo bash install_root.sh`).
2. Pi: implement the heartbeat publisher (contract above) in the run/heater path.
3. Arm (`config.json` `armed:true` + restart) once heartbeats are confirmed live.
4. Bench frozen-Pi drill with a real heated run before it guards overnight.
