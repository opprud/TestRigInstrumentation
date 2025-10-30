# Test Rig Metadata Integration

## Overview

The MSO-X 2024A data acquisition system now supports integrated telemetry collection from all test rig sensors. This allows each oscilloscope sweep to be annotated with simultaneous readings from:

- **RP2040 Load Cell** (mass in grams)
- **RP2040 Tachometer** (RPM, period)
- **Omron E5CC Temperature Controller** (temperature in °C via Modbus)
- **RS510 VFD** (motor frequency/status via Modbus)

Additionally, test parameters (target RPM, temperature, load, etc.) are stored in the HDF5 metadata for complete test traceability.

## HDF5 File Structure

```
/metadata (root-level attributes)
  ├─ project: "ForeverBearing"
  ├─ operator: "morten"
  ├─ scope_idn: "AGILENT TECHNOLOGIES,MSO-X 2024A,..."
  ├─ created_local: "2025-10-27T08:48:48+01:00"
  ├─ created_utc: "2025-10-27T07:48:48+00:00"
  ├─ telemetry_enabled: true/false
  ├─ test_parameters: {"test_name": "...", "target_rpm": 1500, ...}
  └─ [custom attributes from config.store.attrs]

/sweeps/
  └─ sweep_000/
      ├─ timestamp_local: "2025-10-27T08:48:48+01:00"
      ├─ timestamp_utc: "2025-10-27T07:48:48+00:00"
      ├─ points_requested: 250000
      ├─ waveform_format: "WORD"
      ├─ acq_type: "HRES"
      ├─ telemetry_timestamp_utc: "..." (if enabled)
      ├─ telemetry_mass_g: 205.3 (if enabled)
      ├─ telemetry_rpm: 1523.4 (if enabled)
      ├─ telemetry_temperature_c: 61.2 (if enabled)
      └─ [channel groups...]
          └─ AE/
              ├─ time [dataset]
              ├─ voltage [dataset]
              └─ [scaling attributes]
```

## Configuration

### Basic Configuration (No Telemetry)

```json
{
  "scope_ip": "169.254.196.182",
  "acquisition": { ... },
  "channels": [ ... ],
  "store": {
    "output_file": "data/test.h5",
    "timestamped": true,
    "attrs": {
      "project": "ForeverBearing",
      "operator": "morten"
    }
  }
}
```

### With Test Parameters

Add a `test_parameters` section to document test conditions:

```json
{
  "test_parameters": {
    "test_name": "Bearing run-in test",
    "target_rpm": 1500,
    "target_temperature_c": 60,
    "expected_load_g": 200,
    "duration_minutes": 30,
    "notes": "Initial characterization run"
  }
}
```

This data is stored as a JSON string in `/metadata` attributes.

### With Telemetry Collection

Enable real-time sensor data collection at each sweep:

```json
{
  "telemetry": {
    "enabled": true,
    "rp2040_port": "/dev/tty.usbmodem123456",
    "modbus_config": "modbus_config.json"
  }
}
```

**Requirements:**
- `telemetry_collector.py` must be available
- RP2040 firmware running and connected (optional - gracefully skips if unavailable)
- Modbus devices configured in `modbus_config.json` (optional)

## Usage Examples

### 1. Basic Acquisition (Scope Only)

```bash
python3 acquire_scope_data.py config.json
```

### 2. With Test Parameters

Edit `config.json` to add `test_parameters` section, then:

```bash
python3 acquire_scope_data.py config.json
```

### 3. Full Telemetry Acquisition

1. Connect RP2040 load cell/tachometer
2. Find serial port: `ls /dev/tty.usbmodem*`
3. Update `config.json`:
   ```json
   "telemetry": {
     "enabled": true,
     "rp2040_port": "/dev/tty.usbmodem14201",
     "modbus_config": "modbus_config.json"
   }
   ```
4. Run acquisition:
   ```bash
   python3 acquire_scope_data.py config.json
   ```

### 4. Debug Mode

Enable detailed VISA I/O logging and error checking:

```bash
python3 acquire_scope_data.py config.json --debug
```

This creates `visa_io.log` with full SCPI communication trace.

## Testing Telemetry Collector

Test the telemetry system independently:

```bash
# Test RP2040 only
python3 telemetry_collector.py --rp2040-port /dev/tty.usbmodem14201 --json

# Test all sensors
python3 telemetry_collector.py \
  --rp2040-port /dev/tty.usbmodem14201 \
  --modbus-config modbus_config.json \
  --json
```

Expected output:
```json
{
  "timestamp_utc": "2025-10-27T07:48:57+00:00",
  "mass_g": 205.3,
  "raw_load": 123456,
  "ts_load": 1698384537000,
  "rpm": 1523.4,
  "period_ms": 39.4,
  "pulses": 15234,
  "ts_speed": 1698384537000,
  "temperature_c": 61.2
}
```

