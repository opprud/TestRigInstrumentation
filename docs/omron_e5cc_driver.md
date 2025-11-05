# Omron E5CC Temperature Controller Driver

## Introduction

This page documents how to monitor and control the **Omron E5CC Temperature Controller** using Python and Modbus RTU over an RS485/USB adapter. This allows remote reading of bearing temperature, setpoint adjustment, and continuous temperature monitoring during test runs.

The E5CC temperature controller has registers exposed via Modbus, allowing control. See Omron E5CC manual for detailed register specifications.

The Python script (`omron_temp_poll.py`) provides:

- Read Process Value (PV) - current temperature measurement
- Read Setpoint Value (SV) - target temperature
- Write Setpoint Value (SV) - adjust target temperature
- Continuous temperature monitoring with configurable polling interval
- JSON output for programmatic integration
- Support for 1°C and 0.1°C resolution modes

---

## Overview

The Omron E5CC temperature controller driver provides Python-based monitoring and control of the Omron E5CC digital temperature controller via Modbus RTU over RS485. This driver enables:

- **Temperature Monitoring**: Real-time reading of process temperature (PV)
- **Setpoint Management**: Read and write target temperature (SV)
- **Continuous Logging**: Poll temperature at configurable intervals
- **Data Integration**: Store temperature data in HDF5 files alongside oscilloscope measurements
- **Shared Bus Operation**: Safe concurrent access with VFD and other Modbus devices

**Key Features:**
- Thread-safe shared Modbus connection manager
- Automatic FTDI RS485 adapter detection
- Configurable temperature resolution (1°C or 0.1°C)
- JSON output for automation
- Debug mode for troubleshooting
- One-shot and continuous polling modes

---

## Hardware Setup

### Components

| Component | Description | Interface |
|-----------|-------------|-----------|
| **Omron E5CC** | Digital temperature controller with PID control | Modbus RTU (RS485) |
| **Temperature Sensor** | Thermocouple or RTD connected to E5CC input | Analog |
| **FTDI RS485 Adapter** | USB-to-RS485 converter (e.g., FT232R) | USB |
| **Heating/Cooling Output** | SSR or relay controlled by E5CC output (optional) | - |

### Wiring

**RS485 Bus Connection:**
```
USB Computer
    │
    └─► FTDI RS485 Adapter
            │
            ├─► A+ ───┐
            ├─► B- ───┼─► Omron E5CC (A+/B-)
            └─► GND ──┘
                      │
                      └─► RS510 VFD (optional, daisy-chain)
```

**Temperature Sensor Connection:**
```
Bearing/Test Point
    │
    └─► Thermocouple/RTD ──► E5CC Input Terminals
                              │
                              └─► (Configured via E5CC menu)
```

**Important:**
- Use twisted-pair cable for RS485 (A+/B-) connections
- Add 120Ω termination resistors at both ends of long RS485 bus runs (>10m)
- Keep sensor wiring away from motor power cables to reduce noise
- Verify E5CC unit ID (slave address) matches configuration (typically 2 or 4)
- Ensure proper sensor type configuration in E5CC menu (K-type, PT100, etc.)

### E5CC Configuration

Set the following parameters on the Omron E5CC (consult manual for detailed menu navigation):

| Parameter | Setting | Description |
|-----------|---------|-------------|
| **Communication Protocol** | Modbus RTU | Enable Modbus mode (Communications menu) |
| **Baud Rate** | 9600 | Match `modbus_config.json` (historically 57600) |
| **Parity** | None (N) | Match `modbus_config.json` (historically Even) |
| **Slave Address (Unit ID)** | 4 | Default in config, adjustable (historically 2) |
| **Sensor Type** | K-type TC / PT100 | Match connected sensor |
| **Temperature Range** | Per application | E.g., 0-200°C for bearing tests |
| **Resolution** | 1°C or 0.1°C | Use `--scale` parameter to match |

**Note**: The default configuration has changed from the original E5CC settings. If communication fails, try:
- Baudrate: 57600 (original) vs 9600 (current)
- Parity: E (Even, original) vs N (None, current)
- Unit ID: 2 (original) vs 4 (current)

---

## Software Installation

### Prerequisites

```bash
# Required Python packages
pip install pymodbus pyserial

# Optional for discovery
pip install pyserial
```

### Files

- `omron_temp_poll.py` - Main E5CC driver script
- `shared_modbus_manager.py` - Thread-safe Modbus connection manager
- `hardware_utils.py` - Auto-detection utilities
- `modbus_config.json` - Shared Modbus configuration
- `telemetry_collector.py` - Integration with data acquisition system

