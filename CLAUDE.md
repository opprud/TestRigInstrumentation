# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Test Rig Instrumentation project for ForeverBearing experiments that combines:
- **Keysight MSO-X 2024A oscilloscope** data acquisition via SCPI/TCP
- **RP2040 firmware** for HX711 load cell and tachometer readings
- **Python acquisition tools** for data collection and storage to HDF5
- **React frontend/dashboard** (this directory) for test control and visualization

## Architecture

### Backend Systems
- **Firmware**: PlatformIO-based RP2040 code (`../firmware/src/main.cpp`) with ASCII protocol for load/speed sensors
- **Python Tools**: Located in `../py/` for device communication and data acquisition
- **Data Storage**: HDF5 format with metadata and telemetry integration

### React Frontend (Current Directory)
The React application serves as:
- Dashboard for real-time monitoring of acquisition data
- Test runner interface for controlling measurement sessions  
- Visualization of waveforms, load cell data, and RPM measurements
- Integration layer with Python backend services

## Development Commands

### Firmware Development
```bash
# Build and upload firmware to RP2040
cd ../firmware
pio run --target upload --environment seeed-xiao-rp2040

# Monitor serial output
pio device monitor --port /dev/tty.usbmodemXXXX --baud 115200
```

### Python Tools
```bash
# Set up Python environment (from py directory)
cd ../py
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt

# Test RP2040 communication
python3 util_tool.py --port /dev/tty.usbmodemXXXX ping
python3 util_tool.py --port /dev/tty.usbmodemXXXX load --json

# Calibrate load cell
python3 util_tool.py --port /dev/tty.usbmodemXXXX calibrate --weight-g 100.0

# Acquire oscilloscope data to HDF5
python3 acquire_scope_data.py config.json --debug

# Plot waveforms from HDF5
python3 plot_waveform.py data/data_20241201_143022.h5 --sweep sweep_000 --channels AE,Accel --fft --spectrogram
```

### React Development
```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Run tests
npm test
```

## Key Integration Points

### RP2040 ASCII Protocol
The firmware exposes these commands over serial:
- `LOAD?` → mass readings with timestamps
- `SPEED?` → RPM data with pulse counts  
- `TARE` → zero the load cell
- `SETCAL <slope> <tare>` → set calibration parameters
- `SETTIME <unix_ms>` → synchronize device clock

### Python Backend APIs
- `util_tool.py` provides JSON output via `--json` flag for RP2040 sensor integration
- `acquire_scope_data.py` handles MSO-X 2024A data acquisition with PyVISA/SCPI
- `plot_waveform.py` generates time-domain, FFT, and spectrogram visualizations
- Data stored to HDF5 with `/metadata` and `/sweeps/sweep_XXX/<channel>/{time,voltage}` structure
- Configuration via `config.json` for scope IP, channels, acquisition settings

### Python Dependencies
```
python-dateutil  # timezone handling
numpy           # numerical processing  
pyvisa-py       # SCPI communication with oscilloscope
h5py            # HDF5 data storage
plotly          # interactive plotting (plot_waveform.py)
scipy           # signal processing (FFT, spectrograms)
pyserial        # RP2040 serial communication
```

### Expected React Components
- Real-time sensor monitoring (load cell, RPM, temperature)
- Oscilloscope configuration interface matching `config.json` structure
- Test sequence runner with start/stop/pause controls
- Waveform visualization with time/frequency domain plots
- HDF5 data browser and export functionality
- Serial port selection and RP2040 device management

## Hardware Configuration

- **Oscilloscope**: Keysight MSO-X 2024A at IP (currently: 169.254.5.204)
- **Microcontroller**: Seeed XIAO RP2040 with HX711 load cell amplifier  
- **Sensors**: Load cell (HX711), tachometer input, optional Omron E5CC temperature
- **Channels**: 4 analog channels (AE probe, accelerometer, ultrasound, temperature)

## Data Flow

1. **Acquisition**: `acquire_scope_data.py` triggers MSO-X captures via PyVISA/SCPI
2. **Telemetry**: Concurrent sensor readings from RP2040 via `util_tool.py --json`
3. **Storage**: Timestamped HDF5 files with metadata and per-sweep channel data
4. **Analysis**: `plot_waveform.py` provides time/FFT/spectrogram visualization  
5. **Integration**: React frontend orchestrates test sequences and displays results

## Configuration Files

### config.json Structure
```json
{
  "scope_ip": "169.254.5.204",
  "acquisition": {
    "points": 250000,
    "samples": 3,
    "interval_sec": 3,
    "waveform_format": "WORD",
    "points_mode": "RAW",
    "trigger_sweep": "AUTO", 
    "acq_type": "HRES"
  },
  "channels": [
    {"name": "AE", "source": "CHAN1", "enabled": true, "notes": "Kistler acoustic emission probe"},
    {"name": "Accel", "source": "CHAN2", "enabled": true, "notes": "Piezo accelerometer"},
    {"name": "UL", "source": "CHAN3", "enabled": true, "notes": "Ultrasound"},
    {"name": "Temp", "source": "CHAN4", "enabled": true, "notes": "Temperature"}
  ],
  "store": {
    "output_file": "data/data2.h5",
    "timestamped": true,
    "compress": "none",
    "chunk": false,
    "attrs": {"project": "ForeverBearing", "operator": "morten"}
  }
}
```

## Known Issues & TODO
- Python tools may need updates for React frontend integration
- Missing requirements: `plotly`, `scipy`, `pyserial` not in current requirements.txt
- Need API layer for web frontend to control acquisition and access HDF5 data