# ForeverBearing TestRig — Instrumentation

This file provides guidance for anyone (human or agent) working in this repository.

Automated data-acquisition system for a **bearing test rig** used in tribology research
(acoustic-emission / ultrasound vs. speed and temperature). A VFD-driven motor spins a
test bearing through an RPM staircase across a series of temperature set-points while an
oscilloscope captures high-resolution waveforms from the sensors and hardware telemetry
(RPM, temperature, load, drive frequency) is logged alongside. Everything is written to
HDF5 and can be uploaded to Azure Blob storage for offline analysis.

The rig runs on a **Raspberry Pi**. A React dashboard drives it; a Python backend does the
acquisition and motor/temperature control; a small C++ firmware on an RP2040 reads the
tachometer and load cell.

---

## What a run actually does

1. Operator loads a **test profile** (JSON) in the dashboard and starts a run.
2. The backend starts one process that runs two things in parallel, paired by a `run_id`:
   - a **scope-acquisition loop** (own thread) that repeatedly digitizes the scope and
     writes each capture ("sweep") to HDF5;
   - a **test runner** (asyncio) that drives the motor through the profile's RPM/temperature
     schedule over Modbus/RS485 and logs telemetry to JSONL.
3. The latest telemetry (RPM, drive Hz, temperature, load, current step…) is stamped onto
   **every HDF5 sweep as attributes**, so each waveform is tagged with its operating point.
4. Output lands in a per-run folder (`py/data/runs/<run_id>/`): the scope HDF5, the
   telemetry JSONL, and a human-readable event log (`acquire_scope.log`).
5. The HDF5 can be uploaded to Azure from the dashboard.

---

> **Before every run: `docs/Prerun_Checklist.md`.** Lubricate the bearing, and verify the drive
> against the tach at a known frequency — that one measurement catches parameter 02-03, a summing
> pot, a wedged tacho and a mis-scaled sensor at once.

## Repository layout

```
py/          Python backend (acquisition, motor/temp control, API server, tools)
react/       React + Vite dashboard; test profiles live in react/public/config/
firmware/    RP2040 (Seeed XIAO) firmware — PlatformIO/C++ — tachometer + load cell
docs/        Hardware/driver notes, dashboard usage, Azure upload notes
```

Key Python modules:

| File | Role |
|------|------|
| `py/acquire_scope_data.py` | **Main entry point.** Orchestrates scope acquisition + runner, writes HDF5. |
| `py/test_runner.py` | Motor speed control (PI or open-loop), temperature set-points, tacho/load reads, telemetry JSONL. |
| `py/api_server.py` | HTTP API the dashboard talks to; launches `acquire_scope_data.py` as a subprocess and streams its stdout. |
| `py/rs510_vfd_control.py` | VFD (variable-frequency drive) control over Modbus/RS485. |
| `py/omron_temp_poll.py` | Omron E5CC temperature controller over Modbus/RS485. |
| `py/hardware_discovery.py` | Enumerates serial ports (RS485 adapter, RP2040). |
| `py/util_tool.py` | Command-line client for the RP2040 (load cell + tachometer). |
| `py/plot_waveform.py` | Plot waveforms from an HDF5 file (time / FFT / spectrogram). |
| `py/scope_utils.py` | Scope connection helpers. |
| `py/config.json` | Scope + hardware configuration and acquisition **defaults**. |

---

## Hardware

| Part | What | Interface |
|------|------|-----------|
| Oscilloscope | Keysight/Agilent **MSO-X 2024A** (InfiniiVision 2000 X-Series, 200 MHz, 4 analog channels) | LAN, raw SCPI socket (port 5025) |
| Motor | **KLEE T712-2**, 3-phase induction, **2-pole**, 0.55 kW (2840 rpm @ 50 Hz, 3470 @ 60 Hz) | via VFD |
| VFD | RS510-type drive | Modbus RTU / RS485 |
| Temp controller | Omron **E5CC** | Modbus RTU / RS485 |
| Tachometer | **ifm OGT500** diffuse reflection sensor (reflective mark on shaft) | digital pulse → RP2040 GPIO0 |
| Load cell | HX711 | → RP2040 |
| Microcontroller | Seeed XIAO **RP2040** | USB serial (ASCII protocol, 115200 baud) |

The VFD and the Omron share one RS485 bus (different Modbus slave IDs), so bus access is
serialized with a lock. Sensor channels wired to the scope are configured in
`config.json → channels`. **The aliases do not read as you would expect** — the alias `UL`
is the acoustic-emission probe and the alias `AE` is the accelerometer:

| Scope source | Alias (`name`) | Sensor |
|---|---|---|
| CHAN1 | `UL` | Kistler acoustic-emission probe |
| CHAN2 | `AE` | Piezo accelerometer |
| CHAN3 | `SP` | Slip ring (slæbering) |
| CHAN4 | `Temp` | Temperature — **disabled** |

The aliases are what the profile's `scope_channels` block, `plot_waveform.py --channels` and
the dashboard's preview picker refer to, so keep those three in sync with this table.

---

## Build & run

### Python backend
```bash
cd py
python3 -m venv .venv && source .venv/bin/activate   # first time
pip install -r requirements.txt
```
The plotting tool (`plot_waveform.py`) additionally needs `scipy` and `plotly`; confirm they
are in `requirements.txt`.

