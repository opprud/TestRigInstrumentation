# OE ultrasound-mic sensor (BearingBrain) — description, use, test, gotchas

Consolidated reference for the BearingBrain **OE** BLE sensor and its integration into rig runs.
Scattered detail lives in tickets 0001 / 0019 / 0022 / 0024 / 0025 / 0026 and in `config.json`; this
document is the single place to start.

## What it is
- A BLE device (`OE00031204100074`, BlueZ MAC `03:24:71:01:04:54`) carrying several channels; the
  rig uses the **two PDM ultrasound microphones**:

  | dataset | sensor_id | what |
  |---|---|---|
  | `mic_amb` | 3 | Ambient Microphone (reference) |
  | `mic_mch` | 4 | Machine Microphone (near the bearing) |

  Mask `0x18` = sensors 3+4. The device also exposes battery, temperatures, accelerometers, gyro and
  magnetometer (ids 0–18) — see `BearingBrain/PiSensorTest/test_configs/` — but runs sample the mics.
- Values are **raw PDM counts** (arbitrary units, roughly zero-mean) — **not volts**.
- **Sample rate: 80 kHz** (both mics). The vendor `pdm_mic_config.json` says 100000 and is **wrong**
  for this custom PDM firmware — do not restore it from that file.
- One capture is a **~0.93 s burst** (~74 k samples / 80 kHz), then ~18 s to transfer over BLE.

## How to use (config)
`py/config.json` → `oe` block:
- `enabled` — false by default; true adds an `/oe_samples` group to the run HDF5.
- `device_address` — the **BlueZ MAC** from `ble_debug_scan.py` (Linux uses the MAC, not the macOS
  UUID).
- `interval_min` — capture cadence in minutes (the 13 h run used **3 min**).
- `sensors` — `[3, 4]`.
- `keep_connected` — default **true** (ticket 0026): holds the BLE link open between captures so the
  device never sleeps. Set false to fall back to the scan-based path (ticket 0024), which is
  hardware-proven; keep_connected's reconnect path is field-tested only lightly (fired once in 13 h).
- `sample_rate_hz` — `{"3": 80000, "4": 80000}`, stamped onto every dataset.

The sampler runs as an async task inside the acquire loop and drains captures into the HDF5. It is
created **only in the auto path** (a profiled run), so a manual-mode run does not sample OE.

## How to test
1. `ble_debug_scan.py` → confirm the device advertises and get its MAC.
2. A short **15-min integration run** (profile `OeIntegration_15min.json`, motor turning so the auto
   path runs). Pass criteria: all cycles yield data · **0 sweep skips** · **0 reconnects**.
3. `py/test_oe_hdf5.py` — unit tests for the HDF5 write path (no BLE / sensor / scope needed).
4. A green 15 min is necessary but **not** proof for a 13 h run (sleep windows, held-link drift) — a
   longer soak is worth it before betting a night.

## Data layout in the HDF5
```
/oe_samples/oe_NNN/
    mic_amb   (~74 k float64)   attrs: sensor_name, sensor_id, sample_rate_hz, sample_rate_source
    mic_mch   (~75 k float64)   "
  group attrs: tick_start, near_sweep, t_start, t_stop, mask, sensors, device_*, telem_* (rpm/temp/mass/step)
/oe_samples  group attrs: tick_definition, tick_accuracy
```
- **Timing:** `tick_start` = run-relative seconds from the **same origin as `/sweeps` tick**; sample
  *i* is at `tick_start + i / sample_rate_hz`. Use `tick`/`tick_start` to align OE with scope sweeps —
  **not** `near_sweep`, which is a coarse label ~21 s off (captures start ~21 s before their labelled
  sweep; on 59 s plateaus that can land in the previous step).
- `tick_start` is good to **sub-second only** (BLE round-trip + firmware; the sensor returns no
  device timestamp) — **not** valid for sample-level (10 µs) overlay on scope waveforms.

## Gotchas (the traps that cost time)
- **`read_config` times out BY DESIGN — it is NOT a liveness probe.** On this custom firmware the
  config-read is deliberately skipped; a "wedged / vendor-broken sensor" (2026-08-20, ~1.5 days)
  turned out to be a healthy sensor answering everything except that one call. **Use `sample()`.**
- **80 kHz, not 100 kHz** (vendor config wrong). The "samples fill only ~5 % of the t_start..t_stop
  window / implied ~4 kHz" a visualiser may flag is a **red herring** — it is a short burst plus a
  long transfer, not a low rate.
- **Self-healing gap vs genuine wedge — different signatures, different responses.** Transient gaps
  (`not advertising after ~3 scans over ~155 s`, 10–14 min) **recover on their own** — do NOT reach
  for the reset button; on an unattended night it is unavailable anyway. The genuinely-wedged case is
  `sample()` timing out the full 120 s for three consecutive cycles while the device is still
  connectable.
- **No remote reset over BLE** (ticket 0019). The firmware/OTA path could reboot it but needs a
  **signed image from BearingBrain**; the app-facing UART path is exactly what a wedge kills. Physical
  button, or a signed image from the vendor.

## First results — the sensor delivers, and it sees the lubrication regime (2026-08-21)
Validated on the 15-min test and the 13 h run `20260820_125647` (249 captures):
- **Usable, structured signal:** machine mic ~2× ambient; energy tracks RPM (`rms_mch ~ rpm+rpm²`,
  R² 0.77, corr +0.88).
- **A strong component BEYOND speed, tracking temperature.** The rpm-model residual correlates **+0.78
  with temperature**, and at every fixed speed the mic energy rises **1.9–3.5× from 40 → 100 °C**
  (corr 0.7–0.96):

  | rpm | 40 °C → ~95 °C | factor |
  |---|---|---|
  | 500 | 71 → 250 | ×3.5 |
  | 1000 | 218 → 481 | ×2.2 |
  | 2000 | 531 → 1337 | ×2.5 |
  | 2500 | 761 → 1635 | ×2.2 |

  **Interpretation:** oil viscosity falls with temperature → thinner lubricant film → more asperity
  contact / less damping → more ultrasound emission. **The OE mic tracks the lubrication regime, not
  just speed** — the signal an endurance test wants.
- **Caveat:** temperature and elapsed time are confounded in this run (temp rose monotonically), so a
  reversible **thermal/viscosity** effect cannot be fully separated from an irreversible
  **run-in/degradation** one. Step-by-step temp correlation + the physics point to thermal. **To
  separate them, a future run should decouple temp and time** — hold temp constant over hours, or
  cycle it up/down and watch whether the mic energy reverses (viscosity) or persists (degradation).