---

## Configuration

### modbus_config.json

```json
{
  "description": "Shared Modbus configuration for test rig devices",
  "connection": {
    "port": "auto",
    "baudrate": 9600,
    "parity": "N",
    "bytesize": 8,
    "stopbits": 1,
    "timeout": 2.0,
    "notes": "Use 'auto' to auto-detect FTDI adapter, or specify explicit path"
  },
  "devices": {
    "omron_e5cc": {
      "description": "Omron E5CC Temperature Controller",
      "unit_id": 4,
      "registers": {
        "pv_address": "0x2000",
        "sv_address": "0x2103"
      },
      "scale": 1.0,
      "notes": [
        "May require different settings - check E5CC manual",
        "Original settings: baudrate=57600, parity='E'",
        "If communication fails, try unit_id=2 or original settings"
      ]
    }
  }
}
```

**Port Configuration:**
- `"auto"` - Automatically detect FTDI RS485 adapter (recommended)
- `"/dev/tty.usbserial-XXXXXX"` (macOS) - Explicit device path
- `"/dev/ttyUSB0"` (Linux) - Explicit device path
- `"COM3"` (Windows) - Explicit COM port

**Register Addresses:**
- `0x2000` - Process Value (PV) - Current measured temperature
- `0x2103` - Setpoint Value (SV) - Target temperature

**Scale Factor:**
- `1.0` - Temperature in whole degrees (e.g., 65°C)
- `0.1` - Temperature in tenths of degrees (e.g., 65.5°C)

---

## Command Reference

### Basic Usage

```bash
python3 omron_temp_poll.py --port <PORT> --unit <ID> <COMMAND>
```

### Commands

#### 1. Read Current Temperature (PV) - One Shot

```bash
# Read once with human-readable output
python3 omron_temp_poll.py --port auto --unit 4 --get-pv --once

# Read once with JSON output
python3 omron_temp_poll.py --port auto --unit 4 --get-pv --once --json

# Enable debug output
python3 omron_temp_poll.py --port auto --unit 4 --get-pv --once --debug
```

**Example Output (Human-Readable):**
```
62.0 °C
```

**Example Output (JSON):**
```json
{
  "temp_C": 62.0,
  "kind": "PV",
  "addr": 8192,
  "unit": 4
}
```

#### 2. Read Setpoint (SV) - One Shot

```bash
# Read setpoint once
python3 omron_temp_poll.py --port auto --unit 4 --get-sv --once

# Read with JSON output
python3 omron_temp_poll.py --port auto --unit 4 --get-sv --once --json
```

**Example Output:**
```json
{
  "temp_C": 60.0,
  "kind": "SV",
  "addr": 8451,
  "unit": 4
}
```

#### 3. Write Setpoint (SV)

```bash
# Set target temperature to 65°C
python3 omron_temp_poll.py --port auto --unit 4 --set-sv 65.0

# Set with JSON confirmation
python3 omron_temp_poll.py --port auto --unit 4 --set-sv 65.0 --json
```

**Example Output:**
```json
{
  "ok": true,
  "set_sv_C": 65.0
}
```

#### 4. Continuous Temperature Monitoring

```bash
# Poll temperature every 1 second (default)
python3 omron_temp_poll.py --port auto --unit 4 --get-pv

# Poll every 5 seconds
python3 omron_temp_poll.py --port auto --unit 4 --get-pv --interval 5.0

# Continuous with JSON output (for logging)
python3 omron_temp_poll.py --port auto --unit 4 --get-pv --json > temp_log.json
```

**Example Continuous Output (JSON):**
```json
{"ts_ms": 1730814735123, "temp_C": 61.5, "kind": "PV"}
{"ts_ms": 1730814736123, "temp_C": 61.7, "kind": "PV"}
{"ts_ms": 1730814737123, "temp_C": 62.0, "kind": "PV"}
...
```

Press `Ctrl+C` to stop continuous monitoring.

#### 5. High-Resolution Mode (0.1°C)

If your E5CC is configured for 0.1°C resolution:

```bash
# Read with 0.1°C scale factor
python3 omron_temp_poll.py --port auto --unit 4 --get-pv --once --scale 0.1
```