Run a profiled test directly (paths are relative to the `py/` working directory):
```bash
python3 acquire_scope_data.py config.json ../react/public/config/<profile>.json
```
Manual mode (no profile — uses `config.json` acquisition defaults only, no motor/temp):
```bash
python3 acquire_scope_data.py config.json
```
Add `--debug` for verbose output. Normally the run is started from the dashboard, which
launches the same command via `api_server.py`.

### Dashboard (frontend)
```bash
cd react
npm install
npm run dev        # dev server
npm run build      # production build
npm test           # tests
```
The dashboard reads test profiles from `react/public/config/*.json` and talks to the API
server (`py/api_server.py`). See `docs/Dashboard_Test.md` for the exact workflow.

### RP2040 firmware
```bash
cd firmware
pio run                     # build
pio run --target upload     # flash (auto-detects the board)
pio device monitor          # serial console at 115200 baud
```
The firmware speaks a line-based ASCII protocol: `SPEED?`, `LOAD?`, `TARE`, `SETPPR <n>`,
`PPR?`, `SETCAL <slope> <tare>`, `CAL?`, `SETGAIN <64|128>`, `SETTIME <unix_ms>`, `PING`,
`INFO`. See `firmware/RP2040_README.md` for the full command reference and load-cell
calibration procedure.

### Command-line tools (`py/`)
Talk to the RP2040 directly (useful for bring-up and sensor debugging):
```bash
python3 util_tool.py --port <PORT> ping | info | load | speed | tare | cal
python3 util_tool.py --port <PORT> calibrate --weight-g 10000    # guided load-cell cal
python3 util_tool.py --port <PORT> setppr --ppr 1                # tach pulses per revolution
python3 util_tool.py --port <PORT> --json load                  # machine-readable output
```
Inspect a captured file:
```bash
python3 plot_waveform.py <file>.h5 --sweep sweep_000 --channels UL,AE,SP --fft --spectrogram
python3 inspect_hdf5.py <file>.h5
```
Other helpers in `py/`: `test_scope_connection.py`, `hardware_discovery.py`,
`scanmodbusregisters.py`, `omron_temp_poll.py`, `rs510_vfd_control.py`.

---

## Configuration model

Two layers, resolved with **the profile overriding `config.json`**:

- `py/config.json` — the baseline: scope IP/port, channel list, acquisition defaults,
  bearing/lubricant metadata, output/compression, Azure target.
- A **test profile** (`react/public/config/<name>.json`) — per-test overrides:
  - `setpoints.rpm` / `setpoints.temperature` — the time-based schedule,
  - `acquisition` — scope points / memory depth / interval for that test,
  - `scope_channels` — per-channel time-base and volts-per-division,
  - `control` — motor-control parameters (see below).

**Scope channel scaling:** `volt_range` in a profile is the *full vertical range*
(`:CHANx:RANGe`), i.e. **8 × volts-per-division** on this 8-division scope. So
`volt_range: 8.0` = 1 V/div, `16.0` = 2 V/div. `timebase_range` is the full 200 ms window
(10 × time/div).

**Acquisition (points / depth):** `points_mode: RAW` reads the full acquisition memory (not
just the ~1000 on-screen points); `scope_points`/`points: "MAX"` transfers everything;
`acq_points` forces the scope's acquisition memory depth. With 3 channels the ceiling is
~500 k points/channel (memory is shared across active channels).

**Motor control (`control` block, read by `test_runner.py`):**
- `rpm_per_hz_guess` — rpm-per-Hz for the feedforward. **Must be 59.5** for this 2-pole
  motor at the rig's light load. (The old default of 30 assumed a 4-pole motor and was wrong.)
- `open_loop` — if `true`, command drive Hz directly from the target (`Hz = target / rpm_per_hz`)
  and **ignore the tachometer**; if `false`, closed-loop PI on the tacho.
- Plus PI gains, rate limits and safety thresholds (kept at defaults).

> Note: `control` is currently read **only from the profile**, not from `config.json`.

---

## Architecture decisions (and why)

- **One `:DIGITIZE` per sweep over one reused TCP connection, reading all channels from the
  same shot** — not a digitize-per-channel. The per-channel approach (3 digitizes + 3 fresh
  sockets each sweep) overloaded the scope at high resolution and made its LAN interface
  wedge; the single-shot approach is ~3× lighter and keeps the channels time-aligned. (This
  replaced the earlier PyVISA/SCPI path; capture is now done over a raw TCP socket.)

- **Resilient sweep loop: retry → scope reset → skip-and-continue.** At the high-resolution
  setting the scope's interface wedges *intermittently* (roughly every ~10 minutes) under
  load. On a failed capture the loop retries; before each retry it opens a fresh connection
  and sends `:STOP` + `*CLS` (which do **not** change scope setup) and re-applies the channel
  and acquisition settings; if all attempts fail it **skips that one sweep and keeps going**.
  A full 13-hour run typically loses well under 1 % of sweeps and never dies. This is the
  single most important reliability decision.

- **Forced acquisition memory depth.** The scope defaults to a modest auto depth. The code
  sets `:ACQuire:POINts` (via `acq_points`) and reads out with `RAW` mode + `:WAV:POIN MAX`
  to get the maximum points per channel in the fixed time window.

