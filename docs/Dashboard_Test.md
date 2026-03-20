# ForeverBearing — Test Rig Instrumentation

System for control and data acquisition for bearing endurance tests. Combines oscilloscope acquisition (HDF5), motor control (VFD), temperature control (Omron E5CC), load sensor and tachometer (RP2040), and power control (Shelly Pro 4PM).

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Hardware](#hardware)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running a Test](#running-a-test)
- [Shelly Power Control](#shelly-power-control)
- [File Structure](#file-structure)
- [HDF5 Data Format](#hdf5-data-format)

---

## System Architecture

```
Raspberry Pi
├── py/
│   ├── api_server.py          ← FastAPI backend (port 8000)
│   ├── acquire_scope_data.py  ← Oscilloscope + HDF5 acquisition
│   ├── test_runner.py         ← Test sequence control (RPM/temp PI control)
│   ├── config.json            ← Scope and hardware configuration
│   └── shelly_config.json     ← Shelly MQTT configuration
└── react/
    └── src/                   ← React dashboard (port 3000)
```

**Data flow during a test:**
```
acquire_scope_data.py  →  HDF5 file (scope sweeps + telemetry)
test_runner.py         →  JSONL file (RPM/temp samples)
api_server.py          →  REST API → React Dashboard (live telemetry)
```

---

## Hardware

| Device | Interface | Function |
|---|---|---|
| Keysight MSO-X 2024A | TCP/IP (port 5025) | Oscilloscope — AE + UL channels |
| RS PRO RS510 VFD | RS485/Modbus (slave 3) | Motor control |
| Omron E5CC | RS485/Modbus (slave 2) | Temperature control |
| Seeed XIAO RP2040 | USB Serial | Load sensor + Tachometer |
| Shelly Pro 4PM | MQTT | Power control (4 channels) |

---

## Quick Start

### 1. Clone and start the system

```bash
git clone <repo>
cd ForeverBearing/sw/TestRigInstrumentation
bash start_system.sh
```

Open browser:
- **Dashboard:** http://localhost:3000
- **Power control:** http://localhost:3000/shelly
- **API docs:** http://localhost:8000/docs

### 2. Select test profile in UI

1. Go to http://localhost:3000
2. Select profile in "Configuration File" (e.g. *First-Oil Validation*)
3. Press **Start**
4. Monitor live telemetry: RPM, temperature, load
5. Press **Stop** to end early — HDF5 file is saved automatically

### 3. Run test from command line

```bash
cd py
source .venv/bin/activate

# With test profile (automatic RPM + temp)
python3 acquire_scope_data.py config.json ../react/public/config/first-oil.json

# Manual mode (set RPM/temp yourself on VFD/Omron)
python3 acquire_scope_data.py config.json
```

---

## Installation

### Requirements

- Python 3.10+
- Node.js 18+
- `mosquitto` client (optional, for debug)

### Automatic installation

`start_system.sh` handles everything automatically:

```bash
bash start_system.sh
```

The script:
1. Creates Python virtual environment (`py/.venv`)
2. Installs Python dependencies from `requirements.txt`
3. Starts API server (port 8000)
4. Installs Node.js dependencies (first time)
5. Starts React dev server (port 3000)

### Manual installation

```bash
# Python
cd py
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# React
cd ../react
npm install
npm run dev
```

### Python dependencies (`requirements.txt`)

```
numpy, h5py, pyserial, pyvisa-py, pymodbus, fastapi, uvicorn, paho-mqtt
```

---

## Configuration

### `py/config.json`

Main configuration for scope, channels and test:

```json
{
  "scope_ip": "169.254.172.2",        ← Scope IP address
  "channels": [
    {"name": "AE",  "source": "CHAN1", "enabled": true},
    {"name": "UL",  "source": "CHAN2", "enabled": true}
  ],
  "store": {
    "output_file": "data/test.h5"     ← Output folder
  },
  "bearing": { ... },                  ← Bearing parameters (stored in HDF5)
  "lubricant": { ... }                 ← Lubricant data (stored in HDF5)
}
```

### Test profiles (`react/public/config/`)

| File | Description | Duration |
|---|---|---|
| `first-oil.json` | First oil test — RPM 500→3000 rpm | 170 min |
| `test-profile.json` | Standard test — RPM 1000→2000 rpm | 15 min |
| `endurance-profile.json` | Endurance test — 1800→2200 rpm | 61 min |
| `high-stress-profile.json` | High stress — up to 3200 rpm | 14 min |
| `lub1_validation.json` | Lubricant validation | 110 min |

**Profile structure:**

```json
{
  "name": "My Test",
  "duration_minutes": 15,
  "setpoints": {
    "rpm": [
      {"time_sec": 0,   "value": 1000},
      {"time_sec": 600, "value": 2000}
    ],
    "temperature": [
      {"time_sec": 0,   "value": 40},
      {"time_sec": 300, "value": 60}
    ]
  },
  "acquisition": {
    "scope_points": 250000,
    "interval_sec": 3,
    "samples_per_step": 3
  },
  "scope_channels": {
    "AE": {"timebase_range": 0.02, "volt_range": 1.0, "coupling": "DC"},
    "UL": {"timebase_range": 0.02, "volt_range": 0.8, "coupling": "DC"}
  }
}
```

> **Important:** `duration_minutes` must cover the maximum `time_sec` in setpoints.
> Valid `volt_range` values for MSO-X: 0.016, 0.04, 0.08, 0.2, 0.4, 0.8, 1.0, 2.0, 4.0, 8.0 (V)

### `py/shelly_config.json`

```json
{
  "mqtt": {
    "host": "185.81.165.190",
    "port": 1883,
    "username": "mqttuser",
    "password": "3711"
  },
  "device_id": "shellypro4pm-c8f09e84cdf8",
  "channels": [
    {"id": 0, "name": "Heater",    "description": "Oil heater"},
    {"id": 1, "name": "Channel 2", "description": "Spare"},
    {"id": 2, "name": "Channel 3", "description": "Spare"},
    {"id": 3, "name": "CPU",       "description": "Raspberry Pi"}
  ]
}
```

---

## Running a Test

### From UI

1. Open http://localhost:3000
2. Select profile → **Start**
3. Live telemetry updates every second
4. HDF5 file is shown in "HDF5 Data Log" with file size and sweep counter
5. **Stop** saves the file and stops motor + scope

### From command line

```bash
cd py && source .venv/bin/activate

# With profile (automatic)
python3 acquire_scope_data.py config.json ../react/public/config/test-profile.json

# With debug output
python3 acquire_scope_data.py config.json ../react/public/config/test-profile.json --debug

# Manual (no profile)
python3 acquire_scope_data.py config.json
```

### Output

Files are saved in `data/runs/<timestamp>/`:

```
data/runs/20260319_142500/
├── scope_20260319_142500.h5           ← HDF5 scope data + metadata
└── telemetry_20260319_142500_*.jsonl  ← Telemetry log
```

---

## Shelly Power Control

### Web UI

Open http://localhost:3000/shelly

- Toggle buttons for on/off per channel
- Live power (W), current (mA), voltage (V)
- Total active power at the top

### From command line (another PC)

```bash
pip install paho-mqtt
python3 shelly_control.py --status

python3 shelly_control.py --on cpu        # Turn on CPU (channel 3)
python3 shelly_control.py --off heater    # Turn off Heater (channel 0)
python3 shelly_control.py --on 2          # Turn on channel 2
```

> Used to restart the Raspberry Pi if the CPU channel is switched off.

---

## HDF5 Data Format

Open files with [myHDF5](https://myhdf5.hdfgroup.org) or Python:

```python
import h5py
with h5py.File("scope_20260319.h5", "r") as f:
    # Metadata
    bearing = dict(f["metadata/bearing"].attrs)
    scope   = dict(f["metadata/scope_settings/AE"].attrs)

    # Sweep data
    voltage = f["sweeps/sweep_000/AE/voltage"][:]
    time    = f["sweeps/sweep_000/AE/time"][:]

    # Telemetry per sweep
    rpm  = f["sweeps/sweep_000"].attrs["telem_rpm_meas"]
    temp = f["sweeps/sweep_000"].attrs["telem_omron_pv_c"]
```

**Structure:**

```
scope_*.h5
├── metadata/
│   ├── bearing/          ← Bearing parameters (from config.json)
│   ├── lubricant/        ← Lubricant data (from config.json)
│   ├── scope_settings/
│   │   ├── AE/           ← Channel settings (range, coupling etc.)
│   │   └── UL/
│   └── test_parameters/  ← Test parameters
└── sweeps/
    ├── sweep_000/
    │   ├── AE/
    │   │   ├── time      ← Time vector (s)
    │   │   └── voltage   ← Voltage data (V)
    │   └── UL/
    │       ├── time
    │       └── voltage
    │   attrs:
    │       telem_rpm_meas      ← Measured RPM at sweep
    │       telem_omron_pv_c    ← Temperature (°C)
    │       telem_mass_g        ← Load (g)
    │       telem_vfd_cmd_hz    ← VFD frequency (Hz)
    ├── sweep_001/
    └── ...
```

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/run/status` | Run status (elapsed, steps, telemetry) |
| `POST /api/run/start` | Start test with profile |
| `POST /api/run/stop` | Stop running test |
| `GET /api/telemetry` | Live telemetry (RPM, temp, load) |
| `GET /api/hdf5/status` | HDF5 file status (size, sweeps, disk space) |
| `GET /api/shelly/status` | Shelly channel status |
| `POST /api/shelly/switch/{id}` | Turn Shelly channel on/off |
| `GET /api/scope/waveform` | Live waveform preview |
| `GET /docs` | Interactive API documentation |