## Inspecting HDF5 Files

Use the `inspect_hdf5.py` tool to view file structure:

```bash
python3 inspect_hdf5.py data/test_20251027_084848.h5
```

This displays all groups, datasets, and attributes in a tree format.

## Error Handling

The telemetry collection is **non-blocking** - if sensors are unavailable:
- Acquisition continues with scope data only
- Missing telemetry fields are omitted from sweep attributes
- Warnings printed to stderr (visible with `--debug`)

Example scenarios:
- RP2040 not connected → `telemetry_mass_g` and `telemetry_rpm` omitted
- Modbus timeout → `telemetry_temperature_c` omitted
- All sensors fail → sweep has no `telemetry_*` attributes

## Integration with Python Analysis

### Reading Test Parameters

```python
import h5py
import json

with h5py.File("data/test.h5", "r") as f:
    params_json = f["/metadata"].attrs["test_parameters"]
    params = json.loads(params_json)
    print(f"Test: {params['test_name']}")
    print(f"Target RPM: {params['target_rpm']}")
```

### Reading Sweep Telemetry

```python
import h5py

with h5py.File("data/test.h5", "r") as f:
    for sweep_name in f["/sweeps"].keys():
        sweep = f[f"/sweeps/{sweep_name}"]

        ts = sweep.attrs["timestamp_utc"]
        rpm = sweep.attrs.get("telemetry_rpm", None)
        temp = sweep.attrs.get("telemetry_temperature_c", None)
        load = sweep.attrs.get("telemetry_mass_g", None)

        print(f"{sweep_name} @ {ts}")
        print(f"  RPM: {rpm}, Temp: {temp}°C, Load: {load}g")
```

### Correlating Waveforms with Telemetry

```python
import h5py
import numpy as np

with h5py.File("data/test.h5", "r") as f:
    sweep = f["/sweeps/sweep_000"]

    # Get telemetry metadata
    rpm = sweep.attrs.get("telemetry_rpm")
    load_g = sweep.attrs.get("telemetry_mass_g")

    # Get waveform data
    ae_voltage = sweep["AE/voltage"][:]
    ae_time = sweep["AE/time"][:]

    # Analyze waveform with context
    rms = np.sqrt(np.mean(ae_voltage**2))
    print(f"AE RMS @ {rpm} RPM, {load_g}g load: {rms:.3f}V")
```

## Dashboard Integration

The React dashboard can consume this data via the Python API server (`api_server.py`).

Recommended endpoints:
- `GET /api/telemetry` - Latest sensor readings
- `GET /api/acquisition/start` - Start acquisition with config
- `GET /api/acquisition/status` - Check acquisition progress
- `GET /api/hdf5/latest` - Get latest HDF5 file info

See `api_server.py` for implementation details.

## Troubleshooting

### Scope Connection Issues

```bash
# Test scope connectivity
python3 test_scope_connection.py

# Check IP configuration
ping 169.254.196.182
```

### RP2040 Not Detected

```bash
# List serial devices
ls /dev/tty.usbmodem*

# Test RP2040 communication
python3 util_tool.py --port /dev/tty.usbmodemXXXX ping
python3 util_tool.py --port /dev/tty.usbmodemXXXX load --json
```

### Modbus Communication Errors

```bash
# Verify Modbus configuration
cat modbus_config.json

# Test temperature controller
python3 omron_temp_poll.py --config modbus_config.json pv

# Scan for Modbus devices
python3 scanmodbusregisters.py
```

### HDF5 File Errors

```bash
# Check file integrity
h5ls -r data/test.h5

# Inspect with Python tool
python3 inspect_hdf5.py data/test.h5
```

## Next Steps

1. **Dashboard Integration**: Connect React frontend to Python API for real-time acquisition control
2. **Automated Test Sequences**: Create test profiles with RPM/temperature ramps
3. **Real-time Streaming**: Add WebSocket support for live telemetry updates
4. **Data Analysis**: Develop Jupyter notebooks for post-processing HDF5 files
5. **VFD Integration**: Complete RS510 VFD telemetry in `telemetry_collector.py`

## Files Modified/Created

### New Files
- `telemetry_collector.py` - Unified sensor data collection
- `test_scope_connection.py` - Scope connectivity test
- `inspect_hdf5.py` - HDF5 file structure viewer
- `config_with_telemetry.json` - Example configuration
- `METADATA_README.md` - This documentation

### Modified Files
- `acquire_scope_data.py` - Added telemetry integration
- `config.json` - Added telemetry and test_parameters sections

## Configuration Reference

See `config_with_telemetry.json` for a complete example with all features enabled.