- **Open-loop speed option.** The optical tachometer has proven unreliable, and in *closed*
  loop a mis-reading tacho silently corrupts the actual speed (the loop just drives the motor
  to whatever makes the bad reading equal the target). The recorded **drive frequency is a
  deterministic, physically-grounded speed reference** (2-pole motor ⇒ ~59.5 rpm/Hz), so
  open-loop control makes the shaft follow the protocol regardless of the sensor, and true
  speed is reconstructed offline as `59.5 × Hz`. The tacho is still read and logged for
  cross-checking.

- **Unified per-run event log** (`acquire_scope.log`) — both scope failures (with the exact
  SCPI step that failed) *and* runner/RS485 errors + the stop reason land in one
  human-readable file, so an unattended run leaves a self-contained trace.

- **Config defaults + profile overrides**, so the system has a sane headless baseline while
  each test carries only what it changes.

---

## Known issues / gotchas

- **⚠️ UL PROBE DETACHED since 2026-08-19 — CHAN1 is not measuring.** The ultrasound probe was
  unscrewed to make room for mounting the BearingBrain OE BLE sensor, pending a mechanical change.
  CHAN1 (alias `UL`) records whatever sits on a disconnected cable. **The `UL` group in the HDF5
  looks entirely normal** — same 500,000 points, same scaling attributes — so nothing in the file
  distinguishes it from real data except the note now stamped into
  `/metadata/test_parameters/ul_probe_status`. **Do not analyse UL data from runs in this period.**
  Remove this entry, the `config.json` note and the profile note together when the probe is
  refitted.


- **The scope wedges intermittently at high resolution — frequently, not occasionally.** Quantified on the 13 h run `20260820_125647` (`acquire_scope.log`): **114 reset/recovery cycles (~one every 7 minutes), 468 error lines, dominated by `ConnectionRefused` (280) and `TimeoutError` (149)**. The resilience machinery absorbs nearly all of it — **1 sweep lost of 3778 (0.026 %)** — but it is masked, not eliminated: the run is one un-recovered retry from a real gap. `ConnectionRefused` dominating points at the scope's own LXI socket server dropping/capping connections, not just network latency. Lower the point count or raise `sweep_retries` for zero-loss runs; root cause tracked in **ticket 0029**.

- **The tachometer is accurate — verified 2026-08-19.** It was long suspected of over-reading;
  it was not. Measured against commanded drive frequency across the full range:

  | drive Hz | shaft rpm | rpm/Hz | slip vs 60 |
  |---|---|---|---|
  | 5 | 288 | 57.6 | 4.0 % |
  | 10 | 588 | 58.8 | 2.0 % |
  | 20 | 1190 | 59.5 | 0.8 % |
  | 30 | 1788 | 59.6 | 0.7 % |
  | 40 | 2382 | 59.5 | 0.8 % |
  | 50 | 2979 | 59.6 | 0.7 % |

  **`rpm = 59.83 x Hz - 11.7`, maximum deviation 5 rpm.** The intercept is zero within error, and
  slip falls with speed as an induction motor under light load should. Pulse-count, single-period
  and `SPEED?` agree at every point; one glitch in 110,658 pulses. Use `rpm_meas` from the tach as
  the speed of record **for runs from 2026-08-19 onward** (firmware >= 1.1.1). For earlier runs use
  `rpm_target`: the old firmware derived rpm from the last two edges with no timeout or filtering
  and over-read by ~582 rpm.

- **The frequency reference source is selected by drive parameter 02-03 — pot *or* communication,
  not both.** Until 2026-08-19 it was set to the analog pot, so Modbus frequency writes were
  accepted, echoed back in the registers, and **ignored**: the shaft ran at whatever the pot was
  set to. Kim fixed it by power-cycling the drive, entering edit mode, setting 02-03 to
  communication and leaving edit mode; after that Modbus commands the speed to within 5 rpm and
  the pot has no effect. **Check 02-03 before a run** — a drive in pot mode will accept a whole
  profile and follow none of it.

- **The pot can be *summed onto* the Modbus reference, not just substituted for it — check it is
  at zero before every run.** Found 2026-08-20 after a mains power cut and drive power-cycle. The
  shaft ran a constant **+3.4 Hz / +200 rpm** above every commanded point: 8.40 Hz commanded read
  700.7 rpm on the tach (11.78 Hz implied) and 15.13 Hz commanded read 1101.2 rpm, with Kim reading
  18.66 Hz on the drive's own display. The offset is **additive, not a scale error** — +200.7 and
  +201.2 rpm at two steps while the ratio moved from 1.40 to 1.22.

  This is nastier than plain pot mode, because **the drive still obeys**: the staircase tracked
  every step change, so a run looks healthy and is simply 200 rpm too fast throughout. Kim turned
  the pot to its bottom stop and the bias vanished — 10.084 Hz commanded then read 590.8 rpm
  against the calibration's 591.6, and after a drive restart 20.00 Hz commanded read 1182.87
  against 1185.0 (−2.1 rpm, 0.2 %). **The tacho was right the whole time**; it was the drive
  output that was high.

  > **The +582 rpm offset in the 2026-08-17 and 2026-08-18 13 h runs is resolved.** It belonged to
  > the old setup — 02-03 on the pot, the old firmware, or both; the two were changed together so
  > they cannot be separated after the fact. Verified gone on 2026-08-19 in two runs, one started
  > directly and one from the UI, matching the calibration within 5 rpm at every step and
  > measuring 591 rpm at the 600 rpm step in *both*. **For those two 13 h runs use `rpm_target`,
  > not `rpm_meas`** — the drive followed its commands (the staircase was tracked through all 31
  > steps), and it was the *old firmware* that over-read by a constant ~582 rpm. The calibration
  > below was measured after flashing 1.1.1 and does not retroactively validate those readings.

