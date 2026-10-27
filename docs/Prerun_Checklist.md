# Pre-run checklist

Run through this before **every** rig run, and especially before an unattended 13 h one.
Most of it exists because we have been caught by it — the references point at the full story
in `CLAUDE.md`.

---

## 1. Lubricate the bearing

**Every run. Not optional, not even for 15 minutes.** A dry start damages the specimen.

> The oil also has a **measurement** consequence, not just a mechanical one — see §8. The film's state
> resets every time the rig stands still, and it moves UL by 20-50 %.

## 2. Mechanical assembly — the bearing must not slip on the shaft

**Especially after any teardown/reassembly, and spot-checked on long runs.** This is the check that
was missing for months and cost a worn bushing plus months of suspect data: the retaining nut was
never torqued to spec, slowly **self-loosened under rotation** (Junker vibration self-loosening), the
bearing lost its axial clamp and **slipped on the shaft** — found 2026-09 with a **stroboscope**,
bushing + lock nut then replaced. Full story in `docs/Maintenance_Log.md`.

- [ ] **Bearing-on-bushing bolt: finger-tight, then +90° with the tool wrench**, and the **tab-washer
      wings bent out** against the bolt head so it is positively locked. The tab washer is what stops
      it self-loosening — a bolt on a rotating shaft backs off on friction alone. Record date in the
      maintenance log.
- [ ] **Strobe the shaft at running speed — nothing may creep.** Set a stroboscope to the shaft
      frequency so the rotation freezes; a reference mark on the bearing collar / nut that **drifts**
      under the strobe = the bearing slipping or the nut backing off. The cheap test that would have
      caught it months ago. **After a rebuild this strobe pass is the gate to resume runs.**
- [ ] **New running surface = a hard data boundary.** A replaced bushing/bearing changes the acoustic
      signature; the first run after is a deliberate **re-baseline**, not a warm-up (`CLAUDE.md`,
      `docs/Maintenance_Log.md`).

## 3. The drive — the two settings that lie

Both of these let a run look perfectly healthy while the shaft does something else.

- [ ] **Read the drive's EFFECTIVE frequency reference, register 0x2523, with the motor stopped**
      (added 2026-10-27). Write 0x2502 = 2000 and 0 in turn; 0x2523 must read **2000 and 0**. If it
      stays put (it sat at 5000 = 50.00 Hz on 2026-10-27), something other than Modbus is setting the
      frequency. The source parameters as read over Modbus that day: **00-02 = 2** (run source =
      communication), **00-05 = 5** (main frequency = communication), **00-06 = 1** (alternative source =
      analog / pot), **00-07 = main + alternative SUMMED** when 1 — set to **0** (main only) on 2026-10-27,
      which makes the pot irrelevant. Re-check 00-07 after any drive power cycle (ticket 0047: source
      settings have fallen back before). Use a plain `pymodbus` client, `device_id=3`.
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

