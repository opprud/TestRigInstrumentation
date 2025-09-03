# MSO-X Data Acquisition & Telemetry

Tools to acquire waveforms from a **Keysight/Agilent MSO-X 2024A** over SCPI/TCPIP, store them in **HDF5**, plot/analyze with Python, and augment each sweep with **telemetry** (load cell via HX711 on RP2040, tachometer RPM via RP2040, and temperature via Omron E5CC over RS-485/Modbus).

## Features

- **Oscilloscope capture** (SCPI/TCPIP via PyVISA)
  - WORD (16-bit) or BYTE transfers, robust IEEE-488.2 block reads
  - Fresh capture per sweep: `:DIGitize → *OPC? → :WAV:PRE? → :WAV:DATA?`
  - Timezone-aware timestamps (CET/CEST) and UTC
  - Optional acquisition modes: `NORM | HRES | AVER`
- **Storage**: Compact, metadata-rich **HDF5**
  - `/metadata` + `/sweeps/sweep_XXX/<alias>/{time,voltage}` + per-channel attrs
  - Optional `/sweeps/sweep_XXX/telemetry/{load,speed,temperature}`
- **Telemetry**
  - **RP2040** (Arduino) firmware exposes ASCII protocol:
    - `LOAD?`, `TARE`, `SPEED?`, `SETCAL`, `CAL?`, `SETTIME`, `SETPPR`, …
    - EEPROM-emulated persistence for calibration (slope/tare)
  - **Python host** (`rp2040_tool.py`) with guided calibration and **--json** output
  - **Omron E5CC** temperature over Modbus/RS-485 (`e5cc_reader.py`)
- **Plotting**: `plot_waveform.py`
  - Time series, FFT, spectrogram
  - Channel colors match MSO defaults (CH1 yellow, CH2 green, CH3 blue, CH4 red)
  - Select channels by **alias** or by **scope source** (e.g., `CHAN1`)


---

## Repository layout

├── acquire_scope_data.py      # SCPI acquisition → HDF5 (with debug mode)
├── plot_waveform.py           # Plot time/FFT/spectrogram from HDF5
├── rp2040_tool.py             # Host tool for RP2040 (HX711 + tachometer)
├── e5cc_reader.py             # Omron E5CC temperature via Modbus/RS-485
├── firmware/
│   └── rp2040_hx711_tacho/    # Arduino sketch with EEPROM calibration
│       └── rp2040_hx711_tacho.ino
├── config.json                # Example configuration
├── requirements.txt
└── README.md

---

## Prerequisites & Setup

The acquisition script is a plain Python tool; recommended usage is inside a **virtual environment** to keep dependencies clean.  

### 1) Install Python
- Requires **Python 3.10+** (tested on macOS/Linux; Windows also fine).
```bash
python3 --version

python3 -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

###  Install dependencies
pip install -r requirements.txt



## Config (config.json)
```
{
  "scope_ip": "169.254.86.40",
  "acquisition": {
    "points": 1000000,
    "samples": 3,
    "interval_sec": 1.0,
    "waveform_format": "WORD",    // WORD(16-bit) or BYTE
    "points_mode": "NORM",        // RAW often rejected; NORM is safe
    "trigger_sweep": "AUTO",      // AUTO or NORM
    "acq_type": "NORM"            // NORM | HRES | AVER (+averages)
  },
  "channels": [
    { "name": "AE_probe", "source": "CHAN1", "enabled": true },
    { "name": "Accel",    "source": "CHAN2", "enabled": true }
  ],
  "sensors": {
    "rp2040": {
      "port": "/dev/tty.usbmodemXXXX",
      "baud": 115200,
      "timeout_sec": 1.0
    },
    "speed":      { "source": "rp2040", "enabled": true },
    "loadcell":   { "source": "rp2040", "enabled": true },
    "temperature": {
      "source": "modbus_e5cc", "enabled": false,
      "serial_port": "/dev/ttyUSB0", "baud": 9600, "parity": "N", "stopbits": 1,
      "slave_id": 1, "pv_register": 0, "pv_scale": 1.0
    }
  },
  "store": {
    "output_file": "data/data.h5",
    "timestamped": true,
    "compress": "none",
    "chunk": false,
    "attrs": { "project": "ForeverBearing", "operator": "morten" }
  }
}
```


