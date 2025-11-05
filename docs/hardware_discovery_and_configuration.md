# Hardware Discovery and Configuration

## Overview

The Test Rig Instrumentation system integrates multiple hardware devices for bearing test measurements. This document describes how hardware is discovered, connected, and configured through the Python backend.

---

## Hardware Components

The test rig consists of four main hardware subsystems:

| Component | Type | Interface | Purpose |
|-----------|------|-----------|---------|
| **Keysight MSO-X 2024A** | Oscilloscope | Ethernet (SCPI/TCP) | High-speed waveform acquisition (AE, vibration, ultrasound) |
| **Seeed XIAO RP2040** | Microcontroller | USB Serial | Load cell (HX711) and tachometer readings |
| **Omron E5CC** | Temperature Controller | RS485/Modbus RTU | Bearing temperature monitoring |
| **RS510 VFD** | Variable Frequency Drive | RS485/Modbus RTU | Motor speed control |

---

## Hardware Discovery

### `hardware_discovery.py`

The `hardware_discovery.py` script automatically detects and tests all connected hardware devices. It provides both human-readable and JSON output formats.

#### Usage

```bash
# Basic discovery with formatted output
python3 hardware_discovery.py

# JSON output for programmatic access
python3 hardware_discovery.py --json

# Verbose debug logging
python3 hardware_discovery.py --verbose

# Use config.json for scope IP
python3 hardware_discovery.py --config config.json --json
```

#### Discovery Process

**1. Serial Port Enumeration**

The script scans all USB serial ports and categorizes them by Vendor ID (VID) and Product ID (PID):

- **RP2040 Devices**: `VID:0x2E8A` or `VID:0x2886` (Raspberry Pi / Seeed Studio)
- **FTDI Adapters**: `VID:0x0403` (FT232R, FT232H, FT-X series)
- **Unknown**: Other serial devices

**2. Oscilloscope Connection Test**

```python
# Tests TCP connectivity on port 5025 (SCPI default)
# Issues *IDN? query to verify instrument identity
```

The script attempts to connect to the oscilloscope using:
1. TCP socket test to `<scope_ip>:5025`
2. PyVISA SCPI connection: `TCPIP::<scope_ip>::INSTR`
3. `*IDN?` query to retrieve model and serial number

**3. RP2040 Firmware Test**

```python
# Opens serial connection at 115200 baud
# Sends PING command, expects "OK PONG" response
# Sends INFO command to retrieve firmware version
```

Protocol commands:
- `PING` → `OK PONG <uptime_ms>`
- `INFO` → `OK INFO vendor=ForeverBearing device=RP2040 fw=1.0.1`

**4. RS485/Modbus Device Test**

The script verifies that FTDI serial adapters are accessible. Full Modbus communication testing is handled by device-specific utilities (`omron_temp_poll.py`, `rs510_vfd_control.py`).

#### Example Output

```
Hardware Discovery Report
==================================================
Timestamp: 2025-11-05T14:32:15.123456+01:00

🔬 MSO-X 2024A: CONNECTED
   IDN: KEYSIGHT TECHNOLOGIES,MSO-X 2024A,MY56123456,07.50.2021102830
   IP: 169.254.227.76

🔧 RP2040: CONNECTED
   Port: /dev/tty.usbmodem14201
   Firmware: 1.0.1

🌡️  E5CC (RS485): CONNECTED
   Port: /dev/tty.usbserial-FTDI485

📍 Available Ports:
   RP2040: 1 found
     - /dev/tty.usbmodem14201 (Seeed Studio XIAO RP2040)
   FTDI: 1 found
     - /dev/tty.usbserial-FTDI485 (FTDI FT232R)
```

---

## Configuration Files

### Main Configuration: `config.json`

The primary configuration file controls all aspects of data acquisition and hardware settings.

#### Structure

```json
{
  "scope_ip": "169.254.227.76",
  "acquisition": { ... },
  "dashboard_preview": { ... },
  "channels": [ ... ],
  "telemetry": { ... },
  "test_parameters": { ... },
  "store": { ... }
}
```

#### Scope Configuration

```json
{
  "scope_ip": "MSO-X-2024A-MY12345678.local"
}
```

**Key Settings:**
- Can use IP address (e.g., `"169.254.227.76"`) or hostname (e.g., `"scope.local"`)
- **Recommendation**: Use mDNS hostname to avoid tracking DHCP-assigned IPs
- Find hostname on scope: **Utility** → **I/O** → **LAN** → **Host Name**

#### Acquisition Configuration

