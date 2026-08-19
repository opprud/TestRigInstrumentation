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
  the speed of record — it is better than reconstructing from drive frequency.

- **The frequency reference source is selected by drive parameter 02-03 — pot *or* communication,
  not both.** Until 2026-08-19 it was set to the analog pot, so Modbus frequency writes were
  accepted, echoed back in the registers, and **ignored**: the shaft ran at whatever the pot was
  set to. Kim fixed it by power-cycling the drive, entering edit mode, setting 02-03 to
  communication and leaving edit mode; after that Modbus commands the speed to within 5 rpm and
  the pot has no effect. **Check 02-03 before a run** — a drive in pot mode will accept a whole
  profile and follow none of it.

  > **The +582 rpm offset seen in the 2026-08-17 and 2026-08-18 13 h runs is NOT yet explained.**
  > It was blamed on the sensor, then on VFD EMI, then on the pot adding to the command — all three
  > wrong. A source *selection* cannot produce it: with the pot selected the speed would be
  > constant rather than tracking the profile's staircase, and with communication selected the
  > speed should have been correct. Those runs tracked the staircase **and** sat 582 rpm high.
  > Until this is settled, treat their speeds as uncertain and use the logged `rpm_meas`, which the
  > calibration above shows is trustworthy. **Next step: a short profiled run now that 02-03 is
  > correct and firmware 1.1.1 is flashed — does `rpm_meas` match `rpm_target`?**

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

`firmware/src/main.cpp` **is now v1.2.0 (auto gain scaling)** — this is the chosen firmware going
forward. `auto_scale(raw)` auto-switches the HX711 gain **128 ↔ 64 ↔ 32** (high gain/resolution for
light loads, drops for heavy) with hysteresis, a 3-read stability gate, **per-gain calibration**, an
ADC-saturation guard (`ERR 21`), and it emits `OK AUTOGAIN gain=N` when it switches.

The previous **v1.1.0 (manual gain)** was overwritten in place; it is preserved **in git history**,
not as a second file — `main.cpp` is the only source in `firmware/src/`. To read or roll back:

```bash
git show 07cf7907:firmware/src/main.cpp            # view v1.1.0
git show 07cf7907:firmware/src/main.cpp > firmware/src/main.cpp   # roll back
```

> **Do not keep a second `.cpp` in `firmware/src/`.** `platformio.ini` sets no `build_src_filter`,
> so PlatformIO compiles *every* source in that directory. A copy of the old firmware there brings a
> second `setup()`/`loop()` and the build fails at link time with duplicate symbols.

v1.1.0 has manual `SETGAIN 64|128`, `SETPPR`/`PPR?`, and a 100 µs glitch filter in the tach ISR
(`if (dt > 100) …`) that v1.2.0 does **not**.

**Tradeoffs v1.2.0 carries** (fine for the current single-mark rig, but know them before you flash):
- No `SETPPR`/`PPR?` — `PULSES_PER_REV` is hardcoded to 1 (OK: one reflective mark). `util_tool.py
  setppr` will error against it.
- No 100 µs ISR debounce.
- Still **no tach timeout** — a lost tacho signal freezes at the last value (see the tacho known-issue).

**Renaming the source does NOT reflash the board.** The RP2040 keeps running whatever was last
flashed (still v1.1.0's behaviour) until you build + upload v1.2.0 (`pio run --target upload`).
Confirm what is actually *running* with the `INFO` command (reports `fw=`), not by looking at the
source. And **only flash when the rig is idle** — the same board serves the tacho *and* the load
cell during a run, so flashing mid-test breaks both.

**After flashing, on the Python side:** with auto-scale live, `LOAD?` produces unsolicited
`OK AUTOGAIN gain=N` lines — verify `util_tool.py` / `test_runner.py`'s response parser **skips**
non-matching lines, or a gain switch mid-read will desync it. Then **re-TARE and re-run SETCAL per
gain** — calibration is gain-dependent.

---

## BLE bearing sensor (OE) — integration (built, awaiting hardware test)

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

**Data layout:** `/oe_samples/oe_000, oe_001, …`, one dataset per channel named by sensor
(`Ambient Microphone`, `Machine Microphone`), plus attributes `t_start`, `t_stop`,
`device_name`, `device_address`, `mask`, `sensors`, `near_sweep` (the sweep index it sits
between) and the same `telem_*` stamps the sweeps carry. With `enabled: false` the group is
never created, so existing files keep their exact layout.

**Fixed in `oe_device.connect()` on the way in:** `start_notify(UART_CHAR_UUID, …)` was
commented out. Since `oe_protocol` only ever *writes* (there is no `read_gatt_char` anywhere),
nothing could reach `notification_handler` → `OeProtocol.push()`, so no device reply could be
parsed **on any platform** — not just Linux. It is now enabled, placed *after* service discovery
as the code's own comment requires, and the redundant second `connect()` and the 3 s
"Windows BLE stack" wait are gone.

> **Not yet verified against the sensor.** BlueZ, bleak 3.0.2 and scanning are confirmed working
> on the Pi (25 devices seen), and the HDF5 path is unit-tested, but no OE device has been
> connected. Get the MAC from `ble_debug_scan.py`, set `device_address`, `enabled: true`, and
> confirm `/oe_samples` fills and the sweep skip count is unchanged against a no-OE reference run.

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
7. **Load-cell auto gain scaling** — `main.cpp` is now v1.2.0 (see "Load cell & firmware").
   Remaining: flash it when the rig is idle (`pio run --target upload`), make the `LOAD?` parser
   tolerant of `OK AUTOGAIN` lines, and re-TARE + SETCAL per gain. Optional: fold
   `SETPPR`/debounce/tach-timeout back in from the preserved v1.1.0.
8. **BLE OE sensor integration** — built (ticket 0001, `enabled: false`). Remaining: connect a
   real OE sensor, take its MAC from `ble_debug_scan.py`, enable it, and confirm `/oe_samples`
   fills without changing the sweep skip count (see "BLE bearing sensor (OE)").

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
