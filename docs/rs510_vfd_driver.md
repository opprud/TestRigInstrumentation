# RS510 VFD Motor Controller Driver

## Introduction

This page documents how to control and monitor the **RS PRO RS510 Frequency Converter (VFD)** using Python and Modbus RTU over an RS485/USB adapter. This allows remote control and monitoring of motor speed, run/stop state, and diagnostic information.

The RS510 VFD has registers exposed via Modbus, allowing control. See RS510 manual for detailed register specifications.

The Python script (`rs510_vfd_control.py`) provides:

- Set motor frequency (Hz, resolution 0.01 Hz)
- Start/Stop forward and reverse
- Emergency stop
- Read data: output frequency, current, bus voltage, temperature
- Read and decode fault codes

---

## Overview

The RS510 VFD (Variable Frequency Drive) driver provides Python-based control of the RS PRO RS510 Series frequency converter via Modbus RTU over RS485. This driver enables:

- Motor speed control (frequency command in Hz)
- Start/Stop/Emergency stop operations
- Real-time status monitoring (frequency, run state, faults)
- Configuration parameter access (acceleration, deceleration, limits)
- Shared bus operation with other Modbus devices (Omron E5CC)

**Key Features:**
- Thread-safe shared Modbus connection manager
- Automatic FTDI RS485 adapter detection
- Configurable retry logic and timeout protection
- JSON output for programmatic integration
- Debug mode for troubleshooting

---

## Hardware Setup

### Components

| Component | Description | Interface |
|-----------|-------------|-----------|
| **RS510 VFD** | RS PRO RS510 Series variable frequency drive | Modbus RTU (RS485) |
| **FTDI RS485 Adapter** | USB-to-RS485 converter (e.g., FT232R) | USB |
| **AC Motor** | 3-phase induction motor connected to VFD output | - |

### Wiring

**RS485 Bus Connection:**
```
USB Computer
    │
    └─► FTDI RS485 Adapter
            │
            ├─► A+ ───┐
            ├─► B- ───┼─► RS510 VFD (A+/B-)
            └─► GND ──┘
                      │
                      └─► Omron E5CC (optional, daisy-chain)
```

**Important:**
- Use twisted-pair cable for RS485 (A+/B-) connections
- Add 120Ω termination resistors at both ends of long RS485 bus runs (>10m)
- Keep RS485 cable away from high-voltage AC motor cables
- Verify VFD unit ID (slave address) matches configuration (typically 1, 2, or 3)

### VFD Configuration

Set the following parameters on the RS510 VFD (consult manual for P-codes):

| Parameter | Setting | Description |
|-----------|---------|-------------|
| **Communication Protocol** | Modbus RTU | Enable Modbus mode |
| **Baud Rate** | 9600 | Match `modbus_config.json` |
| **Parity** | None | Match `modbus_config.json` |
| **Slave Address (Unit ID)** | 3 | Default in config, adjustable |
| **Motor Parameters** | Per motor spec | Voltage, current, frequency ratings |

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

- `rs510_vfd_control.py` - Main VFD driver script
- `shared_modbus_manager.py` - Thread-safe Modbus connection manager
- `hardware_utils.py` - Auto-detection utilities
- `modbus_config.json` - Shared Modbus configuration
- `test_vfd_timeout.py` - Test script with timeout protection

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

**Port Configuration:**
- `"auto"` - Automatically detect FTDI RS485 adapter (recommended)
- `"/dev/tty.usbserial-XXXXXX"` (macOS) - Explicit device path
- `"/dev/ttyUSB0"` (Linux) - Explicit device path
- `"COM3"` (Windows) - Explicit COM port

---

## Command Reference

### Basic Usage

```bash
python3 rs510_vfd_control.py --port <PORT> --slave <ID> <COMMAND>
```

### Commands

#### 1. Status Check

```bash
# Human-readable status
python3 rs510_vfd_control.py --port auto --slave 3 --status

# JSON output for programmatic access
python3 rs510_vfd_control.py --port auto --slave 3 --json

# Enable debug output
python3 rs510_vfd_control.py --port auto --slave 3 --status --debug
```

**Example Output:**
```
RS510 Status @ 2025-11-05 12:53:47
  Frequency Command : 10.00 Hz
  Base Frequency    : 50.00 Hz
  Max Frequency     : 60.00 Hz
  Accel Time        : 5.0 s
  Decel Time        : 5.0 s
  Run Command       : RUN_FORWARD
  Fault Code        : None
```

#### 2. Start Motor

```bash
# Start motor at specified frequency (Hz)
python3 rs510_vfd_control.py --port auto --slave 3 --start 10.0

# Start with low frequency for testing
python3 rs510_vfd_control.py --port auto --slave 3 --start 5.0
```

**Safety Notes:**
- Start at low frequencies (5-10 Hz) for initial testing
- VFD will ramp up according to acceleration time setting
- Ensure mechanical load is safe before starting
- Maximum frequency limited by VFD configuration