> **⚠️ THE TACH CANNOT VERIFY THAT THE MOTOR HAS STOPPED — it is on the RIG shaft, and the coupling is
> MAGNETIC (2026-10-20).** The rig shaft and the motor shaft are joined by two wheels of four magnets
> each, across an air gap, with no mechanical contact. So `rpm=0` with a frozen pulse count proves the
> **rig shaft** is stopped and says nothing about the motor, which can keep turning behind a coupling
> that is slipping or disengaged. Caught the same day: the check below reported "stopped" on a frozen
> pulse count while Kim could see the motor still running.
>
> It is worse than a blind spot, because the drive's own registers lie in the same direction — they have
> been caught reporting `run=STOP` with the shaft turning at 190 rpm. **The rig has NO sensor on the
> motor shaft at all.**
>
> **⚠️ AND THE DRIVE'S DISPLAY DOES NOT SHOW IT EITHER — it shows the SETPOINT (2026-10-20).** An earlier
> version of this entry said the panel was the valid test. It is not: with the motor confirmed stopped by
> eye and the telemetry reading `cmd=0.00 Hz, is_running=False`, **the panel still read 10.08 Hz** — the
> last value written to it, exactly the same stale behaviour as `frequency_out_hz` in the registers.
>
> So all three machine sources fail, and they fail in **different directions at different times**: the
> tach is mechanically decoupled from the motor, the registers have read `run=STOP` with the shaft at
> 190 rpm, and the panel holds the setpoint after a stop. On this one occasion the registers happened to
> be the accurate source and the panel the misleading one — the reverse of earlier the same day. **That
> is the point: none of them can be trusted as a rule.**
>
> **BUT WITH THE MOTOR ON THE RIG, THE TACH IS TRUSTWORTHY (Kim, 2026-10-20).** The paragraph above
> over-generalised. With the coupling engaged, a turning motor drags the rig shaft, so a tach reading
> **0 rpm with a frozen pulse count — and staying there** — does mean the motor is not driving. That is
> the normal case and the checklist's test below is valid for it.
>
> Two qualifications, and neither makes the tach useless:
>
> - **Coast-down:** the magnetic coupling releases as torque falls, so the rig shaft stops a few seconds
>   **before** the motor does. That is what happened on 2026-10-20 — the tach read 0 with the counter
>   frozen while the motor was still spinning down. Two shafts stopping at different times, not a blind
>   instrument. Read the tach twice, a few seconds apart, and let the motor coast.
> - **Breakaway slip:** the coupling can slip, leaving the motor turning while the rig shaft does not.
>   That is a **starting** failure, not a stopping one — it makes the tach under-report at start-up, and
>   it is why a profile's first speed step must be checked against an advancing pulse count.
>
> **Where the tach genuinely says nothing is when the motor is deliberately turned away** (the magnet
> wheels rotated apart, as in the 0052/0053 baselines). There is then no coupling at all, `rpm_meas = 0`
> is correct through a 600 or 3000 rpm segment, and **the only record of whether the motor ran is a human
> watching it** — write it down with a timestamp in the run folder.
>
> **Worth fixing:** the panel can usually be switched to display **output current** or **actual output
> frequency** instead of the setpoint, and either would indicate running. That, or a sensor on the motor
> shaft, would give the rig its first machine-readable answer to "is the motor turning?".
>
> The same applies in reverse when the motor is deliberately disengaged (the wheels turned apart): a run
> logging `rpm_meas = 0` through a 600 or 3000 rpm segment is then **correct**, not failed — and the
> only record of whether the motor actually ran is a human watching it. Write that down with a
> timestamp in the run folder; nothing in the data file can supply it.

The tach must read **`59.83 x Hz - 11.7`** — 1185 rpm at 20.00 Hz, within a few rpm. If it reads
high, the pot is summing in. If it reads zero while the drive claims to run, 02-03 is wrong.

- [ ] **Confirm the shaft actually stopped afterwards** — tach `rpm=0.00` *and* a frozen pulse
      count across two reads. `stop()` has been reported as successful without stopping the motor.

> **Verify actuation against the tach, never against a readback.** The drive has reported
> `cmd=0.0` while the shaft turned at 2985 rpm, and has shown a stale frequency in its own display
> minutes after a run ended.

## 4. Scope

- [ ] Reachable and answering SCPI:

```bash
python3 -c "import socket; s=socket.create_connection(('169.254.227.43',5025),timeout=8); \
s.sendall(b'*IDN?\n'); print(s.recv(200).decode().strip())"
```

Expect `AGILENT TECHNOLOGIES,MSO-X 2024A,…`. **Do not use `test_scope_connection.py`** — it points
at a stale IP and the PyVISA path we no longer use, so it fails even when the scope is fine.

- [ ] Nothing else is holding the connection. The scope takes **one TCP connection at a time**;
      a second one gets `ConnectionRefused`. Never poll the scope while a run is going.

## 5. OE BLE sensor (if `oe.enabled`)

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

## 6. Sensors and firmware

