# Telemetry Integration Guide

## Overview

The telemetry system integrates load cell, tachometer, and temperature sensor data into HDF5 acquisition files alongside oscilloscope waveform data.

## Architecture

### Data Flow
```
┌─────────────────┐
│   RP2040        │  HX711 Load Cell + Tachometer
│  (util_tool.py) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  telemetry.py   │  TelemetryReader class
│                 │  - read_rp2040()
│                 │  - read_modbus_temperature()
└────────┬────────┘
         │
         ▼
┌──────────────────┐
│ acquire_scope_   │  Main acquisition loop
│   data.py        │  - Reads scope data
│                  │  - Calls telemetry.read_all()
│                  │  - Stores both in HDF5
└──────────────────┘
```

### HDF5 Structure

```
file.hdf5
├── metadata/
│   ├── created_local: "2025-11-28T..."
│   ├── created_utc: "2025-11-28T..."
│   ├── scope_idn: "AGILENT TECHNOLOGIES..."
│   ├── telemetry_enabled: True
│   └── rp2040_port: "/dev/tty.usbmodem123456"
│
└── sweeps/
    ├── sweep_000/
    │   ├── timestamp_local: "2025-11-28T..."
    │   ├── timestamp_utc: "2025-11-28T..."
    │   ├── load_g: 150.5                    # ← Telemetry data
    │   ├── load_timestamp_ms: 1234567890    # ← RP2040 timestamp
    │   ├── rpm: 1500.0                      # ← Tachometer reading
    │   ├── rpm_timestamp_ms: 1234567890     # ← RP2040 timestamp
    │   ├── temperature_c: 60.5              # ← Temperature sensor
    │   │
    │   ├── AE/                              # ← Scope channel
    │   │   ├── time: [dataset]
    │   │   └── voltage: [dataset]
    │   └── Accel/
    │       ├── time: [dataset]
    │       └── voltage: [dataset]
    │
    ├── sweep_001/
    │   └── ...
    └── sweep_002/
        └── ...
```

## Configuration

### Enable Telemetry in config.json

```json
{
  "telemetry": {
    "enabled": true,
    "rp2040_port": "/dev/tty.usbmodem1234",
    "modbus_config": "modbus_config.json",
    "notes": "Enable to collect load/speed/temperature data"
  }
}
```

### RP2040 Requirements

The RP2040 must be running firmware that supports the ASCII protocol with:
- `LOAD?` command (returns JSON with mass_g, timestamp_ms, raw)
- `SPEED?` command (returns JSON with rpm, timestamp_ms, pulses)

Example:
```bash
python util_tool.py --port /dev/tty.usbmodem1234 load --json
# {"mass_g": 150.5, "timestamp_ms": 1234567890, "raw": 12345}

python util_tool.py --port /dev/tty.usbmodem1234 speed --json
# {"rpm": 1500.0, "timestamp_ms": 1234567890, "pulses": 1000}
```

## Usage

### 1. Configure Telemetry

Edit `config.json`:
```json
"telemetry": {
  "enabled": true,
  "rp2040_port": "/dev/tty.usbmodem123456"
}
```

### 2. Run Acquisition

```bash
python acquire_scope_data.py config.json
```

Output will show telemetry values:
```
[2025-11-28T13:45:23] Sweep 1/100 (Load: 150.5g, RPM: 1500)
[2025-11-28T13:45:28] Sweep 2/100 (Load: 151.2g, RPM: 1505)
...
```

### 3. View Telemetry Data

```bash
python view_telemetry.py data/acquisition_20251128_134523.hdf5
```

Output:
```
================================================================================
Sweep        Timestamp                     load_g          rpm
================================================================================
sweep_000    2025-11-28T13:45:23            150.50      1500.00
sweep_001    2025-11-28T13:45:28            151.20      1505.00
sweep_002    2025-11-28T13:45:33            149.80      1498.00
...

Statistics:
================================================================================
Parameter                  Min          Max         Mean          Std
--------------------------------------------------------------------------------
load_g                  149.80       151.20       150.50         0.70
rpm                    1498.00      1505.00      1501.00         3.51
```

### 4. Analyze Data

```python
import h5py

with h5py.File("data/acquisition.hdf5", "r") as f:
    # Extract telemetry time series
    loads = []
    rpms = []

    for sweep_name in sorted(f["sweeps"].keys()):
        sweep = f["sweeps"][sweep_name]
        loads.append(sweep.attrs["load_g"])
        rpms.append(sweep.attrs["rpm"])

    # Plot or analyze
    import matplotlib.pyplot as plt
    plt.plot(loads, label="Load (g)")
    plt.plot(rpms, label="RPM")
    plt.legend()
    plt.show()
```

## Features

### Automatic Integration
- Telemetry data is automatically read for each sweep
- No additional code needed in acquisition loop
- Gracefully handles missing/failed sensor reads

### Error Handling
- Continues acquisition if telemetry fails
- Warnings printed to console
- Missing values stored as None/NaN

### Flexible Configuration
- Enable/disable per config file
- Support for multiple sensor types (RP2040, Modbus)
- Easy to extend with new sensors

## Extending

### Add New Sensor Type

Edit `telemetry.py`:

```python
def read_new_sensor(self) -> Optional[Dict[str, Any]]:
    """Read data from new sensor"""
    if not self.enabled:
        return None

    # Your sensor reading code here
    return {
        "sensor_value": 123.45,
        "sensor_timestamp": 1234567890
    }

def read_all(self) -> Dict[str, Any]:
    telemetry = {}

    # Existing sensors
    rp2040_data = self.read_rp2040()
    if rp2040_data:
        telemetry.update(rp2040_data)

    # Add your new sensor
    new_data = self.read_new_sensor()
    if new_data:
        telemetry.update(new_data)

    return telemetry
```

## Benefits

1. **Unified Data Storage**: All test data in one HDF5 file
2. **Synchronized Timestamps**: Each sweep has scope + telemetry at same instant
3. **Traceability**: Know exact test conditions for each waveform
4. **Analysis Ready**: Easy to correlate vibration with load/speed
5. **Flexible**: Works with or without telemetry enabled