- **The profile's 100 rpm step does not turn the bearing.** It commands 1.68 Hz, 3.4 % of rated
  frequency, and the motor has too little torque: measured **0 rpm** on the tach while the drive
  reported running. It recurs 26 times through `Keratech22.json` (the 13 h profile), so those points record a
  *stationary* bearing. Left in place deliberately to keep comparability with earlier runs —
  treat them as stationary-bearing data when analysing. From 3.36 Hz upward the shaft tracks the
  calibration to within 2 rpm.

- **The drive's Modbus registers do not always reflect reality.** Observed 2026-08-19: the drive
  reported `cmd=0.0 ud=0.0` while the shaft turned at 2985 rpm, and accepted and echoed a written
  frequency that had no effect on the output. Writes also intermittently fail outright when
  processes open `/dev/ttyUSB0` in quick succession (`Could not exclusively lock port`), and a
  `stop()` can be reported as successful without stopping the motor. **Verify actuation against
  the tach, never against a readback.**

- **Closed loop hides sensor scale errors.** In closed loop `rpm_meas` always converges to
  the target regardless of sensor accuracy. Only comparing `rpm_meas` against `59.5 × Hz`
  reveals a mis-scaled sensor (e.g. 2 pulses/rev reads 2× high). The rpm-per-Hz factor also
  drifts ~57–60 with load/oil temperature (slip), so treat absolute speed as ±2–3 %.

- **The HDF5 is never flushed, so a power cut costs the whole file — not just the last sweep.**
  Learned the hard way 2026-08-20: mains failed 837 s into a 900 s run and the 634 MB file was
  unrecoverable. `acquire_scope_data.py` never calls `h5py`'s `flush()`, so the superblock still
  said **EOF = 2048 bytes** and carried the "file open for write" flag; patching those two fields
  on a copy did not open it, and `/oe_samples` had never reached disk at all. The telemetry JSONL
  survived to the last tick (it is line-buffered) but ends in NUL padding. On a 13 h run this is
  the difference between losing 20 minutes and losing the night — a periodic `f.flush()` in the
  sweep loop is the fix. **Kim's call 2026-08-20: not worth doing yet**, since it takes a power cut
  to bite. Know the exposure before starting a long unattended run.

- **The 13 h profile is `react/public/config/Keratech22.json`** (`name: "Keratech 22"`, 793 min,
  1561 rpm setpoints). Until 2026-08-20 it was called `KaretTest_Oil1.json` while carrying the name
  "Keratech 22", and a *different*, stale April file called `Keratech22.json` carried the name
  "KaretTest Oil 1" — and the dashboard's hardcoded list labelled the first one "KaretTest Oil 1"
  for good measure. Three crossed copies of the same two names. That is how the stale file kept
  `UL: volt_range 2.0` for four months: a run under the name "Keratech 22" did happen and went
  fine, from the *other* file. Filename, `name`, dashboard label and every existing run's
  `profile_name` now agree; the April file is `KaretTest_Oil1_superseded_20260420.json`, marked
  "do not run". See ticket 0027.

- **The OE sensor drops off the air for 10-14 minutes at a time, and comes back on its own.**
  Measured across the 13 h run of 2026-08-20/21: **six gaps**, at 13:03, 14:54, 18:27, 21:37, 21:55
  and 22:46, lasting 14, 13, 13, 11, 10 and 10 minutes. Every one of them recovered **without
  intervention** — the sampler simply kept retrying every 3 minutes. Net yield **249 captures of
  ~264 possible, 94 %**.

  Do not reach for the reset button on the first failure. It was needed once, on 2026-08-20 at
  midday, when `sample()` timed out at the full 120 s three cycles running and the device stayed
  silent — that is a different signature from these gaps, which show as
  `not advertising after 3 scans over 155s` and clear themselves. **Wait one or two cycles before
  touching the hardware**; a run in progress recovers by itself.

- **Skipped sweeps leave gaps in the HDF5 sweep numbering.** Analysis must iterate the
  existing `sweep_###` groups, not assume contiguous indices.

- **Secret in `config.json`.** An Azure Blob **SAS connection string** is stored in cleartext
  in `py/config.json`. It should be moved to an environment variable / secret store and
  rotated; do not commit it.

- **`control` parameters are per-profile only.** Motor constants such as `rpm_per_hz_guess`
  currently have to be repeated in every profile.

- **Multiple copies / backups exist.** `py/` has kept backups of the main script from earlier
  iterations, and there is at least one older snapshot of this whole tree elsewhere on disk.
  Make sure the file actually deployed to the Pi is the current `acquire_scope_data.py`, and
  that you are editing the current tree.

---

## Load cell & firmware — auto gain scaling