#### 3. Stop Motor

```bash
# Normal stop (ramps down according to deceleration time)
python3 rs510_vfd_control.py --port auto --slave 3 --stop
```

#### 4. Health Check

```bash
# Check connection health and statistics
python3 rs510_vfd_control.py --port auto --slave 3 --health
```

**Example Output:**
```json
{
  "is_connected": false,
  "consecutive_failures": 0,
  "last_successful_op": 1762343678.086803,
  "seconds_since_success": 0.5,
  "connection_count": 0,
  "port": "/dev/cu.usbserial-FT07T8EH",
  "port_config": "auto",
  "timeout": 1.0,
  "max_retries": 2
}
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--port PORT` | Serial port (auto, or explicit path) | Required |
| `--slave ID` | Modbus slave/unit ID | 3 |
| `--baudrate RATE` | Serial baud rate | 9600 |
| `--debug` | Enable debug output | Off |
| `--status` | Read and display status | - |
| `--json` | Output status as JSON | - |
| `--health` | Show connection health | - |
| `--start HZ` | Start motor at frequency (Hz) | - |
| `--stop` | Stop motor | - |

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
from rs510_vfd_control import RS510VFDController, VFDCommand

# Initialize controller with auto-detection
vfd = RS510VFDController(port="auto", slave_id=3, debug=True)

# Connect
vfd.connect()

# Start motor at 10 Hz
vfd.start_forward(10.0)

# Read status
status = vfd.get_status()
print(f"Frequency: {status.frequency_cmd_hz} Hz")
print(f"Running: {status.is_running}")

# Stop motor
vfd.stop()

# Check health
health = vfd.get_health_status()
print(f"Connected: {health['is_connected']}")

# Cleanup
vfd.disconnect()
```

### VFDState Object

```python
@dataclass
class VFDState:
    frequency_cmd_hz: float        # Commanded frequency
    frequency_out_hz: float        # Actual output frequency
    base_freq_hz: float            # Base frequency setting
    max_freq_hz: float             # Maximum frequency limit
    accel_time_s: float            # Acceleration time
    decel_time_s: float            # Deceleration time
    run_command: VFDCommand        # Current run state
    fault_code: int                # Fault code (0 = no fault)
    is_running: bool               # Motor running status
    is_fault: bool                 # Fault present flag
    timestamp: str                 # Status timestamp
```

---

## Shared Modbus Operation

The driver uses `shared_modbus_manager.py` to enable safe concurrent access to the RS485 bus with other devices (e.g., Omron E5CC temperature controller).

### Features

- **Thread-safe**: Uses `threading.RLock()` for serialization
- **Automatic retries**: Configurable retry logic with exponential backoff
- **Health monitoring**: Tracks connection failures and recovery
- **Single connection**: Reuses one serial port connection across devices

### Example: Concurrent Access

```bash
# Terminal 1: Monitor VFD
while true; do
  python3 rs510_vfd_control.py --port auto --slave 3 --json
  sleep 2
done

# Terminal 2: Monitor temperature
while true; do
  python3 omron_temp_poll.py --port auto --unit 4 --get-pv --once
  sleep 2
done
```

Both scripts share the same FTDI adapter without conflicts.

---

## Example Workflows

### 1. Initial Test Sequence

```bash
# Step 1: Verify connection
python3 rs510_vfd_control.py --port auto --slave 3 --status --debug

# Step 2: Start at low speed
python3 rs510_vfd_control.py --port auto --slave 3 --start 5.0

# Step 3: Wait and check status
sleep 3
python3 rs510_vfd_control.py --port auto --slave 3 --status

# Step 4: Increase speed
python3 rs510_vfd_control.py --port auto --slave 3 --start 15.0

# Step 5: Stop motor
sleep 5
python3 rs510_vfd_control.py --port auto --slave 3 --stop
```

### 2. Automated Test with Script

```bash
# Run comprehensive timeout test
python3 test_vfd_timeout.py --port auto --slave 3
```

This script:
1. Tests connection health
2. Reads status with retries
3. Starts motor at 2 Hz
4. Runs for 2 seconds
5. Stops motor
6. Reports final statistics

### 3. Integration with Data Acquisition

The VFD status can be collected during test runs and stored in HDF5 files alongside oscilloscope data:

```python
from rs510_vfd_control import RS510VFDController

# During acquisition sweep
vfd = RS510VFDController(port="auto", slave_id=3)
status = vfd.get_status()

