# BearingBrain OE Sensor — BLE Test (Pi)

Minimal, self-contained harness for **bench-testing the BearingBrain "OE" bearing sensor
over Bluetooth Low Energy** on this machine. It scans for the sensor, connects, requests
samples from its sensors, and saves the results as JSON.

This is a trimmed extract of the full **BearingBrain Gateway Emulator** — only the pieces
needed to sample a device are here. The full project (production gateway service, firmware
update, MQTT, extra services) lives elsewhere at `software/BearingBrain/BearingBrainGWEmulator 1/`
and is **not** required for testing.

## The sensor

The "OE" device (advertises as e.g. `OE00031204100074`) is a bearing-condition sensor with
an **ultrasound microphone** (the signal of primary interest) plus accelerometers, gyros, a
magnetometer, and temperature/battery. Communication is a custom **UART-over-BLE** protocol
(GATT), driven from Python with **bleak**.

- UART service/char UUID base: `00002760-08c2-11e1-9073-0e8ac72e0254`
- 19 sensor channels (used by `run_sensor_tests.sh`):

| ID | Sensor | ID | Sensor | ID | Sensor |
|----|--------|----|--------|----|--------|
| 0 | battery | 7 | adxl362_y | 14 | ism330_gyro_y |
| 1 | temp_amb | 8 | adxl362_z | 15 | mmc5603_x |
| 2 | temp_mch | 9 | ism330_acc_x | 16 | mmc5603_y |
| 3 | mic_amb | 10 | ism330_acc_y | 17 | mmc5603_z |
| 4 | mic_mch | 11 | ism330_acc_z | 18 | drv425 |
| 5 | adxl1002 | 12 | ism330_gyro_x | | |
| 6 | adxl362_x | 13 | ism330_gyro_y | | |

## Layout

```
run_sampler.py            Entry point: scan → connect → sample → save JSON
ble_debug_scan.py         BLE scan utility (find the device + its address)
run_sensor_tests.sh       Runs run_sampler.py over all 19 test_configs (PASS/FAIL)
plot_samples.py           Plot a saved samples JSON (needs plotly)
requirements_local.txt    bleak>=0.22.3, numpy, plotly
gateway-service-ble/      The 3 protocol modules the sampler imports:
    oe_device.py            BLE connect / notify / disconnect (BleakClient)
    oe_protocol.py          OE command protocol (sample/config/sleep/firmware)
    utils.py                Data parsing + sensor-name helpers (stdlib only)
test_configs/             19 per-sensor sampling configs (00_battery … 18_drv425)
samples/                  Output JSON is written here
```

`run_sampler.py` adds `gateway-service-ble/` to `sys.path` and imports `oe_device` + `utils`;
`oe_device` → `oe_protocol` → `utils`. `utils.py` is stdlib-only, so there are no other
local dependencies.

## Setup on the Pi

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_local.txt          # bleak, numpy, plotly
```
BLE on Linux goes through **BlueZ** over D-Bus. Make sure it is running and the adapter is
powered:
```bash
systemctl status bluetooth        # should be active
bluetoothctl show                 # adapter present, Powered: yes
```
No root is normally needed for scanning/connecting via BlueZ, but if scans return nothing,
check that the user can talk to BlueZ (bluetooth group) and that no other process holds the
adapter.

## Running the test

```bash
# 1) Find the device (note its name and address)
python ble_debug_scan.py

# 2) Sample it (interactive pick, or target it directly)
python run_sampler.py                              # scan + pick interactively
python run_sampler.py --address AA:BB:CC:DD:EE:FF  # connect by MAC (see gotcha below)
python run_sampler.py --sensors 0 1 2              # battery + both temperatures
python run_sampler.py --all-sensors                # all 19
python run_sampler.py --read-configs               # read device config only, no sampling

# 3) Full per-sensor sweep (PASS/FAIL for each of the 19), by address or serial
./run_sensor_tests.sh -a AA:BB:CC:DD:EE:FF
./run_sensor_tests.sh -d OE00031204100074
```
Results are written to `samples/<device>_<timestamp>.json`. Plot one with
`python plot_samples.py samples/<file>.json`.

## Pi-specific gotchas (read before debugging)

- **This code was written/tested on macOS** (see the header in `run_sampler.py`). bleak is
  cross-platform, so it runs on the Pi over BlueZ — but the platform differences below matter.
- **Address format:** macOS identifies devices by a random **UUID**; **Linux/BlueZ uses the
  real MAC address**. On the Pi, connect with `--address <MAC>` / `-a <MAC>` (get the MAC from
  `ble_debug_scan.py` or `bluetoothctl scan on`).
- **"Packet" rename:** after the first connection the device may re-advertise as `Packet`
  instead of `OE…`. When that happens, connect by **MAC address**, not by name.
- **`run_sensor_tests.sh` hardcodes `.venv/bin/python`** — create the virtualenv at `.venv/`
  in this folder (as above), or edit `PYTHON=` in the script.
- **`samples/` must exist** for output — it is included in this folder.
- **Passive scanning:** `ble_service.py` in the full project uses passive scan mode; the
  standalone `ble_debug_scan.py` / `run_sampler.py` use active discovery, which is what you
  want for bench testing.

## What was intentionally left out

The production gateway (`gateway-service-ble/ble_service.py`, `device_handler.py`, `main.py`,
`interface.py`) and the sibling services (`gateway-service-device-configs`,
`gateway-service-measurement-creator`) are **not** here — they are the systemd-managed gateway
(watchdog, MQTT, firmware rollout) and are not needed to sample a device on the bench. If you
need them, they are in the full emulator at `software/BearingBrain/BearingBrainGWEmulator 1/`.

## Likely next steps

- Confirm BlueZ passive/active scan actually sees the OE device on this adapter.
- Do one `--read-configs` to verify the connection + protocol before a full `run_sensor_tests.sh`.
- The ultrasound mic channels (`mic_amb`/`mic_mch`, IDs 3–4) are the primary interest — sample
  those and inspect with `plot_samples.py`.