```json
{
  "acquisition": {
    "points": 250000,
    "samples": 3,
    "interval_sec": 3,
    "waveform_format": "WORD",
    "points_mode": "RAW",
    "trigger_sweep": "AUTO",
    "acq_type": "HRES"
  }
}
```

| Parameter | Description | Options |
|-----------|-------------|---------|
| `points` | Number of waveform points to capture | Oscilloscope-dependent (typically 1k-2M) |
| `samples` | Number of sweeps to acquire | Integer ≥ 1 |
| `interval_sec` | Delay between sweeps | Seconds (float) |
| `waveform_format` | Data transfer format | `WORD` (16-bit, preferred), `BYTE` (8-bit), `ASC` (ASCII) |
| `points_mode` | Acquisition mode | `NORM` (decimated), `RAW` (full memory depth) |
| `trigger_sweep` | Trigger mode | `AUTO`, `NORM` (normal) |
| `acq_type` | Acquisition type | `NORM`, `HRES` (high-resolution), `AVER` (averaging) |

#### Channel Configuration

```json
{
  "channels": [
    {
      "name": "AE",
      "source": "CHAN1",
      "enabled": true,
      "notes": "Kistler acoustic emission probe"
    },
    {
      "name": "Accel",
      "source": "CHAN2",
      "enabled": true,
      "notes": "Piezo accelerometer"
    },
    {
      "name": "UL",
      "source": "CHAN3",
      "enabled": true,
      "notes": "Ultrasound"
    },
    {
      "name": "Temp",
      "source": "CHAN4",
      "enabled": true,
      "notes": "Temperature"
    }
  ]
}
```

- **`name`**: Alias for HDF5 dataset naming
- **`source`**: Oscilloscope channel (`CHAN1` through `CHAN4`)
- **`enabled`**: Set to `false` to skip acquisition for this channel
- **`notes`**: Human-readable description stored in HDF5 metadata

#### Telemetry Configuration

```json
{
  "telemetry": {
    "enabled": true,
    "rp2040_port": "/dev/tty.usbmodem14201",
    "modbus_config": "modbus_config.json"
  }
}
```

When enabled, the system collects sensor data at each sweep:
- **Load cell** mass (grams)
- **Tachometer** RPM and pulse counts
- **Temperature** from Omron E5CC (°C)
- **VFD** motor frequency (Hz)

Data is stored as HDF5 sweep attributes:
```
/sweeps/sweep_000 (attributes):
  - telemetry_mass_g: 156.7
  - telemetry_rpm: 1503
  - telemetry_temperature_c: 62.4
  - telemetry_frequency_hz: 25.0
```

#### Test Parameters

```json
{
  "test_parameters": {
    "test_name": "Bearing endurance test",
    "target_rpm": 1500,
    "target_temperature_c": 60,
    "expected_load_g": 200,
    "duration_minutes": 60,
    "notes": "Standard test configuration"
  }
}
```

Stored in HDF5 `/metadata` group for experiment documentation.

#### Storage Configuration

```json
{
  "store": {
    "output_file": "data/data3.h5",
    "timestamped": true,
    "compress": "none",
    "chunk": false,
    "attrs": {
      "project": "ForeverBearing",
      "operator": "morten",
      "scope_model": "MSO-X 2024A"
    }
  }
}
```

- **`timestamped: true`**: Appends `_YYYYMMDD_HHMMSS` to filename
- **`compress`**: `"none"` or `"gzip"` (level 4)
- **`chunk`**: Enable HDF5 chunking for large datasets

---

### Modbus Configuration: `modbus_config.json`

Shared configuration for RS485/Modbus devices (Omron E5CC and RS510 VFD).

```json
{
  "description": "Shared Modbus configuration for test rig devices",
  "connection": {
    "port": "/dev/tty.usbserial-FTDI485",
    "baudrate": 9600,
    "parity": "N",
    "bytesize": 8,
    "stopbits": 1,
    "timeout": 2.0
  },
  "devices": {
    "omron_e5cc": {
      "description": "Omron E5CC Temperature Controller",
      "unit_id": 4,
      "registers": {
        "pv_address": "0x2000",
        "sv_address": "0x2103"
      },
      "scale": 1.0
    },
    "rs510_vfd": {
      "description": "RS PRO RS510 VFD Motor Controller",
      "unit_id": 3,
      "registers": {
        "run_command": "0x2501",
        "frequency_cmd": "0x2502",
        "base_freq": "0x000B",
        "max_freq": "0x000C",
        "accel_time": "0x000E",
        "decel_time": "0x000F",
        "fault_code": "0x0015"
      }
    }
  }
}
```