**Example Output:**
```
62.3 °C
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--port PORT` | Serial port (auto, or explicit path) | `/dev/tty.usbserial-XXXXXX` |
| `--unit ID` | Modbus slave/unit ID | 4 |
| `--baudrate RATE` | Serial baud rate | 9600 |
| `--parity {N,E,O}` | Parity mode (None, Even, Odd) | N |
| `--bytesize {7,8}` | Data bits | 8 |
| `--stopbits {1,2}` | Stop bits | 1 |
| `--timeout SECS` | Communication timeout | 1.5 |
| `--pv-address ADDR` | PV register address | 0x2000 |
| `--sv-address ADDR` | SV register address | 0x2103 |
| `--scale FACTOR` | Temperature scaling (raw × scale = °C) | 1.0 |
| `--get-pv` | Read process value (temperature) | - |
| `--get-sv` | Read setpoint | - |
| `--set-sv TEMP` | Write setpoint (°C) | - |
| `--once` | Read once instead of continuous | Off |
| `--interval SECS` | Polling interval for continuous mode | 1.0 |
| `--json` | JSON output format | Off |
| `--debug` | Enable debug output | Off |

---

## Auto-Detection

The driver automatically detects FTDI RS485 adapters when `--port auto` is used.

### Detection Process

1. Scans all USB serial ports
2. Filters by FTDI Vendor ID (0x0403) and Product IDs:
   - 0x6001 (FT232R)
   - 0x6014 (FT232H)
   - 0x6015 (FT-X)
3. Returns first available FTDI device
4. Falls back to configured path if detection fails

### Testing Detection

```bash
# Test hardware detection directly
python3 hardware_utils.py
```

**Example Output:**
```
Hardware Port Detection Test
==================================================

FTDI RS485 Adapters:
[DEBUG] Found 1 FTDI device(s)
[DEBUG]   /dev/cu.usbserial-FT07T8EH - FTDI FT232R (SN: FT07T8EH)
  → Selected: /dev/cu.usbserial-FT07T8EH
```

---

## Python API

### Programmatic Usage

```python
from omron_temp_poll import E5CCTool

# Initialize with auto-detection
tool = E5CCTool(
    port="auto",
    baudrate=9600,
    parity="N",
    bytesize=8,
    stopbits=1,
    timeout=1.5,
    unit_id=4,
    pv_address=0x2000,
    sv_address=0x2103,
    scale=1.0,
    debug=True
)

# Read current temperature
current_temp = tool.read_pv_c()
print(f"Current temperature: {current_temp:.1f} °C")

# Read setpoint
setpoint = tool.read_sv_c()
print(f"Setpoint: {setpoint:.1f} °C")

# Write new setpoint
tool.write_sv_c(65.0)
print("Setpoint updated to 65.0 °C")

# Cleanup
tool.close()
```

### Integration with Data Acquisition

```python
from omron_temp_poll import E5CCTool
import h5py

# Initialize temperature controller
temp_controller = E5CCTool(
    port="auto",
    baudrate=9600,
    parity="N",
    bytesize=8,
    stopbits=1,
    timeout=1.5,
    unit_id=4,
    pv_address=0x2000,
    sv_address=0x2103,
    scale=1.0
)

# During acquisition sweep
with h5py.File("data.h5", "a") as h5f:
    sweep_grp = h5f["sweeps/sweep_000"]

    # Read and store temperature
    current_temp = temp_controller.read_pv_c()
    sweep_grp.attrs['temperature_c'] = current_temp

    # Read and store setpoint
    setpoint = temp_controller.read_sv_c()
    sweep_grp.attrs['temperature_setpoint_c'] = setpoint

temp_controller.close()
```

---

## Shared Modbus Operation

The driver uses `shared_modbus_manager.py` to enable safe concurrent access to the RS485 bus with other devices (e.g., RS510 VFD).

### Features

- **Thread-safe**: Uses `threading.RLock()` for serialization
- **Automatic retries**: Configurable retry logic with exponential backoff
- **Health monitoring**: Tracks connection failures and recovery
- **Single connection**: Reuses one serial port connection across devices

### Example: Concurrent Access

```bash
# Terminal 1: Monitor temperature
python3 omron_temp_poll.py --port auto --unit 4 --get-pv --json

# Terminal 2: Control VFD
python3 rs510_vfd_control.py --port auto --slave 3 --start 10.0
```

Both scripts share the same FTDI adapter without conflicts.

---

## Example Workflows

### 1. Initial Connection Test

```bash
# Step 1: Test auto-detection
python3 hardware_utils.py

# Step 2: Read current temperature
python3 omron_temp_poll.py --port auto --unit 4 --get-pv --once --debug

# Step 3: Read setpoint
python3 omron_temp_poll.py --port auto --unit 4 --get-sv --once

# Step 4: Verify both values
python3 omron_temp_poll.py --port auto --unit 4 --get-pv --once --json
python3 omron_temp_poll.py --port auto --unit 4 --get-sv --once --json
```

