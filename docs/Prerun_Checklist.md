# Pre-run checklist

Run through this before **every** rig run, and especially before an unattended 13 h one.
Most of it exists because we have been caught by it — the references point at the full story
in `CLAUDE.md`.

---

## 1. Lubricate the bearing

**Every run. Not optional, not even for 15 minutes.** A dry start damages the specimen.

## 2. The drive — the two settings that lie

Both of these let a run look perfectly healthy while the shaft does something else.

- [ ] **Parameter 02-03 is on communication**, not the pot. A drive in pot mode accepts a whole
      profile over Modbus, echoes it back in the registers, and follows none of it.
- [ ] **The pot is at its bottom stop.** Nastier than pot mode, because the drive still *obeys*:
      the pot is **summed onto** the Modbus reference. Found 2026-08-20 with a constant
      **+3.4 Hz / +200 rpm** on every commanded point — the staircase tracked every step and the
      run simply ran 200 rpm too fast throughout.

**Verify both with one measurement**, because neither can be trusted from a readback:

```bash
cd py
.venv/bin/python rs510_vfd_control.py --port /dev/ttyUSB0 --start 20   # a known frequency
sleep 15
.venv/bin/python util_tool.py --port /dev/ttyACM0 speed                # expect ~1185 rpm
.venv/bin/python rs510_vfd_control.py --port /dev/ttyUSB0 --stop
.venv/bin/python util_tool.py --port /dev/ttyACM0 speed                # expect rpm=0.00
```

The tach must read **`59.83 x Hz - 11.7`** — 1185 rpm at 20.00 Hz, within a few rpm. If it reads
high, the pot is summing in. If it reads zero while the drive claims to run, 02-03 is wrong.

- [ ] **Confirm the shaft actually stopped afterwards** — tach `rpm=0.00` *and* a frozen pulse
      count across two reads. `stop()` has been reported as successful without stopping the motor.

> **Verify actuation against the tach, never against a readback.** The drive has reported
> `cmd=0.0` while the shaft turned at 2985 rpm, and has shown a stale frequency in its own display
> minutes after a run ended.

## 3. Scope

- [ ] Reachable and answering SCPI:

```bash
python3 -c "import socket; s=socket.create_connection(('169.254.227.43',5025),timeout=8); \
s.sendall(b'*IDN?\n'); print(s.recv(200).decode().strip())"
```

Expect `AGILENT TECHNOLOGIES,MSO-X 2024A,…`. **Do not use `test_scope_connection.py`** — it points
at a stale IP and the PyVISA path we no longer use, so it fails even when the scope is fine.

- [ ] Nothing else is holding the connection. The scope takes **one TCP connection at a time**;
      a second one gets `ConnectionRefused`. Never poll the scope while a run is going.

## 4. OE BLE sensor (if `oe.enabled`)

- [ ] The sensor is **advertising** — it sleeps on its own and a sleeping device is invisible:

```bash
.venv/bin/python -c "
import asyncio; from bleak import BleakScanner
async def m():
    ds = await BleakScanner.discover(timeout=25.0)
    print([ (d.address, d.name) for d in ds if d.address.upper()=='03:24:71:01:04:54' ])
asyncio.run(m())"
```

If it is silent, press the reset button on the unit (ticket 0019 — it cannot be revived over BLE).

- [ ] `oe.device_address` is the MAC **as BlueZ sees it**, not a macOS UUID.
- [ ] `oe.interval_min` is what you want for *this* run — 3 for the short tests, and see the
      cadence note in `CLAUDE.md` before changing it for a long one.
- [ ] `oe.sample_rate_hz` is **80000**. The vendor's file says 100000 and is wrong.

## 5. Sensors and firmware

- [ ] `INFO` reports the firmware you think is running — the source file on disk is not evidence:

```bash
.venv/bin/python util_tool.py --port /dev/ttyACM0 info
```

- [ ] **Never flash mid-run.** The same board serves the tacho *and* the load cell.
- [ ] Load cell tared, and calibrated **per gain** if running the auto-gain firmware.
- [ ] **Is the UL probe mounted?** If not, `UL` records nothing and the run is OE +
      accelerometer + slip ring only (ticket 0015).

## 6. Housekeeping

- [ ] Disk space for the run — roughly **2.7 GB/hour** at 1 M points and a 12 s sweep interval.
      A 13 h run needs ~35 GB. `df -h /home/aau`
- [ ] The tree on the Pi is the current one. Several older copies of `acquire_scope_data.py`
      exist; make sure you are running the deployed current file.
- [ ] Heater guard arms at run start — check `heater_guard.log` in the run folder. Note the Shelly
      currently reports `???` for all channels (ticket 0006), so the guard is armed but blind to
      the relay's real state.
- [ ] Bearing lubricated. Yes, again. It is the one on this list that cannot be undone.

---

## After the run starts

Watch the first minute of telemetry and confirm **`rpm_meas` tracks `59.83 x vfd_cmd_hz - 11.7`**.
That single check catches the pot, 02-03, a wedged tacho and a mis-scaled sensor in one go — and
it is the check that would have caught the +200 rpm bias immediately on 2026-08-20 instead of
three steps in.