# Store in HDF5 metadata
sweep_grp.attrs['vfd_frequency_hz'] = status.frequency_cmd_hz
sweep_grp.attrs['vfd_is_running'] = status.is_running
```

---

## Troubleshooting

### No Response from VFD

**Symptoms:**
- Timeout errors
- "Failed to read register" messages
- No status returned

**Solutions:**

1. **Verify Unit ID:**
   ```bash
   # Try different slave IDs
   for id in 1 2 3 4; do
     echo "Testing slave ID: $id"
     python3 rs510_vfd_control.py --port auto --slave $id --status --debug
   done
   ```

2. **Check Wiring:**
   - Verify A+ to A+ and B- to B- connections
   - Check cable continuity
   - Ensure GND is connected

3. **Test Baud Rate:**
   ```bash
   # Try different baud rates
   python3 rs510_vfd_control.py --port auto --slave 3 --baudrate 19200 --status
   ```

4. **Check VFD Configuration:**
   - Confirm Modbus RTU is enabled on VFD
   - Verify slave address matches `--slave` parameter
   - Check communication parameters (baud, parity, stop bits)

### Motor Won't Start

**Symptoms:**
- Start command accepted but motor doesn't spin
- Fault code present

**Solutions:**

1. **Check Fault Code:**
   ```bash
   python3 rs510_vfd_control.py --port auto --slave 3 --status
   ```
   If fault code is non-zero, consult RS510 manual for fault description.

2. **Verify VFD Enable:**
   - Check that VFD front panel shows "ready" state
   - Ensure external enable input is satisfied (if used)
   - Reset fault by power-cycling VFD

3. **Check Motor Connections:**
   - Verify 3-phase motor wiring (U, V, W)
   - Ensure motor parameters match VFD configuration

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
   python3 rs510_vfd_control.py --port /dev/tty.usbserial-XXXXXX --slave 3 --status
   ```

4. **Check Permissions (Linux):**
   ```bash
   sudo usermod -a -G dialout $USER
   # Log out and back in
   ```

### Slow Response / Timeouts

**Symptoms:**
- Commands take several seconds
- Intermittent timeouts

**Solutions:**

1. **Reduce Timeout:**
   Edit `rs510_vfd_control.py:59` to use shorter timeout:
   ```python
   timeout=1.0  # Reduce from 2.0
   ```

2. **Check Bus Load:**
   - Disconnect other Modbus devices temporarily
   - Test VFD alone on bus

3. **Verify Cable Quality:**
   - Use shielded twisted-pair cable
   - Keep cable runs short (<50m without repeaters)
   - Add termination resistors

---

## Register Map Reference

### Command Registers (Holding Registers)

| Address | Name | Description | Units | Access |
|---------|------|-------------|-------|--------|
| 0x2501 | Run Command | 0=Stop, 1=Forward, 2=Reverse, 3=E-Stop | - | R/W |
| 0x2502 | Frequency Command | Target frequency × 100 | 0.01 Hz | R/W |
| 0x000B | Base Frequency | Motor base frequency × 100 | 0.01 Hz | R/W |
| 0x000C | Max Frequency | Maximum allowed frequency × 100 | 0.01 Hz | R/W |
| 0x000E | Acceleration Time | Time to ramp up × 10 | 0.1 s | R/W |
| 0x000F | Deceleration Time | Time to ramp down × 10 | 0.1 s | R/W |
| 0x0015 | Fault Code | Current fault code (0 = no fault) | - | R |

### Scaling Examples

```python
# Frequency: 50.0 Hz → register value 5000
register_value = int(50.0 * 100)  # 5000

# Acceleration time: 5.0 seconds → register value 50
register_value = int(5.0 * 10)  # 50
```

---

## Safety Considerations

⚠️ **Important Safety Notes:**

1. **Emergency Stop:**
   - Always have a physical emergency stop button wired to VFD
   - Do not rely solely on software control for safety

2. **Motor Protection:**
   - Configure VFD overcurrent protection
   - Set appropriate motor parameters (voltage, current, frequency)
   - Monitor motor temperature during extended operation

3. **Gradual Speed Changes:**
   - Start at low frequencies (5-10 Hz) for testing
   - Use appropriate acceleration/deceleration times
   - Never exceed motor or mechanical system ratings

4. **Supervision:**
   - Monitor first runs closely
   - Check for unusual vibration, noise, or heating
   - Verify direction of rotation before full-speed operation

---

## Related Documentation

- **Hardware Discovery**: `hardware_discovery_and_configuration.md`
- **Shared Modbus Manager**: `shared_modbus_manager.py` (source code documentation)
- **Data Acquisition**: `DATA_MANAGEMENT.md`
- **Telemetry Collection**: `telemetry_collector.py` documentation

---

## Support and References

### RS510 VFD Documentation

- **Manufacturer**: RS PRO
- **Model**: RS510 Series Variable Frequency Drive
- **Manual**: Consult RS510 user manual for register addresses and P-code parameters

### Code Repository

- **Location**: `TestRigInstrumentation/py/rs510_vfd_control.py`
- **Issues**: Report bugs or feature requests via project issue tracker

### Contact

For questions or support with the ForeverBearing test rig instrumentation system, contact the Test Rig Instrumentation Team.

---

**Document Version**: 1.0
**Last Updated**: 2025-11-05
**Author**: Test Rig Instrumentation Team