`firmware/src/main.cpp` is **v1.2.5, and it is the version actually flashed on the board**
(flashed 2026-08-25 with the rig apart for load-cell calibration; `INFO` reports `fw=1.2.5`).
`auto_scale(raw)` auto-switches the HX711 gain **128 ↔ 64 ↔ 32** (high gain/resolution for
light loads, drops for heavy) with hysteresis, a 3-read stability gate, **per-gain slope**, an
ADC-saturation guard (`ERR 21`), and it emits `OK AUTOGAIN gain=N` when it switches. v1.2.1 added
the robust tach from ticket 0007 — 1.5 s timeout (rpm → 0 when the signal is lost, no more frozen
value), 8 ms glitch floor, median filter and `TACHDIAG?`.

> **v1.2.0/v1.2.1 were unusable and never ran on the rig: the parser lost the CR strip.** Their
> `loop()` dropped v1.1.0's `if (c == '\r') continue;`, so every host command — all tools send
> `CRLF` — parsed as `"PING\r"` and came back `ERR 10 unknown_command`. **Every** command, so the
> board was dead to `util_tool.py`, `test_runner.py` and the dashboard alike. Fixed in **v1.2.2**,
> which also restores the `ERR 11 line_too_long` guard. If a future edit touches `loop()`, verify
> with a raw `PING` over serial before trusting the board.

> **v1.2.2 reported the switching sample through the wrong gain's slope (fixed in v1.2.3).**
> The HX711 applies a new gain only from its *next* conversion, but `cmd_load()` called
> `auto_scale(raw)` first and then `slope()`, so the one reading in which a switch happened was
> scaled by the gain it was about to move to. Measured on the bench: a settled unloaded reading
> stepped 1778 g -> 889 g on the `OK AUTOGAIN gain=128` line, a clean 2x, and stepped back on the
> next read. It would have looked like the load cell jumping, not like a scaling bug, and it would
> have survived calibration. `cmd_load()` now captures `slope()` **before** `auto_scale()`; verified
> continuous across a switch (1777.9 -> 1777.7 -> 1771.6).

> **Three more defects, all found on hardware the same day (v1.2.4, v1.2.5).**
> - **`SETGAIN` pinned nothing.** `auto_scale()` runs inside every `LOAD?` and overrode the gain
>   that had just been set, so a calibration could not hold a band: pinning 128, 64 and 32 in turn
>   all produced the same ~3.31 M reading because every one of them was dragged back to 64.
>   `SETGAIN <n>` is now **manual mode** (auto_scale returns immediately) and `SETGAIN AUTO` hands
>   control back. `CAL?` reports `mode=auto|manual`. Manual is RAM-only — a reset returns to auto.
> - **Gain 32 is HX711 *channel B*, not the load cell.** Unloaded reads 884096 at gain 128 and
>   443600 at 64 (a clean 2x) but **2177** at 32 — an unconnected input. The auto ladder stepped
>   down into it above 7.5 M and would have read channel B noise as load. The ladder is now
>   128 <-> 64 only, and `SETGAIN 32` returns `ERR 35`.
> - **Tare was one value shared by all gains** while slope was per gain. Measured: zero is 881372
>   counts at 128 and 442361 at 64 — **4.1 kg apart** once scaled, and a run crosses 128 -> 64 as
>   load applies, so one shared tare is wrong in whichever band it was not taken in. v1.2.5 stores
>   `t128`/`t64` alongside `g128`/`g64`; `TARE` and `SETCAL` write the active band's pair.

**Calibration was wiped by the flash and must be redone.** The EEPROM `CAL_VERSION` differs from
v1.1.0's, so `loadCal()` rejected the stored record and `resetCal()` ran: after flashing the board
reports factory defaults (`slope=0.004 tare=0 gain=64`). Slope is stored **per gain** (`g128`,
`g64`, `g32`), so calibrate each gain the rig will actually reach:

```bash
python3 util_tool.py --port /dev/ttyACM0 setgain --gain 128   # or 64, or auto
python3 util_tool.py --port /dev/ttyACM0 calibrate --gain 128 --weight-g 2000
python3 util_tool.py --port /dev/ttyACM0 cal      # CAL? reports slope + tare + gain + mode
```

### The bench calibration of 2026-08-25 — and why its tare is worthless

Measured with the scale unit **off the rig**, weights on the pan, gain pinned per band. Ladder
1/2/4/6 kg (the 6 kg point repeated four times), least-squares over the loaded points:

| | slope | tare (line intercept) | verified against 6 kg |
|---|---|---|---|
| gain 128 | `0.004820812` g/count (207434 counts/kg) | 854943 | 6139 g (+2.3 %) |
| gain 64 | `0.009726785` g/count (102809 counts/kg) | 431818 | 5980 g (-0.3 %) |

The two slopes differ by 1.991 — the factor 2 they must, which is the one clean internal check in
the whole exercise. **Both are ~2.3x from the factory defaults**, so writing them is a large
improvement over what the flash left behind.

> **Kim's accuracy requirement for load is +/-10-15 % (stated 2026-08-25), and we are at +/-3-5 %.**
> So the placement scatter below, alarming as it looks, is comfortably inside what the work needs —
> it is documented so nobody over-claims, not because it must be improved. What is *not* covered by
> that tolerance is the factor-5 question further down: that is force actually reaching the cell,
> not measurement error, and no tolerance makes it safe.