**Important Notes:**
- Both devices share a single FTDI485 adapter using `shared_modbus_manager.py`
- Communication is thread-safe and serialized to prevent bus collisions
- If devices require incompatible serial settings (baud rate, parity), use separate adapters
- Verify `unit_id` settings match physical device configuration (typically set via DIP switches or menu)

---

## Typical Hardware Setup Workflow

### 1. Physical Connections

1. Connect oscilloscope to network via Ethernet
2. Connect RP2040 to USB (load cell + tachometer)
3. Connect FTDI485 adapter to USB
4. Wire RS485 bus: FTDI485 → Omron E5CC → RS510 VFD (daisy chain)

### 2. Find Device Addresses

```bash
# Discover all connected hardware
python3 hardware_discovery.py --verbose

# Test RP2040 communication
python3 util_tool.py --port /dev/tty.usbmodem14201 ping

# Test Omron E5CC
python3 omron_temp_poll.py --config modbus_config.json --json pv

# Test RS510 VFD
python3 rs510_vfd_control.py --config modbus_config.json status
```

### 3. Configure `config.json`

Update the following fields based on discovery results:
- `scope_ip`: Oscilloscope IP or hostname
- `telemetry.rp2040_port`: RP2040 serial port (e.g., `/dev/tty.usbmodem14201`)
- `telemetry.modbus_config`: Path to `modbus_config.json`

### 4. Configure `modbus_config.json`

Update:
- `connection.port`: FTDI adapter serial port (e.g., `/dev/tty.usbserial-FTDI485`)
- `devices.omron_e5cc.unit_id`: Verify against device configuration
- `devices.rs510_vfd.unit_id`: Verify against device configuration

### 5. Validate Configuration

```bash
# Run full hardware test
python3 test_hardware.py

# Test scope connection
python3 test_scope_connection.py

# Test data acquisition
python3 acquire_scope_data.py config.json --debug
```

---

## Troubleshooting

### Oscilloscope Not Found

**Symptom**: `Cannot reach <ip>:5025`

**Solutions**:
1. Verify oscilloscope is powered on and connected to network
2. Check IP address: **Utility** → **I/O** → **LAN** → **IP Address**
3. Ping the device: `ping <scope_ip>`
4. Try using hostname instead of IP: `MSO-X-2024A-<serial>.local`
5. Check firewall settings on host computer

### RP2040 Not Responding

**Symptom**: `Unexpected response` or timeout

**Solutions**:
1. Verify correct port: `ls /dev/tty.usbmodem*` (macOS) or `ls /dev/ttyACM*` (Linux)
2. Check baud rate: Should be 115200
3. Reset device: Unplug and reconnect USB
4. Re-flash firmware: `cd ../firmware && pio run --target upload`
5. Check serial permissions: `sudo chmod 666 /dev/ttyACM0` (Linux)

### Modbus Communication Errors

**Symptom**: `No response from slave` or timeout

**Solutions**:
1. Verify FTDI adapter port: `ls /dev/tty.usbserial*`
2. Check RS485 wiring: A → A, B → B, GND → GND
3. Verify device `unit_id` settings (consult device manual)
4. Try different baud rates: Some devices default to 9600, others 19200 or 57600
5. Check bus termination: 120Ω resistors at each end of RS485 bus
6. Test one device at a time to isolate issues
7. Use `scanmodbusregisters.py` to scan for active slave IDs

### Multiple FTDI Adapters

If you have multiple FTDI devices, identify them by serial number:

```bash
python3 hardware_discovery.py --json | grep -A5 ftdi
```

Use serial number in udev rules (Linux) or identify by unique path on macOS.

---

## Data Flow Summary

```
Hardware Layer
├─ MSO-X 2024A ─────► PyVISA/SCPI ─────► acquire_scope_data.py
├─ RP2040 ──────────► USB Serial ───────► util_tool.py
├─ Omron E5CC ──────► RS485/Modbus ────► omron_temp_poll.py
└─ RS510 VFD ───────► RS485/Modbus ────► rs510_vfd_control.py
                                           │
                                           ▼
                                  telemetry_collector.py
                                           │
                                           ▼
                                    HDF5 Storage
                                           │
                                           ▼
                              ┌────────────┴──────────┐
                              │                       │
                        plot_waveform.py      React Dashboard
```

---

## Related Documentation

- **Firmware Protocol**: `../firmware/PROTOCOL.md` (RP2040 ASCII command reference)
- **Data Format**: `DATA_MANAGEMENT.md` (HDF5 structure and metadata)
- **Python Tools**: `../py/README.md` (Utility scripts and API)

---

**Document Version**: 1.0
**Last Updated**: 2025-11-05
**Author**: Test Rig Instrumentation Team