- [ ] `INFO` reports the firmware you think is running — the source file on disk is not evidence:

```bash
.venv/bin/python util_tool.py --port /dev/ttyACM0 info
```

- [ ] **Never flash mid-run.** The same board serves the tacho *and* the load cell.
- [ ] Load cell tared, and calibrated **per gain** if running the auto-gain firmware.
- [ ] **Is the UL probe mounted?** If not, `UL` records nothing and the run is OE +
      Kistler AE + slip ring only (ticket 0015).
- [ ] **Slip-ring PSU set to ~5 VDC.** The slip ring (`SP`, CHAN3) is fed from its own bench PSU;
      at the wrong voltage the SP channel records garbage or nothing. Confirm the supply reads
      **~5 VDC** before starting — nothing in software reads it back, so a wrong setting is invisible
      until the data is already useless.

## 7. Housekeeping

- [ ] Disk space for the run — roughly **0.32 GB/hour** at 1 M points (clamped to 500 k with three
      channels) and a 12 s sweep interval. **A 13 h run needs ~4.5 GB.** `df -h /home/aau`

      > **This used to say 2.7 GB/hour and ~35 GB, and that was stale by a factor of eight.** The old
      > figure came from runs that stored the time axis as its own dataset. Since `store.time_axis`
      > was set false (ticket 0044 — lossless, the attrs carry the ramp) the files are a fraction of
      > the size: the 13 h baseline `20260923_125909` was **4.26 GB for 793 minutes**. Corrected
      > 2026-10-02 after the stale figure was used to justify deleting a run as urgent when there was
      > room for seven more.
- [ ] The tree on the Pi is the current one. Several older copies of `acquire_scope_data.py`
      exist; make sure you are running the deployed current file.
- [ ] Heater guard arms at run start — check `heater_guard.log` in the run folder. Note the Shelly
      currently reports `???` for all channels (ticket 0006), so the guard is armed but blind to
      the relay's real state.
- [ ] Bearing lubricated. Yes, again. It is the one on this list that cannot be undone.

---

## 8. The oil-film transient — settle, or record time-since-start

**The oil-film transient resets on every stand and contaminates the first ~1 h.** Either run the rig
until UL stabilises before taking baseline measurements, **or** record time-since-start so the
first-hour rows can be binned out in analysis — **bin by time-since-start as a co-axis with
temperature.**

- [ ] Decide which of the two you are doing, **before** the run, and write it in the run notes.
- [ ] If the run is a baseline or is meant to be compared against another run, **settle first**:
      allow **>2 h** of running before the first measurement that counts.
- [ ] If you cannot settle (a 13 h protocol with its own schedule), accept that **the first hour is not
      steady state** and that a cold-start ramp puts its **lowest-temperature rows** exactly there.

**Why this is a checklist item and not a footnote.** Measured 2026-09-24 on `20260924_133945` at a
temperature held fixed at 41.0 C throughout: running dropped UL **−8 to −22 %**, one hour with the shaft
stopped recovered it **+21 to +55 %** (to 110-120 % of the starting block), and running again dropped it
**−23 to −43 %**. The cycle repeats on demand. The 0 rpm floor moved less than 1 %, so it is the rotating
contact, not the instrument. That is **as large as the genuine temperature response** (−16 to −36 %,
`20260924_065556`) — and it is the reason two runs of the same profile can differ by **+56 to +93 %** at
identical temperature purely because one of them had the night off. Full record in
`docs/Maintenance_Log.md`, 2026-09-24.

> **Consequence for comparing runs:** without controlling for time-since-start you are comparing
> oil-film state, not the variable you think you are measuring.

---

## After the run starts

Watch the first minute of telemetry and confirm **`rpm_meas` tracks `59.83 x vfd_cmd_hz - 11.7`**.
That single check catches the pot, 02-03, a wedged tacho and a mis-scaled sensor in one go — and
it is the check that would have caught the +200 rpm bias immediately on 2026-08-20 instead of
three steps in.