> **The dominant error is mechanical, and it is huge: the same 6 kg placed four times read
> 2023357 / 2056850 / 2137756 / 2144042 counts — a spread of 555 g (9.3 %), sd 275 g.** Electrical
> noise on the same cell is +/- 25 counts (+/- 0.1 g), so **placement is ~2750x worse than the
> electronics**. Treat the slope as good to **+/- 3-5 %, not better** — at the rig's ~62 kg that is
> +/- 3 kg. Anything quoting logged load to tighter than that is quoting noise.

> **The 10 kg weight never reached the cell.** Loaded, it read *below* empty (861841 vs 884533 at
> gain 128, i.e. -104 g). Twice, after repositioning. It rests on the frame beside the pan rather
> than on it. It is excluded from the fit entirely — and it is why the calibrated range is 1-6 kg
> while the rig runs at ~62 kg, a **10x extrapolation** that nothing here validates.

> **Do not use the bench tare in the rig.** Over the session the unloaded raw drifted from 881372
> to 802769 counts — **379 g** — and after calibration an empty pan read -252 g (gain 128) /
> -288 g (64). The zero wanders with the mechanics; only the slope travels with the unit. **After
> remounting the scale unit, tare in place, unloaded, in both bands:**
>
> ```bash
> python3 util_tool.py --port /dev/ttyACM0 setgain --gain 128 && python3 util_tool.py --port /dev/ttyACM0 tare
> python3 util_tool.py --port /dev/ttyACM0 setgain --gain 64  && python3 util_tool.py --port /dev/ttyACM0 tare
> python3 util_tool.py --port /dev/ttyACM0 setgain --gain auto
> ```

**Tared in place 2026-08-25, mounted and unloaded** — `tare` 690680 (gain 128) / 346464 (gain 64),
after which an unloaded rig reads **-5.6 g / -6.5 g**. The band ratio is 1.994, as it must be.

> **Mounted, the mechanics are ~50x quieter than the bench.** Reading spread with the unit in the
> rig is **2.8 g**, against 150 g within a single bench measurement and 555 g between placements of
> the same weights. The instability was the pan and the loose weights, not the cell — the cell
> itself behaves well. It also means the +/- 3-5 % slope uncertainty is a property of *how we
> calibrated*, not of what the rig measures: a calibration performed through the rig's own load
> path would be far better, and that is the route if the load figure ever needs to be trusted
> tighter.

**The rig runs in gain 64.** At 102809 counts/kg, ~62 kg sits near 6.2 M counts — above the 2.5 M
step-up threshold, so the band is stable during a run; the board sits at 128 only while unloaded
and crosses to 64 as load applies. That crossing is exactly why per-gain tare had to exist.

`util_tool.py` gained `setgain` and `calibrate --gain` for this (2026-08-25). `calibrate` reads
`CAL?` before and after and **aborts if the gain auto-switched mid-measurement** — the loaded and
unloaded raw reads would then be on different scales, and nothing else would show it because the
`OK AUTOGAIN` line is skipped as unsolicited.

> **`tare` is a single value shared across all three gains — slope is not.** `cmd_tare()` writes one
> `tare_offset` in raw counts, but raw counts scale with gain, so a tare taken at 128 is wrong by
> roughly 2× once auto-scale drops to 64. Tare at the gain the run will sit at, and treat a
> zero-offset error after a gain switch as expected, not as a fault. Per-gain tare (`t128/t64/t32`)
> is the real fix and is not implemented.

**Host-side parsing is done (2026-08-25).** `util_tool.py`'s `send_cmd(expect_arg=…)` and
`test_runner.py`'s `_read_load()` both read past `OK AUTOGAIN` lines, and `_read_speed()` now does
too — it previously took one line and `_parse_first_float`, so an interleaved `OK AUTOGAIN gain=64`
parsed as a perfectly plausible **64 rpm** sample. It now accepts only the `rpm=` field of a real
`SPEED?` reply. `_read_load()`'s regex also accepts negative masses.

The previous **v1.1.0 (manual gain)** was overwritten in place; it is preserved **in git history**,
not as a second file — `main.cpp` is the only source in `firmware/src/`. To read or roll back:

```bash
git show 07cf7907:firmware/src/main.cpp            # view v1.1.0
git show 07cf7907:firmware/src/main.cpp > firmware/src/main.cpp   # roll back
```

> **Do not keep a second `.cpp` in `firmware/src/`.** `platformio.ini` sets no `build_src_filter`
> for the default env, so PlatformIO compiles *every* source in that directory. A copy of the old
> firmware there brings a second `setup()`/`loop()` and the build fails at link time with duplicate
> symbols. (The separate `seeed-xiao-rp2040-tach-v111` env does set one, onto `src_tach_v111/`.)

**What v1.2.5 still does not have, that v1.1.0 did:** `SETPPR`/`PPR?` — `PULSES_PER_REV` is
hardcoded to 1 (fine: one reflective mark), so `util_tool.py setppr` errors against it.

**Flashing:** `pio run -e seeed-xiao-rp2040 --target upload`. Confirm what is actually *running*
with `INFO` (`fw=`), not by looking at the source. And **only flash when the rig is idle** — the
same board serves the tacho *and* the load cell during a run, so flashing mid-test breaks both.

---

## BLE bearing sensor (OE) — integration (validated against the sensor 2026-08-20)