### 2. Setpoint Adjustment

```bash
# Read current setpoint
python3 omron_temp_poll.py --port auto --unit 4 --get-sv --once

# Output: 60.0 °C

# Adjust to 65°C
python3 omron_temp_poll.py --port auto --unit 4 --set-sv 65.0

# Verify new setpoint
python3 omron_temp_poll.py --port auto --unit 4 --get-sv --once

# Output: 65.0 °C
```

### 3. Continuous Monitoring to File

```bash
# Start continuous logging (JSON format)
python3 omron_temp_poll.py --port auto --unit 4 --get-pv --json > temperature_log_$(date +%Y%m%d_%H%M%S).json

# Let it run during test...
# Press Ctrl+C to stop

# Parse log file
jq '.temp_C' temperature_log_20251105_123045.json
```

### 4. Real-Time Monitoring Dashboard

```bash
# Watch temperature in real-time with timestamps
watch -n 1 'python3 omron_temp_poll.py --port auto --unit 4 --get-pv --once'
```

### 5. Integration with Test Acquisition

```bash
# Shell script for full test run
#!/bin/bash

# Set target temperature
python3 omron_temp_poll.py --port auto --unit 4 --set-sv 60.0

# Start motor
python3 rs510_vfd_control.py --port auto --slave 3 --start 15.0

# Wait for temperature stabilization
echo "Waiting for temperature to stabilize..."
while true; do
    TEMP=$(python3 omron_temp_poll.py --port auto --unit 4 --get-pv --once --json | jq '.temp_C')
    echo "Current: ${TEMP}°C, Target: 60°C"

    # Check if within ±2°C of setpoint
    if (( $(echo "$TEMP > 58.0" | bc -l) )) && (( $(echo "$TEMP < 62.0" | bc -l) )); then
        echo "Temperature stabilized!"
        break
    fi
    sleep 5
done

# Start data acquisition
python3 acquire_scope_data.py config.json

# Stop motor
python3 rs510_vfd_control.py --port auto --slave 3 --stop

echo "Test complete!"
```

---

## Troubleshooting

### No Response from E5CC

**Symptoms:**
- Timeout errors
- "Failed to read register" messages
- No temperature returned

**Solutions:**

1. **Verify Unit ID:**
   ```bash
   # Try different slave IDs (common: 2 or 4)
   for id in 1 2 3 4; do
     echo "Testing unit ID: $id"
     python3 omron_temp_poll.py --port auto --unit $id --get-pv --once --debug
   done
   ```

2. **Check Communication Settings:**
   Try original E5CC settings:
   ```bash
   # Original baudrate and parity
   python3 omron_temp_poll.py --port auto --unit 2 --baudrate 57600 --parity E --get-pv --once --debug
   ```

3. **Verify Wiring:**
   - Check A+ to A+ and B- to B- connections
   - Verify cable continuity
   - Ensure GND is connected

4. **Check E5CC Configuration:**
   - Confirm Modbus RTU is enabled (Communications menu on E5CC)
   - Verify slave address matches `--unit` parameter
   - Check communication parameters (baud, parity, stop bits)

### Incorrect Temperature Reading

**Symptoms:**
- Temperature value off by factor of 10
- Readings like 620°C instead of 62°C

**Solutions:**

1. **Check Scale Factor:**
   ```bash
   # If reading is 10x too high, use scale 0.1
   python3 omron_temp_poll.py --port auto --unit 4 --get-pv --once --scale 0.1
   ```

2. **Verify E5CC Resolution Setting:**
   - Check E5CC menu: Advanced Settings → Display Resolution
   - Match `--scale` parameter to E5CC configuration

### Sensor Reading Errors

**Symptoms:**
- Temperature reading is `-1°C`, `9999°C`, or other unusual value
- E5CC display shows error code (e.g., `SSSS`, `SBBB`)

**Solutions:**

1. **Check Sensor Connection:**
   - Verify thermocouple/RTD is properly connected to E5CC input terminals
   - Check for broken wires or loose connections

2. **Verify Sensor Type Configuration:**
   - E5CC menu: Initial Settings → Sensor Type
   - Must match actual sensor (K-type TC, PT100, etc.)

3. **Check Sensor Range:**
   - Temperature may be out of configured range
   - E5CC menu: Initial Settings → Temperature Range

