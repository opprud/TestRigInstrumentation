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

- **The scope wedges intermittently at high resolution.** Symptoms in the log:
  `step=connect: TimeoutError`, `Empty PRE?`, `DATA? … timed out`, occasional
  `ConnectionRefused`. The resilience machinery absorbs it (sub-1 % loss), but it is not
  eliminated. Lower the point count or increase `sweep_retries` if zero loss is required.

- **The optical tachometer (ifm OGT500) is the weak link.** Historically it over-read
  (multiple reflections → extra pulses/rev), reported spurious values at standstill, and
  saturated near the top of the range. The firmware computes rpm from the interval between
  the last two pulses and has **no timeout**, so when the sensor stops producing edges the
  reading **freezes at the last value** — this looks like a stuck reading, not a zero. Teach
  the OGT500 as: reflective mark in front → **OUT ON**, dark shaft in front → **OUT OFF**;
  verify the yellow LED blinks exactly once per revolution. Check it live with
  `python3 util_tool.py --port <PORT> speed` (watch `pulses` increment by one per turn) and
  set pulses-per-rev with `setppr` if the shaft has more than one mark. Prefer open-loop
  control until the mark is robust.

- **Closed loop hides sensor scale errors.** In closed loop `rpm_meas` always converges to
  the target regardless of sensor accuracy. Only comparing `rpm_meas` against `59.5 × Hz`
  reveals a mis-scaled sensor (e.g. 2 pulses/rev reads 2× high). The rpm-per-Hz factor also
  drifts ~57–60 with load/oil temperature (slip), so treat absolute speed as ±2–3 %.

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

---

## Data model (quick reference)

HDF5 per run:
- `/metadata/` — `scope_settings`, `bearing`, `lubricant`, `test_parameters`, IDN, timestamps.
- `/sweeps/sweep_000, sweep_001, …` — each has per-channel groups with `time` + `voltage`
  datasets and channel scaling attributes, plus `telem_*` attributes (RPM, drive Hz,
  temperature, load, elapsed, step) captured at that sweep.

Telemetry JSONL (from the runner): one `run_header`, then per-tick `sample` records
(`rpm_target`, `rpm_meas`, `vfd_cmd_hz`, temperatures, load…), then a `run_end` with the
stop reason.