The **BearingBrain "OE"** sensor's ultrasound mic is sampled periodically *during* a rig run
and stored in the run's HDF5. Implemented under ticket `TEAM/tickets/0001-ble-oe-integration.md`.
**Off by default** — nothing changes until `oe.enabled` is set.

**Config** (`py/config.json`):
```json
"oe": { "enabled": false, "device_address": "", "interval_min": 5, "sensors": [3, 4] }
```
`device_address` is the **MAC as BlueZ sees it** (from `BearingBrain/PiSensorTest/ble_debug_scan.py`),
not the macOS UUID. Sensors 3+4 are `mic_amb` + `mic_mch` (mask `0x18`).

**Pieces:**

| File | Role |
|------|------|
| `py/ble/__init__.py` | Adapter onto the harness. Puts `BearingBrain/PiSensorTest/gateway-service-ble/` on `sys.path` and re-exports `OeDevice`; adds `find_device_by_address()` and `build_mask()`. **The harness stays the single source of the protocol — do not fork it.** |
| `py/oe_sampler.py` | `OeSampler.run()`: async task, one connect→sample→disconnect cycle every `interval_min`, bounded by scan 20 s / connect 45 s / sample 120 s. |
| `py/acquire_scope_data.py` | `main()` starts the task next to the runner; `_drain_oe_queue()` writes captures into `/oe_samples` from the sweep loop. |

**Why the cadence is minutes, not sweeps:** one mic capture is ~2–3 MB and takes 16–120 s over
BLE, against a ~12 s sweep period. A capture can never delay a sweep: the sampler is an asyncio
task in the runner's loop and hands finished captures to the scope thread over a `queue.Queue`,
which the sweep loop drains *non-blocking*. The scope thread stays the only HDF5 writer.

**Failure policy — loud, never fatal.** A failed cycle (sensor not advertising, connect refused,
no data) is logged with its reason, counted, and skipped; the run continues. Counts are reported
when the task stops. If `bleak` or the harness is missing, `py/ble` degrades to `OeUnavailable`
and OE sampling simply does not start — a rig run must never die because an optional BLE sensor
is absent.

**Data layout:** `/oe_samples/oe_000, oe_001, …`, one dataset per channel keyed by **short
alias** — `mic_amb`, `mic_mch` — taken from the vendor's own `test_configs` filenames so the HDF5,
`config.json` and the harness all call a channel the same thing. The full table is
`OE_SENSOR_ALIASES` in `acquire_scope_data.py`; unknown sensor ids fall back to a slug of the
display name. The vendor's display string and numeric id are kept as **dataset** attributes
(`sensor_name`, `sensor_id`), together with **`sample_rate_hz` and `sample_rate_source`** — the
device does not send a rate with the data, so without this a mic capture is an array with no time
axis and no way to recover one. The rate comes from `config.json → oe.sample_rate_hz`; if it is
absent the attribute is simply left off rather than guessed.

> **The rate is 80 kHz — confirmed by Kim 2026-08-20.** The vendor's `pdm_mic_config.json`
> (matching our `device_serial OE00031204100074`) says **100 kHz**, and it is **wrong** for this
> custom PDM firmware; the emulator readme's *"upto 80KHz"* is the accurate one. `config.json`
> now stamps 80000 — **do not restore 100000 from the vendor file.**
>
> **Captures taken before 2026-08-20 carry `sample_rate_hz = 100000` and their frequency axes are
> 25 % high.** That is the three OE validation runs (`20260820_091646`, `20260820_093823`,
> `20260820_103317`). Rescale, or rewrite the attribute, before reading a frequency off them.

Group attributes are `t_start`, `t_stop`, **`tick_start`**,
`device_name`, `device_address`, `mask`, `sensors`, `near_sweep` (the sweep index it sits
between) and the same `telem_*` stamps the sweeps carry. With `enabled: false` the group is
never created, so existing files keep their exact layout.

**One time axis for both streams (ticket 0025).** `main()` takes a single `monotonic()` origin and
hands it to both the scope loop and the sampler, so every sweep carries `tick` and every capture
carries `tick_start`, in run-relative seconds from the same zero. Sample *i* of a capture sits at
`tick_start + i / sample_rate_hz`. The caveat is stamped into the file itself as the `/oe_samples`
attributes `tick_definition` and `tick_accuracy`: `tick_start` is the host's `sample()` call, not
the device's record-start, so it is good to sub-second and **not** valid for sample-level (10 us)
overlay against a waveform.

> **`near_sweep` is a coarse label, not a time — use `tick`/`tick_start`.** Measured on run
> `20260820_103317`: every capture *began* ~21 s **before** the sweep it is labelled with (5.80 vs
> 28.34, 187.44 vs 208.34, 366.27 vs 388.34, 548.29 vs 568.35). That is by design — a capture takes
> ~16 s and is drained by the sweep loop afterwards, so it lands on the next sweep to complete —
> but the shaft accelerates between steps, so the label can name an operating point the first
> seconds of the recording were not taken at. `oe_001` is stamped 1101 rpm and starts before that
> step began.

**Fixed in `oe_device.connect()` on the way in:** `start_notify(UART_CHAR_UUID, …)` was
commented out. Since `oe_protocol` only ever *writes* (there is no `read_gatt_char` anywhere),
nothing could reach `notification_handler` → `OeProtocol.push()`, so no device reply could be
parsed **on any platform** — not just Linux. It is now enabled, placed *after* service discovery
as the code's own comment requires, and the redundant second `connect()` and the 3 s
"Windows BLE stack" wait are gone.