### Port Not Auto-Detected

**Symptoms:**
- "Could not resolve port 'auto'" error
- No FTDI device found

**Solutions:**

1. **List Available Ports:**
   ```bash
   python3 hardware_utils.py
   ```

2. **Check USB Connection:**
   ```bash
   # macOS
   ls /dev/tty.usbserial*

   # Linux
   ls /dev/ttyUSB*
   ```

3. **Use Explicit Port:**
   ```bash
   python3 omron_temp_poll.py --port /dev/tty.usbserial-XXXXXX --unit 4 --get-pv --once
   ```

4. **Check Permissions (Linux):**
   ```bash
   sudo usermod -a -G dialout $USER
   # Log out and back in
   ```

---

## Register Map Reference

### Temperature Registers (Holding Registers)

| Address | Name | Description | Units | Access |
|---------|------|-------------|-------|--------|
| 0x2000 | Process Value (PV) | Current measured temperature | °C × scale | R |
| 0x2103 | Setpoint Value (SV) | Target temperature | °C × scale | R/W |

### Scaling Examples

**1°C Resolution (scale = 1.0):**
```python
# Raw register value: 62
# Temperature: 62 × 1.0 = 62.0°C
```

**0.1°C Resolution (scale = 0.1):**
```python
# Raw register value: 623
# Temperature: 623 × 0.1 = 62.3°C
```

**Setting Setpoint:**
```python
# Desired temperature: 65.5°C
# Scale: 0.1
# Register value: int(65.5 / 0.1) = 655
```

### Additional Registers

Consult the Omron E5CC Modbus manual for additional registers:
- Control outputs (heating/cooling)
- Alarm status
- PID parameters
- Run/stop control

---

## Temperature Sensor Types

The E5CC supports various sensor types. Common configurations:

| Sensor Type | E5CC Code | Typical Range | Application |
|-------------|-----------|---------------|-------------|
| **K-type Thermocouple** | TC-K | -200 to 1300°C | General purpose, bearing tests |
| **PT100 RTD** | RTD PT100 | -200 to 850°C | High accuracy |
| **J-type Thermocouple** | TC-J | -200 to 1200°C | General purpose |
| **Voltage (0-5V)** | 0-5V | Configurable | Custom sensors |
| **Current (4-20mA)** | 4-20mA | Configurable | Custom sensors |

**For ForeverBearing Tests:**
- Recommended: K-type thermocouple
- Range: 0-200°C
- Resolution: 1°C (0.1°C for precision tests)
- Response time: Consider sensor thermal mass for bearing monitoring

---

## Safety Considerations

⚠️ **Important Safety Notes:**

1. **Temperature Monitoring:**
   - Set appropriate high-temperature alarms on E5CC
   - Monitor temperature continuously during test runs
   - Implement automatic shutdown at excessive temperatures

2. **Sensor Installation:**
   - Ensure proper thermal contact between sensor and bearing
   - Use appropriate mounting methods (compression fitting, thermal paste)
   - Protect sensor wiring from mechanical damage

3. **Control Outputs:**
   - If using E5CC heating/cooling outputs, verify safe operation
   - Test emergency shutdown procedures
   - Never exceed bearing manufacturer's temperature limits

4. **Data Validation:**
   - Verify sensor readings are reasonable before starting tests
   - Check for sensor failures (open circuit, short circuit)
   - Log temperature data for post-test analysis

---

## Related Documentation

- **Hardware Discovery**: `hardware_discovery_and_configuration.md`
- **RS510 VFD Driver**: `rs510_vfd_driver.md`
- **Shared Modbus Manager**: `shared_modbus_manager.py` (source code documentation)
- **Data Acquisition**: `DATA_MANAGEMENT.md`
- **Telemetry Collection**: `telemetry_collector.py` documentation

---

## Support and References

### Omron E5CC Documentation

- **Manufacturer**: Omron Corporation
- **Model**: E5CC Digital Temperature Controller
- **Manual**: Consult Omron E5CC user manual for:
  - Complete register map
  - Sensor configuration
  - PID tuning
  - Alarm settings
  - Communications setup

### Code Repository

- **Location**: `TestRigInstrumentation/py/omron_temp_poll.py`
- **Issues**: Report bugs or feature requests via project issue tracker

### Contact

For questions or support with the ForeverBearing test rig instrumentation system, contact the Test Rig Instrumentation Team.

---

**Document Version**: 1.0
**Last Updated**: 2025-11-05
**Author**: Test Rig Instrumentation Team