> **A held BLE link survived a full 13 h run (ticket 0026).** `keep_connected: true` opened one
> session and carried 249 captures through 2026-08-20/21. The reconnect path fired **once**, at
> 18:30, on `device returned no sample data` after five and a half hours on one link: it dropped the
> session, re-established it and retried inside the same cycle, exactly as designed. That path had
> been unit-tested and never exercised on hardware until then. `keep_connected: false` remains the
> documented escape hatch and restores the per-capture session.

> **Verified against the real sensor 2026-08-20** (`03:24:71:01:04:54`, `OE00031204100074`), over
> three 15-minute runs with the motor turning. `/oe_samples` fills, and the design's central claim
> holds: **the sweep skip count stayed at zero** while ~149 k-point mic captures ran concurrently
> with scope digitising, so a capture never delayed a sweep.
>
> The one thing that did not work first time was cadence. In `20260820_091646` only **2 of 6**
> cycles produced data — the device sleeps of its own accord (its `pdm_mic_config.json` carries
> `sleep_time: 30`) and **a sleeping device does not advertise**, so the 20 s scan window gave up
> almost immediately. Raising the scan timeout to 45 s and retrying inside the cycle (ticket 0024)
> took the retest to **5 of 5, zero failures**, on the cadence to the second. See tickets 0021,
> 0024 and 0025.

---

## Next steps

1. **Make the tachometer robust** — reflective-tape mark + re-teach the OGT500, then validate
   `rpm_meas ≈ 59.5 × Hz` across the whole temperature sweep. Add a firmware timeout that
   zeros rpm when no edges arrive (so a lost signal reads 0 instead of freezing).
2. **Centralize motor constants** — let `control` fall back to `config.json` (profile still
   overrides) so `rpm_per_hz_guess` isn't duplicated per profile.
3. **Optional true-speed readout on the dashboard** — display `59.5 × commanded Hz`, which is
   correct even when the tacho misbehaves.
4. **Reliability tuning if zero-skip is ever required** — reduce points toward ~350 k or raise
   `sweep_retries` / back-off.
5. **Move the Azure SAS out of `config.json`.**
6. **Confirm rpm/Hz empirically** with the now-working sensor and refine the 59.5 factor if a
   temperature-dependent value is warranted for the analysis.
7. **Load-cell: tare in the rig, then judge whether the bench slope is good enough.** Firmware
   v1.2.5 is flashed and the bench slope is written per gain (see "Load cell & firmware"). Two
   things remain, in order: **(a)** tare both bands once the scale unit is remounted and unloaded —
   the bench zero is meaningless and the board currently reads ~-270 g empty; **(b)** decide whether
   +/- 3-5 % on load is acceptable for the analysis. If it is not, the fix is not more weights on
   the pan — it is loading the cell through the rig's own load path, because placement, not
   electronics, is what limits us.
8. **BLE OE sensor integration** — **validated against the real sensor 2026-08-20** (tickets 0001,
   0021, 0024, 0025): `/oe_samples` fills, 5 of 5 capture cycles succeed, sweeps stay at zero
   skips, and both streams share one time axis. Remaining before a 13 h run: set
   `oe.interval_min` back to **5** (it is at 3 from the short tests), and pick a profile whose
   bottom step actually turns the bearing — the 100 rpm step does not.
9. **A 13 h run with all three scope channels live is in the archive** — `20260820_125647`,
   uploaded to `eceherning` and size-verified, 34.75 GB. 3778 sweeps with exactly one lost
   (`sweep_247`, 0.026 %), 249 OE captures on the shared tick axis, all thirteen temperature steps
   from 40 to 100 C, and the **first full run since 2026-08-19 with the UL probe fitted**, so UL,
   AE and SP all carry real data. Use `py/tools/upload_to_azure.py` for the next one.
10. **Flush the HDF5 periodically** — see the known issue above. **Deliberately deferred by Kim
   2026-08-20**: the exposure is a mains failure, which is rare, and he judged it not worth the
   change before this run. Left recorded so the cost is known if it happens again.
11. **Fix the dashboard's polling before the next long run** (ticket 0028) — it pulls 62 KB
   twice a second, 58 KB of it log lines no component renders, and the browser tab's renderer is
   eventually killed. Reloading recovers it and the run is unaffected, but it blinds the operator.

---

## Data model (quick reference)

HDF5 per run:
- `/metadata/` — `scope_settings`, `bearing`, `lubricant`, `test_parameters`, IDN, timestamps.
- `/sweeps/sweep_000, sweep_001, …` — each has per-channel groups with `time` + `voltage`
  datasets and channel scaling attributes, plus `telem_*` attributes (RPM, drive Hz,
  temperature, load, elapsed, step) captured at that sweep, and `tick` — run-relative seconds
  on the same origin as the OE captures (ticket 0025).
- `/oe_samples/oe_000, …` — BLE mic captures, one dataset per channel, with `tick_start` on that
  same axis. See "BLE bearing sensor (OE)".

Telemetry JSONL (from the runner): one `run_header`, then per-tick `sample` records
(`rpm_target`, `rpm_meas`, `vfd_cmd_hz`, temperatures, load…), then a `run_end` with the
stop reason.
